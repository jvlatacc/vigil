"""Serving Vigil's own MCP server at /mcp, to callers that are not Vigil.

The same server the agent calls directly in this process, given an address.
Nothing about a tool changes: what changes is that a request arrives from
somewhere, so it has to say who it is, and what it does is recorded against
that person rather than against "an agent".

Three gates, in order, because each one's answer means something different:

* **Closed.** The surface is off, and a 404 says so. Not 403: a door nobody
  opened should not announce that it exists and is locked.
* **Unauthenticated.** No credential, or one that does not work. 401 with a
  challenge, and the same answer for every way a credential can fail.
* **Open.** The principal is bound for the duration of the call, which is what
  ``caller()`` reads when a tool records who did something.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, NamedTuple, Optional

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.audit import tool_calls
from core.auth.mcp_credential_service import authenticate
from core.auth.permissions import username_has_tool_permission
from core.integrations.mcp.surface import VIGIL_SERVER, acting_as, is_enabled

logger = logging.getLogger(__name__)

MOUNT_PATH = "/mcp"

# The credential a developer gets for free, and only with the bypass on.
#
# Without it, trying the surface locally means minting a real credential before
# the first request, which is friction with no safety in it: a machine anyone
# can already reach unauthenticated through DEV_MODE is not protected by making
# its MCP surface harder to try.
#
# It is a constant, so it is not a secret, and it is written to look like one
# that was never meant to be kept. It is refused outright when the bypass is
# off -- which is every packaged path and every install that did not opt in --
# and its use is announced, like the other gates the bypass opens.
DEV_MODE_TOKEN = "vgl_mcp_DEV_MODE_ONLY_not_a_secret"


class BareMountPath:
    """Makes ``/mcp`` and ``/mcp/`` the same address, before routing decides.

    A Starlette mount at ``/mcp`` compiles to ``^/mcp/(?P<path>.*)$``, so the
    bare spelling -- the one MOUNT_PATH, the README and env.example all
    advertise, and the one anyone configuring a client will paste -- does not
    match it. What answers instead depends on what else is registered:

    * With no frontend build, nothing matches, and Starlette's redirect_slashes
      rescues it with a 307 to the slash form.
    * With a frontend build, the SPA catch-all claims every path. It is GET-only,
      so a POST matches it by path and not by method -- a partial match, which is
      still a match, so the search stops and answers 405 and the redirect never
      runs. The gate is never reached.

    Since CI never builds the frontend, only the first case is ever exercised
    there, which is why a surface unreachable in every real install looked fine.

    Rewriting the path here rather than registering a second route puts this
    ahead of routing, so it cannot be decided by what is registered around it.
    """

    def __init__(self, app: ASGIApp, path: str):
        self.app = app
        self.bare = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == self.bare:
            scope = {**scope, "path": self.bare + "/"}
            raw = scope.get("raw_path")
            if raw is not None:
                scope["raw_path"] = raw + b"/"
        await self.app(scope, receive, send)


def serve_at(app, gate: ASGIApp, context_path: str = "") -> str:
    """Put ``gate`` at the advertised address, both ways of writing it.

    Returns the address, which is what an operator is told at startup.
    """
    address = f"{context_path}{MOUNT_PATH}"
    app.mount(address, gate, name="mcp")
    app.add_middleware(BareMountPath, path=address)
    return address


def _bearer(scope: Scope) -> Optional[str]:
    for key, value in scope.get("headers") or []:
        if key.lower() != b"authorization":
            continue
        parts = value.decode("latin-1").split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    return None


class _ToolCall(NamedTuple):
    """The tool a request would run, and the arguments it names."""

    name: str
    arguments: Dict[str, Any]


async def _drain_request_body(receive: Receive, seen: List[Message]) -> bytes:
    """Read the request body to its end, remembering every message.

    The gate has to read the body to know whether a request is a tool call at
    all -- but the server behind it reads the body too. The remembered
    messages are handed back by ``_replay``, so the body is read once and
    consumed twice rather than read and lost.
    """
    chunks: List[bytes] = []
    while True:
        message = await receive()
        seen.append(message)
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            return b"".join(chunks)


def _replay(seen: List[Message], receive: Receive) -> Receive:
    """The messages the gate already read first, then whatever comes next."""
    queued = list(seen)

    async def replay() -> Message:
        if queued:
            return queued.pop(0)
        return await receive()

    return replay


def _tool_call_of(scope: Scope, body: bytes) -> Optional[_ToolCall]:
    """The tool a request would run, when it is a tool call at all.

    Of the protocol's methods only ``tools/call`` executes anything: setup,
    discovery and pings neither ask for nor answer to a permission. A body
    that does not parse is not for the gate to name -- the server behind it
    answers that, as it did before this check existed.
    """
    if scope.get("method") != "POST" or not body:
        return None
    try:
        message = json.loads(body)
    except ValueError:
        return None
    if not isinstance(message, dict) or message.get("method") != "tools/call":
        return None
    params = message.get("params")
    if not isinstance(params, dict):
        return None
    name = params.get("name")
    if not isinstance(name, str) or not name:
        return None
    arguments = params.get("arguments")
    return _ToolCall(
        name=name, arguments=arguments if isinstance(arguments, dict) else {}
    )


class McpSurfaceGate:
    """Decides whether a request reaches the MCP server, and as whom.

    The server app it guards is built by the lifespan rather than at import,
    because each ``streamable_http_app()`` carries its own session manager and
    a manager runs once. The mount is fixed; what it points at is not.
    """

    def __init__(self, app: Optional[ASGIApp] = None):
        self.app = app

    async def _unserved(self, scope: Scope, receive: Receive, send: Send) -> None:
        """No server behind the mount: the lifespan has not run, or has ended."""
        await JSONResponse({"detail": "MCP surface unavailable"}, status_code=503)(
            scope, receive, send
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            if self.app is not None:
                await self.app(scope, receive, send)
            return

        if not is_enabled():
            await JSONResponse({"detail": "Not Found"}, status_code=404)(
                scope, receive, send
            )
            return

        token = _bearer(scope)
        user = _dev_mode_user(token) if token else None
        if user is None and token:
            user = authenticate(token)
        if user is None:
            # One answer for no credential, an unknown one, a revoked one and
            # an expired one. A holder of a working credential learns nothing
            # from the difference; someone trying them would learn plenty.
            await JSONResponse(
                {"detail": "Not authenticated"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return

        if self.app is None:
            await self._unserved(scope, receive, send)
            return

        received: List[Message] = []
        request_body = await _drain_request_body(receive, received)
        call = _tool_call_of(scope, request_body)

        # The one method that executes anything, so the one method whose
        # caller's standing is checked. The surface exposes Vigil's own tools
        # only: every tool here answers to the server named "vigil", whose
        # scope a role holds through the baseline grant or not at all.
        if call is not None and not username_has_tool_permission(
            user.username, VIGIL_SERVER
        ):
            tool_calls.record_tool_call(
                actor_username=user.username,
                surface=tool_calls.SURFACE_MCP_INBOUND,
                server_name=VIGIL_SERVER,
                tool_name=call.name,
                args=call.arguments,
                decision=tool_calls.DECISION_DENY,
                deny_reason="permission",
                trace_id=tool_calls.current_trace_id(),
            )
            await JSONResponse(
                {"detail": "tool not permitted for this role"}, status_code=403
            )(scope, _replay(received, receive), send)
            return

        started = time.perf_counter()
        status_code: List[int] = []

        async def _with_status(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code.append(message["status"])
            await send(message)

        with acting_as(user.username):
            await self.app(
                _owned_by(scope, user), _replay(received, receive), _with_status
            )

        # Written once the response is away, so the row carries what the call
        # answered. A write that fails raises and is logged -- never swallowed:
        # an unaudited tool call is the one thing this surface must not produce.
        if call is not None:
            tool_calls.record_tool_call(
                actor_username=user.username,
                surface=tool_calls.SURFACE_MCP_INBOUND,
                server_name=VIGIL_SERVER,
                tool_name=call.name,
                args=call.arguments,
                decision=tool_calls.DECISION_ALLOW,
                outcome="ok" if status_code and status_code[0] < 400 else "error",
                duration_ms=int((time.perf_counter() - started) * 1000),
                trace_id=tool_calls.current_trace_id(),
            )


def _owned_by(scope: Scope, user) -> Scope:
    """The scope, saying whose it is in the terms the session manager reads.

    A session belongs to the credential that opened it, and the SDK enforces
    that by comparing ``scope["user"]`` against the principal recorded when the
    session was created -- but only when that user is one of its own
    ``AuthenticatedUser``. Vigil authenticates ahead of the server rather than
    through its token verifier, so without this the principal is ``None`` on
    every request, ``None`` matches ``None``, and any authenticated caller who
    learned another's ``mcp-session-id`` could post on it.

    The principal is the person, not the credential: two credentials issued to
    one user are one principal, and may continue each other's session.
    """
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    return {
        **scope,
        "user": AuthenticatedUser(
            AccessToken(
                token="",
                client_id=user.username,
                scopes=[],
                subject=str(getattr(user, "user_id", user.username)),
            )
        ),
    }


def _dev_mode_user(token: str):
    """The developer this stands for, or None when the bypass is off.

    Read live rather than at import so that a test, or an operator changing it,
    does not get an answer decided when this module first loaded.
    """
    if token != DEV_MODE_TOKEN:
        return None

    from core.config import get_settings

    if not get_settings().dev_mode:
        logger.warning(
            "An MCP request presented the development credential; the bypass is "
            "off, so it was refused."
        )
        return None

    from core.auth.current_user import _get_dev_user
    from core.storage.unit_of_work import unit_of_work

    logger.warning(
        "MCP request authenticated by the development credential, not a minted one."
    )
    with unit_of_work() as session:
        return _get_dev_user(session)


def announce(enabled: bool, credential_count: int) -> None:
    """Say at startup what this install is serving, and to whom.

    A surface that is open but that no credential can open is not broken and
    does not stop a boot -- it is a state somebody will otherwise spend an
    afternoon on, so it is said out loud instead.
    """
    if not enabled:
        logger.info("MCP surface: off. Nothing outside Vigil can reach its tools.")
        return

    logger.warning(
        "MCP surface: ON at %s. Vigil's own tools are reachable from the network.",
        MOUNT_PATH,
    )
    from core.config import get_settings

    if get_settings().dev_mode:
        logger.warning(
            "MCP surface: the development bypass is on, so %s also accepts a "
            "fixed credential that is not a secret and works nowhere else.",
            MOUNT_PATH,
        )
    elif credential_count == 0:
        logger.warning(
            "MCP surface: no credentials exist, so every request to %s will be "
            "refused. Mint one before a caller can use it.",
            MOUNT_PATH,
        )
