"""MCP client service for connecting to MCP servers and using their tools with persistent connections.

**The stdio attribution contract.** A stdio session here is persistent per
server, not per user: ``PersistentServerSession`` holds one child process per
server for as long as Vigil runs, and every caller's dispatch shares it. A
per-call identity therefore cannot cross the pipe — no argument, environment
variable, or protocol field can carry "this dispatch is for user X" into a
child that is already running. What attributes a stdio tool call is the pair
Vigil controls end to end: the hash-chained ``tool_call_audit`` row the
``call_tool`` funnel writes (actor read from ``current_caller()``, or
``"agent"`` when no person is bound), and the OTEL trace id the row shares
with the ``mcp.call_tool`` span. Per-user bearer tokens apply to HTTP-capable
connectors, not here; until a connector speaks HTTP, the audit row plus trace
id is the whole attribution.

**The HTTP identity contract.** An HTTP-capable connector — an entry with an
``http`` block in mcp-config.json — dispatches over Streamable HTTP with a
per-(user, server) session whose bearer token is bound to that connector
alone (see ``identity.py``). A connector that has not been authorized by the
acting user fails closed; no static token, no cross-server token, no shared
session across users.
"""

import asyncio
import json
import logging
import ssl
import threading
import time
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    MCP_AVAILABLE = True
except ImportError:
    try:
        # Try alternative import path
        from mcp.client import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        MCP_AVAILABLE = True
    except ImportError:
        MCP_AVAILABLE = False
        # Define dummy types for when MCP is not available
        if TYPE_CHECKING:
            from mcp import ClientSession, StdioServerParameters
        else:
            ClientSession = Any
            StdioServerParameters = Any

try:
    import httpx2
    from mcp.client.streamable_http import streamable_http_client

    HTTP_MCP_AVAILABLE = True
except ImportError:
    HTTP_MCP_AVAILABLE = False
    httpx2 = None  # type: ignore[assignment]

    def streamable_http_client(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Streamable HTTP transport requires the mcp package")


from core.audit import tool_calls
from core.integrations.mcp.child_env import ca_bundle_env
from core.integrations.mcp.identity import (
    AuthorizationRequired,
    IdentityError,
    ServerOAuthClient,
    TokenStore,
)
from core.integrations.mcp.service import MCPService
from core.integrations.mcp.surface import current_caller
from core.secrets import get_secret

logger = logging.getLogger(__name__)


class PersistentServerSession:
    """Manages a persistent connection to an MCP server."""

    def __init__(self, server_name: str, server_params):
        self.server_name = server_name
        self.server_params = server_params
        self.session: Optional[ClientSession] = None
        self.read_stream = None
        self.write_stream = None
        self.stdio_context = None
        self.session_context = None
        self.is_connected = False
        self.last_error: Optional[str] = None
        self.lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Establish persistent connection to the server."""
        async with self.lock:
            if self.is_connected and self.session:
                return True

            try:
                # Create stdio client connection
                self.stdio_context = stdio_client(self.server_params)
                self.read_stream, self.write_stream = (
                    await self.stdio_context.__aenter__()
                )

                # Create session
                self.session_context = ClientSession(
                    self.read_stream, self.write_stream
                )
                self.session = await self.session_context.__aenter__()

                # Initialize session
                await self.session.initialize()

                self.is_connected = True
                logger.info(
                    f"✓ Established persistent connection to {self.server_name}"
                )
                return True

            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                logger.error(f"Failed to connect to {self.server_name}: {e}")
                await self._cleanup()
                return False

    async def disconnect(self):
        """Disconnect from the server."""
        async with self.lock:
            await self._cleanup()

    async def _cleanup(self):
        """Internal cleanup method (must be called with lock held)."""
        try:
            if self.session_context:
                try:
                    await self.session_context.__aexit__(None, None, None)
                except Exception:
                    pass

            if self.stdio_context:
                try:
                    await self.stdio_context.__aexit__(None, None, None)
                except Exception:
                    pass

            self.session = None
            self.session_context = None
            self.stdio_context = None
            self.read_stream = None
            self.write_stream = None
            self.is_connected = False

        except Exception as e:
            logger.debug(f"Error during cleanup of {self.server_name}: {e}")

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool using the persistent session."""
        async with self.lock:
            if not self.is_connected or not self.session:
                # Try to reconnect
                logger.warning(
                    f"Session not connected for {self.server_name}, attempting to reconnect..."
                )
                if not await self._reconnect_internal():
                    raise RuntimeError(f"Failed to connect to {self.server_name}")

            try:
                result = await self.session.call_tool(tool_name, arguments)
                return tool_result_to_dict(result)

            except Exception as e:
                logger.error(
                    f"Tool call failed for {self.server_name}.{tool_name}: {e}"
                )
                # Mark as disconnected and try to reconnect on next call
                self.is_connected = False
                raise

    async def _reconnect_internal(self) -> bool:
        """Internal reconnect (must be called with lock held)."""
        await self._cleanup()
        return await self._connect_internal()

    async def _connect_internal(self) -> bool:
        """Internal connect (must be called with lock held)."""
        try:
            self.stdio_context = stdio_client(self.server_params)
            self.read_stream, self.write_stream = await self.stdio_context.__aenter__()

            self.session_context = ClientSession(self.read_stream, self.write_stream)
            self.session = await self.session_context.__aenter__()

            await self.session.initialize()

            self.is_connected = True
            return True

        except Exception as e:
            logger.error(f"Reconnect failed for {self.server_name}: {e}")
            await self._cleanup()
            return False


def tool_result_to_dict(result) -> Dict[str, Any]:
    """Convert an MCP CallToolResult into the dict contract every session
    type returns (stdio and Streamable HTTP alike)."""
    content_list = []
    for content_item in result.content:
        if hasattr(content_item, "text"):
            content_list.append({"type": "text", "text": content_item.text})
        elif hasattr(content_item, "type"):
            content_list.append(
                {"type": str(content_item.type), "text": str(content_item)}
            )
        else:
            content_list.append({"type": "text", "text": str(content_item)})
    return {
        "error": result.is_error,
        "content": content_list,
    }


def _timeout_result(timeout: float) -> Dict[str, Any]:
    """The timeout answer, shared by both dispatch paths."""
    return {
        "error": True,
        "content": [
            {
                "type": "text",
                "text": f"Tool call timed out after {timeout} seconds. The MCP server may not be responding.",
            }
        ],
    }


def _error_result(reason: str) -> Dict[str, Any]:
    """A tool-call failure that never left the building.

    Same shape as a real tool result so callers have one contract, with the
    reason spelled for the audit row and the console.
    """
    return {
        "error": True,
        "content": [{"type": "text", "text": f"MCP dispatch refused: {reason}"}],
    }


def default_http_client_factory():
    """The httpx2 client the MCP HTTP transport runs on.

    One client per session, carrying the bearer as a default header — the
    transport's per-request MCP headers merge over it and never replace it.
    """
    if httpx2 is None:
        raise RuntimeError("Streamable HTTP transport requires the httpx2 package")
    return httpx2.AsyncClient(
        timeout=httpx2.Timeout(30.0, read=300.0),
        follow_redirects=True,
        verify=_tls_verify(),
    )


def _tls_verify():
    """Honor the CA bundle env the stdio path already respects.

    ``ssl.create_default_context`` reads SSL_CERT_FILE/SSL_CERT_DIR itself;
    ``ca_bundle_env`` normalizes the legacy alias variables into those names.
    """
    bundle = ca_bundle_env()
    if "SSL_CERT_FILE" in bundle:
        context = ssl.create_default_context(cafile=bundle["SSL_CERT_FILE"])
        return context
    if "SSL_CERT_DIR" in bundle:
        context = ssl.create_default_context(capath=bundle["SSL_CERT_DIR"])
        return context
    return True


class _ChallengeObservingClient:
    """An httpx2 client that records the challenge of a 401 it observes.

    The MCP HTTP transport discards the status line — the only place the
    ``WWW-Authenticate`` challenge survives is the raw HTTP response. This
    proxy watches the response before the transport parses it and records
    both the refusal and the challenge when the resource server rejects
    the bearer.
    """

    def __init__(self, inner):
        # Bound to the wrapped client's lifecycle: closing this proxy
        # closes the inner client and nothing else.
        self._inner = inner
        self.observed_401 = False
        self.last_401_challenge: Optional[str] = None

    @property
    def observed_unauthorized(self) -> bool:
        return self.observed_401

    def reset_observation(self) -> None:
        self.observed_401 = False

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _observe(self, response) -> None:
        if response.status_code == 401 and "www-authenticate" in response.headers:
            self.observed_401 = True
            self.last_401_challenge = response.headers["www-authenticate"]

    async def send(self, request, **kwargs):
        response = await self._inner.send(request, **kwargs)
        self._observe(response)
        return response

    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        response = await self._inner.stream(method, url, **kwargs).__aenter__()
        try:
            self._observe(response)
            yield response
        finally:
            await response.aclose()

    async def aclose(self) -> None:
        await self._inner.aclose()


class HttpServerSession:
    """One user's Streamable HTTP session with one HTTP-capable connector.

    The stdio contract above explains why these are per (server, user):
    the session id is created under a bearer, and the connector binds the
    session to whoever that bearer named. Sharing one across users would
    attribute this user's calls to whoever initialized first.
    """

    def __init__(
        self,
        server_name: str,
        mcp_url: str,
        bearer_token: str,
        client_factory=None,
    ):
        self.server_name = server_name
        self.mcp_url = mcp_url
        self.bearer_token = bearer_token
        self.client_factory = (
            client_factory
            if client_factory is not None
            else default_http_client_factory
        )
        self.session: Optional[ClientSession] = None
        self._streams_context: Optional[AbstractAsyncContextManager] = None
        self._session_context: Optional[AbstractAsyncContextManager] = None
        self._transport_client: Optional[_ChallengeObservingClient] = None
        self.lock = asyncio.Lock()
        self.is_connected = False
        self.last_error: Optional[str] = None
        self.last_401_challenge: Optional[str] = None
        self.unauthorized = False

    async def connect(self) -> bool:
        """Open the streams, build the client, initialize the session."""
        if self.session is not None:
            return True
        if httpx2 is None or not HTTP_MCP_AVAILABLE:
            self.last_error = (
                "Streamable HTTP transport unavailable (httpx2/mcp missing)"
            )
            return False
        try:
            inner = self.client_factory()
            inner.headers["Authorization"] = f"Bearer {self.bearer_token}"
            self._transport_client = _ChallengeObservingClient(inner)
            self._streams_context = streamable_http_client(
                url=self.mcp_url,
                # The proxy forwards the full AsyncClient surface (send,
                # stream, and everything else via __getattr__); mypy can
                # only see that it is not a subclass.
                http_client=self._transport_client,  # type: ignore[arg-type]
            )
            read_stream, write_stream = await self._streams_context.__aenter__()
            self._session_context = ClientSession(read_stream, write_stream)
            self.session = await self._session_context.__aenter__()
            await self.session.initialize()
            self.is_connected = True
            return True
        except Exception as exc:
            # The SDK 2.1.1 transport surfaces protocol failures as re-raised
            # exceptions over the read stream — no dedicated error type — so
            # the 401 verdict comes from the challenge-aware client's flag,
            # not from the exception class.
            if self._transport_client is not None and getattr(
                self._transport_client, "observed_unauthorized", False
            ):
                self.unauthorized = True
                self.last_401_challenge = self._transport_client.last_401_challenge
                self.last_error = (
                    f"{self.server_name} refused the bearer token "
                    f"(401 {self.last_401_challenge or 'no challenge'})"
                )
            else:
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.error("Failed to connect to %s: %s", self.server_name, exc)
            await self.disconnect()
            return False

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool on this user's session."""
        async with self.lock:
            if not self.is_connected or not self.session:
                self.last_error = f"session not connected for {self.server_name}"
                raise RuntimeError(f"Failed to connect to {self.server_name}")
            try:
                result = await self.session.call_tool(tool_name, arguments)
                return tool_result_to_dict(result)
            except Exception:
                # A mid-session 401 shows up as the challenge-aware client's
                # flag, whichever exception class the transport re-raised.
                if self._transport_client is not None and getattr(
                    self._transport_client, "observed_unauthorized", False
                ):
                    self.unauthorized = True
                raise
            except Exception as exc:
                logger.error(
                    f"Tool call failed for {self.server_name}.{tool_name}: {exc}"
                )
                raise

    async def disconnect(self):
        """Tear the session down in reverse construction order."""
        self.is_connected = False
        self.session = None
        for ctx in (self._session_context, self._streams_context):
            if ctx is not None:
                try:
                    await ctx.__aexit__(None, None, None)
                except Exception:
                    pass
        self._session_context = None
        self._streams_context = None
        if self._transport_client is not None:
            try:
                await self._transport_client.aclose()
            except Exception:
                pass
            self._transport_client = None


class MCPClient:
    """Client for connecting to MCP servers and using their tools with persistent connections."""

    def __init__(self, mcp_service: MCPService):
        """
        Initialize MCP client with persistent connection support.

        Args:
            mcp_service: MCPService instance for managing server processes
        """
        self.mcp_service = mcp_service
        self.persistent_sessions: Dict[str, PersistentServerSession] = {}
        self.tools_cache: Dict[str, List[Dict]] = {}
        self._connection_locks: Dict[str, threading.Lock] = (
            {}
        )  # Locks per server to prevent concurrent connections
        # Populated by connect_to_server — string reason on failure, and a
        # structured list of env var names when credentials are missing.
        self.last_errors: Dict[str, str] = {}
        self.last_missing_credentials: Dict[str, List[str]] = {}
        # HTTP-capable connectors: one OAuth client per server (its client
        # registration + discovery cache), one Streamable HTTP session per
        # (server, user) — a session id is created under one user's bearer
        # and the connector binds it to that user — and one shared token
        # store, so the cross-server passthrough guard answers against a
        # single key space.
        self._token_store = TokenStore()
        self._oauth_clients: Dict[str, ServerOAuthClient] = {}
        self.http_sessions: Dict[Tuple[str, str], HttpServerSession] = {}
        self._last_oauth_errors: Dict[Tuple[str, str], str] = {}

    async def connect_to_server(
        self,
        server_name: str,
        persistent: bool = True,
        skip_enabled_check: bool = False,
        username: Optional[str] = None,
    ) -> bool:
        """
        Connect to an MCP server, cache its tools, and optionally maintain persistent connection.

        Only connects if the server is enabled in the MCP service, unless
        ``skip_enabled_check`` is set for a temporary pre-enable probe. On failure, the
        exception message is recorded on ``self.last_errors[server_name]`` so the
        Settings → MCP UI can surface *why* a connection failed (missing binary,
        credentials, package not installed) instead of a generic "Failed to connect".

        A server that is already connected returns here without calling ``list_tools``.
        Callers that need a fresh handshake have to list tools on that session themselves.

        Args:
            server_name: Name of the server to connect to
            persistent: If True, maintain persistent connection for reuse
            skip_enabled_check: Probe a disabled server anyway. The disabled
                return below records no error, so a test would look like a
                silent failure that never contacted the process.
            username: The signed-in user to connect an HTTP-capable
                connector as. Required for http entries — sessions and
                bearer tokens are per user — and ignored for stdio.

        Returns:
            True if successful, False otherwise
        """
        # Clear any stale state from a prior attempt so the UI always
        # reflects the most recent connect.
        self.last_errors.pop(server_name, None)
        self.last_missing_credentials.pop(server_name, None)

        if not MCP_AVAILABLE:
            logger.error("MCP SDK not available")
            self.last_errors[server_name] = "MCP SDK not installed in the backend venv"
            return False

        if server_name not in self.mcp_service.servers:
            logger.error(f"Unknown server: {server_name}")
            self.last_errors[server_name] = "Server not present in mcp-config.json"
            return False

        # Skip disabled servers. A pre-enable probe sets skip_enabled_check
        # so this return — False with no last_error — is not the test result.
        if not skip_enabled_check and not self.mcp_service.is_server_enabled(
            server_name
        ):
            logger.debug(f"Server {server_name} is disabled, skipping connection")
            return False

        # Check if already connected with cached tools
        if server_name in self.persistent_sessions and server_name in self.tools_cache:
            if self.persistent_sessions[server_name].is_connected:
                logger.debug(f"Already connected to {server_name}")
                return True

        server = self.mcp_service.servers[server_name]

        # Credential gate: if the server declared ${VAR} placeholders in
        # its mcp-config.json entry and those env vars resolve empty,
        # short-circuit without spawning a child. This is dormancy by
        # design — per #124's conclusion, pre-configuration is not a
        # failure. The UI's existing "Not Configured" treatment takes
        # over once it sees connected=false + a missing_credentials list.
        missing = self._missing_credentials_for(server)
        if missing:
            msg = f"missing credentials: {', '.join(missing)}"
            self.last_errors[server_name] = msg
            self.last_missing_credentials[server_name] = missing
            logger.info(
                "MCP server %s dormant — waiting on env vars: %s",
                server_name,
                ", ".join(missing),
            )
            return False

        # HTTP-capable connectors never spawn a child: their "connection"
        # is a per-user Streamable HTTP session under that user's
        # audience-bound bearer. Without a signed-in user there is no
        # identity to attach — fail closed with the reason on last_errors.
        if server.is_http:
            return await self._connect_http_server(server, username)

        try:
            # Create stdio server parameters. stdio_client narrows the child
            # environment to a six-name allowlist, so a CA bundle set in the
            # backend's environment has to be forwarded rather than inherited.
            if not server.command:
                # An HTTP-capable entry or a malformed stdio entry has no
                # command to spawn; record it like any other connect failure.
                self.last_errors[server_name] = "stdio server has no command to spawn"
                return False
            server_params = StdioServerParameters(
                command=server.command,
                args=server.args,
                env={**ca_bundle_env(), **(server.env or {})},
            )

            if persistent:
                # Create persistent session
                if server_name not in self.persistent_sessions:
                    self.persistent_sessions[server_name] = PersistentServerSession(
                        server_name, server_params
                    )

                # Connect. The session logs and swallows the spawn error;
                # keep it on last_errors so a probe can report it.
                if not await self.persistent_sessions[server_name].connect():
                    err = self.persistent_sessions[server_name].last_error
                    if err:
                        self.last_errors[server_name] = err
                    return False

                # Get tools from the persistent session
                session = self.persistent_sessions[server_name].session
                if session is None:
                    self.last_errors[server_name] = "session not connected"
                    return False
                tools_result = await session.list_tools()

            else:
                # Temporary connection just to get tools
                async with stdio_client(server_params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()

            self._cache_tools(server_name, tools_result)

            logger.info(
                f"Connected to {server_name}, found {len(self.tools_cache[server_name])} tools"
            )
            return True

        except Exception as e:
            # Preserve the exception text so the UI can surface the real
            # reason (e.g. "FileNotFoundError: uvx", "ModuleNotFoundError:
            # mcp", "missing env var GITHUB_TOKEN") instead of a
            # generic "Failed to connect".
            self.last_errors[server_name] = f"{type(e).__name__}: {e}"
            logger.error(f"Failed to connect to {server_name}: {e}")
            return False

    def _cache_tools(self, server_name: str, tools_result) -> None:
        """Normalize a ListToolsResult into ``tools_cache``."""
        self.tools_cache[server_name] = []
        for tool in tools_result.tools:
            # Get input schema - handle both dict and object formats
            input_schema = tool.input_schema
            if hasattr(input_schema, "model_dump"):
                input_schema = input_schema.model_dump()
            elif hasattr(input_schema, "dict"):
                input_schema = input_schema.dict()
            elif not isinstance(input_schema, dict):
                input_schema = dict(input_schema) if input_schema else {}

            # Ensure it's a valid JSON schema
            if not isinstance(input_schema, dict):
                input_schema = {}

            self.tools_cache[server_name].append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": input_schema,
                }
            )

    def _oauth_client_for(self, server) -> ServerOAuthClient:
        """The per-server OAuth client, built once and cached.

        The registered secret resolves through ``get_secret`` here — the one
        credential-read channel — exactly as a spawned server's env would.
        """
        client = self._oauth_clients.get(server.name)
        if client is None:
            oauth = server.oauth
            client = ServerOAuthClient(
                server_name=server.name,
                http_url=server.http_url,
                client_id=oauth.client_id,
                client_secret=oauth.client_secret(),
                scopes=oauth.scopes,
                store=self._token_store,
            )
            self._oauth_clients[server.name] = client
        return client

    async def _http_session_ready(
        self,
        server,
        oauth: ServerOAuthClient,
        username: str,
        allow_refresh: bool = True,
    ) -> Optional[HttpServerSession]:
        """A connected per-user session for (server, username), or None.

        Refresh-then-reacquire: when the connector refuses the cached
        bearer with 401 + WWW-Authenticate, one refresh grant is tried and
        the session rebuilt. A refused or missing refresh drops the token
        and raises — the user authorizes again, nothing falls back to a
        static or cross-server token.
        """
        key = (server.name, username)
        existing = self.http_sessions.get(key)
        if existing is not None:
            if existing.is_connected and not existing.unauthorized:
                return existing
            self.http_sessions.pop(key, None)
            await existing.disconnect()

        session = HttpServerSession(
            server_name=server.name,
            mcp_url=server.http_url,
            bearer_token=await oauth.bearer_token(username),
        )
        if await session.connect():
            self.http_sessions[key] = session
            return session

        if session.unauthorized and allow_refresh:
            refreshed = await oauth.refresh(username)
            if refreshed is None:
                oauth.invalidate(username)
                raise AuthorizationRequired(
                    f"connector {server.name} refused its token for {username} "
                    "— re-authorize the connector in Settings"
                )
            token = await oauth.bearer_token(username)
            session = HttpServerSession(
                server_name=server.name,
                mcp_url=server.http_url,
                bearer_token=token,
            )
            if await session.connect():
                self.http_sessions[key] = session
                return session
            if session.unauthorized:
                oauth.invalidate(username)
                raise AuthorizationRequired(
                    f"connector {server.name} refused its refreshed token for "
                    f"{username} — re-authorize the connector in Settings"
                )

        self._last_oauth_errors[key] = session.last_error or "connection failed"
        return None

    async def _connect_http_server(self, server, username: Optional[str]) -> bool:
        """Connect (and cache tools for) an HTTP-capable connector for one user."""
        server_name = server.name
        if username is None:
            self.last_errors[server_name] = (
                "HTTP connector: no signed-in user — connectors authorize per user"
            )
            return False
        oauth = self._oauth_client_for(server)
        try:
            session = await self._http_session_ready(server, oauth, username)
        except AuthorizationRequired as exc:
            self.last_errors[server_name] = str(exc)
            return False
        except IdentityError as exc:
            self.last_errors[server_name] = str(exc)
            return False
        if session is None:
            self.last_errors[server_name] = self._last_oauth_errors.get(
                (server_name, username), "connection failed"
            )
            return False
        try:
            inner_session = session.session
            if inner_session is None:
                self.last_errors[server_name] = "session not connected"
                return False
            tools_result = await inner_session.list_tools()
        except Exception as exc:
            self.last_errors[server_name] = f"{type(exc).__name__}: {exc}"
            logger.error("Failed to list tools on %s: %s", server_name, exc)
            return False
        self._cache_tools(server_name, tools_result)
        logger.info(
            "Connected to %s as %s (per-user HTTP session), found %d tools",
            server_name,
            username,
            len(self.tools_cache[server_name]),
        )
        return True

    def _missing_credentials_for(self, server) -> List[str]:
        # Resolves through get_secret, so a credential saved via the integration
        # wizard (encrypted store, not the process env) does not read as dormant.
        required = getattr(server, "required_env_vars", None) or []
        if not required:
            return []
        missing: List[str] = []
        for var in required:
            if not get_secret(var):
                missing.append(var)
        return missing

    def get_missing_credentials(self, server_name: str) -> Optional[List[str]]:
        """Return the list of unset required env vars from the last connect."""
        return getattr(self, "last_missing_credentials", {}).get(server_name)

    def get_last_error(self, server_name: str) -> Optional[str]:
        """Return the most recent connect-failure reason for a server, if any."""
        return getattr(self, "last_errors", {}).get(server_name)

    # Per-server rate limit between auto-retry attempts. Prevents a
    # misconfigured secret (wrong value, typo) from hammering the MCP
    # child process with connect storms on every /connections/status
    # poll. 15s balances "user saves key and sees it online quickly"
    # with "don't spin up 20 subprocesses a minute on a stuck setup".
    _RETRY_MIN_INTERVAL_S = 15.0

    async def retry_dormant_if_ready(self) -> Dict[str, bool]:
        """Re-attempt connect for any dormant server whose required env
        vars have since resolved (e.g. user saved the credential via the
        integration wizard). Safe to call from a read-path endpoint:
        no-op when nothing's dormant or when creds are still missing.

        Returns a dict ``{server_name: connected_bool}`` recording what
        we actually tried this call — the common case is an empty dict.
        """
        # Defensive init — mirrors connect_to_server's compat shim.
        if not hasattr(self, "_last_retry_at"):
            self._last_retry_at: Dict[str, float] = {}
        if not hasattr(self, "last_missing_credentials"):
            return {}

        import time

        now = time.monotonic()
        attempted: Dict[str, bool] = {}

        # Snapshot the keys — ``last_missing_credentials`` is mutated
        # by ``connect_to_server`` we're about to call.
        candidates = [
            name
            for name, missing in list(self.last_missing_credentials.items())
            if missing
        ]
        for server_name in candidates:
            server = self.mcp_service.servers.get(server_name)
            if server is None:
                continue
            # Cheap precheck — skip unless creds actually resolve now.
            if self._missing_credentials_for(server):
                continue
            # Rate-limit: don't retry the same server more than once
            # per _RETRY_MIN_INTERVAL_S seconds.
            last = self._last_retry_at.get(server_name, 0.0)
            if now - last < self._RETRY_MIN_INTERVAL_S:
                continue
            self._last_retry_at[server_name] = now
            try:
                attempted[server_name] = await self.connect_to_server(
                    server_name, persistent=True
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Dormant-retry for %s raised: %s", server_name, exc)
                attempted[server_name] = False
        if attempted:
            connected = sum(1 for v in attempted.values() if v)
            logger.info(
                "Auto-reconnect: %d/%d dormant server(s) came online",
                connected,
                len(attempted),
            )
        return attempted

    async def list_tools(
        self, server_name: Optional[str] = None
    ) -> Dict[str, List[Dict]]:
        """
        List available tools from MCP servers.

        Args:
            server_name: Optional server name to list tools from. If None, lists from all servers.

        Returns:
            Dictionary mapping server names to lists of tool definitions
        """
        if not MCP_AVAILABLE:
            return {}

        tools = {}

        if server_name:
            if server_name in self.tools_cache:
                tools[server_name] = self.tools_cache[server_name]
            else:
                # Try to connect and get tools
                if await self.connect_to_server(server_name):
                    tools[server_name] = self.tools_cache.get(server_name, [])
        else:
            # List tools from all servers
            for name in self.mcp_service.list_servers():
                if name in self.tools_cache:
                    tools[name] = self.tools_cache[name]
                else:
                    # Try to connect
                    if await self.connect_to_server(name):
                        tools[name] = self.tools_cache.get(name, [])

        return tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Call a tool on an MCP server using persistent connection with timeout.

        Args:
            server_name: Name of the server
            tool_name: Name of the tool to call
            arguments: Tool arguments
            timeout: Timeout in seconds (default: 30)

        Returns:
            Tool result dictionary

        Every dispatch is audited — the actor ``current_caller()`` names (or
        "agent"), the arguments by digest, and the outcome the server gave, a
        timeout and a refused connect included. The write is fail-closed: a
        dispatch whose audit row cannot land raises rather than answering, so
        this funnel never returns an unaudited result.
        """
        started = time.perf_counter()
        result = await self._dispatch_tool(server_name, tool_name, arguments, timeout)
        tool_calls.record_tool_call(
            actor_username=current_caller() or tool_calls.ACTOR_AGENT,
            surface=tool_calls.SURFACE_MCP_CLIENT,
            server_name=server_name,
            tool_name=tool_name,
            args=arguments,
            decision=tool_calls.DECISION_ALLOW,
            outcome="error" if result.get("error") else "ok",
            duration_ms=int((time.perf_counter() - started) * 1000),
            trace_id=tool_calls.current_trace_id(),
        )
        return result

    async def _dispatch_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """The dispatch itself: session management, timeout, span, result shape."""
        if not MCP_AVAILABLE:
            return {
                "error": "MCP SDK not available",
                "content": [{"type": "text", "text": "MCP SDK not available"}],
            }

        if server_name not in self.mcp_service.servers:
            return {
                "error": f"Unknown server: {server_name}",
                "content": [{"type": "text", "text": f"Unknown server: {server_name}"}],
            }

        server = self.mcp_service.servers[server_name]

        # OTEL span for transport-level MCP call
        _mcp_span = None
        _mcp_t0 = time.monotonic()
        try:
            from opentelemetry.trace import SpanKind
            from opentelemetry.trace import StatusCode as _SC

            from core.telemetry import get_tracer

            _mcp_tracer = get_tracer("vigil.core.integrations.mcp.client")
            _mcp_span = _mcp_tracer.start_span(
                "mcp.call_tool",
                kind=SpanKind.CLIENT,
                attributes={
                    "mcp.server.name": server_name,
                    "mcp.transport": "http" if server.is_http else "stdio",
                    "vigil.tool.name": tool_name,
                    "vigil.tool.input_size": len(json.dumps(arguments, default=str)),
                    "vigil.actor": current_caller() or tool_calls.ACTOR_AGENT,
                },
            )
        except Exception:
            _SC = None

        if server.is_http:
            # HTTP-capable connector: dispatch on the caller's own per-user
            # session under an audience-bound bearer. Same funnel, same audit
            # row — but the session is this user's alone.

            async def _dispatch_call():
                return await self._dispatch_http(server, tool_name, arguments, timeout)

        else:
            # Ensure we have a persistent session
            if server_name not in self.persistent_sessions:
                logger.info(f"Creating persistent connection to {server_name}...")
                if not await self.connect_to_server(server_name, persistent=True):
                    _err = {
                        "error": True,
                        "content": [
                            {
                                "type": "text",
                                "text": f"Failed to connect to server: {server_name}",
                            }
                        ],
                    }
                    try:
                        if _mcp_span is not None:
                            _mcp_span.set_attribute("vigil.tool.success", False)
                            _mcp_span.end()
                    except Exception:
                        pass
                    return _err

            persistent_session = self.persistent_sessions[server_name]

            async def _dispatch_call():
                try:
                    return await persistent_session.call_tool(tool_name, arguments)
                except Exception as e:
                    logger.error(
                        f"Error in tool call {tool_name} on {server_name}: {e}"
                    )
                    raise

        try:
            # Apply timeout
            result = await asyncio.wait_for(_dispatch_call(), timeout=timeout)
            is_err = bool(result.get("error")) if isinstance(result, dict) else False
            if is_err:
                _detail = next(
                    (c["text"] for c in result.get("content") or [] if c.get("text")),
                    "",
                )[:200]
                logger.warning(
                    "Tool call %s.%s returned an error: %s",
                    server_name,
                    tool_name,
                    _detail,
                )
            try:
                if _mcp_span is not None:
                    _mcp_span.set_attribute("vigil.tool.success", not is_err)
                    if is_err and _SC is not None:
                        _mcp_span.set_status(_SC.ERROR, _detail)
                    _mcp_span.set_attribute(
                        "vigil.tool.output_size", len(json.dumps(result, default=str))
                    )
                    _mcp_span.set_attribute(
                        "vigil.tool.duration_ms",
                        round((time.monotonic() - _mcp_t0) * 1000, 1),
                    )
                    _mcp_span.end()
            except Exception:
                pass
            return result
        except asyncio.TimeoutError:
            logger.error(
                f"Tool call {tool_name} on {server_name} timed out after {timeout}s"
            )
            try:
                if _mcp_span is not None and _SC is not None:
                    _mcp_span.set_attribute("vigil.tool.success", False)
                    _mcp_span.set_status(_SC.ERROR, f"Timeout after {timeout}s")
                    _mcp_span.end()
            except Exception:
                pass
            return _timeout_result(timeout)
        except Exception as e:
            logger.error(f"Error calling tool {tool_name} on {server_name}: {e}")
            try:
                if _mcp_span is not None:
                    _mcp_span.set_attribute("vigil.tool.success", False)
                    _mcp_span.end()
            except Exception:
                pass
            return {
                "error": True,
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
            }

    async def _dispatch_http(
        self,
        server,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """Dispatch one tool call over Streamable HTTP as the bound caller.

        The bearer is the acting user's own audience-bound token for this
        connector (identity.py). No signed-in user, no dispatch: a headless
        call has nothing identity-true to attach, and attaching anything
        else — a static token, another connector's token — is precisely the
        passthrough this transport prohibits.
        """
        server_name = server.name
        username = current_caller()
        if not username:
            return _error_result(
                f"{server_name} is an OAuth connector and requires a signed-in "
                "user; per-user HTTP sessions have no agent attribution to fall back on"
            )
        oauth = self._oauth_client_for(server)
        try:
            session = await self._http_session_ready(server, oauth, username)
        except AuthorizationRequired as exc:
            return _error_result(str(exc))
        except IdentityError as exc:
            return _error_result(str(exc))
        if session is None:
            return _error_result(
                self._last_oauth_errors.get(
                    (server_name, username), "connection failed"
                )
            )
        try:
            return await asyncio.wait_for(
                session.call_tool(tool_name, arguments), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Tool call {tool_name} on {server_name} timed out after {timeout}s"
            )
            return _timeout_result(timeout)
        except Exception:
            # The connector refused this user's bearer mid-session:
            # _http_session_ready refreshes once and rebuilds the session
            # (or raises AuthorizationRequired). One retry on the rebuilt
            # session, then stop — a second refusal is a user action,
            # not something more retries fix.
            if not session.unauthorized:
                raise
            self.http_sessions.pop((server_name, username), None)
            await session.disconnect()
            try:
                session = await self._http_session_ready(server, oauth, username)
            except AuthorizationRequired as exc:
                return _error_result(str(exc))
            except IdentityError as exc:
                return _error_result(str(exc))
            if session is None:
                return _error_result(
                    self._last_oauth_errors.get(
                        (server_name, username), "connection failed"
                    )
                )
            try:
                return await asyncio.wait_for(
                    session.call_tool(tool_name, arguments), timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"Tool call {tool_name} on {server_name} timed out after {timeout}s"
                )
                return _timeout_result(timeout)
            except Exception as exc:
                logger.error(f"Error calling tool {tool_name} on {server_name}: {exc}")
                return {
                    "error": True,
                    "content": [{"type": "text", "text": f"Error: {str(exc)}"}],
                }

    def get_tools_for_claude(self) -> List[Dict]:
        """
        Get all available tools formatted for Claude's tool use API.

        Returns:
            List of tool definitions in Claude's format
        """
        all_tools = []

        for server_name, tools in self.tools_cache.items():
            for tool in tools:
                # Format tool for Claude API
                claude_tool = {
                    "name": f"{server_name}_{tool['name']}",
                    "description": f"[{server_name}] {tool['description']}",
                    "input_schema": tool.get("inputSchema", {}),
                }
                all_tools.append(claude_tool)

        return all_tools

    async def disconnect_from_server(self, server_name: str) -> bool:
        """
        Disconnect from a specific MCP server.

        Args:
            server_name: Name of the server to disconnect from

        Returns:
            True if successful, False otherwise
        """
        if server_name in self.persistent_sessions:
            try:
                await self.persistent_sessions[server_name].disconnect()
                del self.persistent_sessions[server_name]
                logger.info(f"Disconnected from {server_name}")
                return True
            except Exception as e:
                logger.error(f"Error disconnecting from {server_name}: {e}")
                return False
        # Per-user HTTP sessions count as "connected" too — drop every
        # user's session for this connector; tokens stay cached.
        for key in [k for k in self.http_sessions if k[0] == server_name]:
            try:
                await self.http_sessions.pop(key).disconnect()
            except Exception as e:
                logger.error("Error disconnecting %s (%s): %s", server_name, key[1], e)
        return True

    def get_connection_status(self) -> Dict[str, bool]:
        """
        Get connection status for all servers.

        Returns:
            Dictionary mapping server names to connection status
        """
        status = {}
        for server_name in self.mcp_service.list_servers():
            if server_name in self.persistent_sessions:
                status[server_name] = self.persistent_sessions[server_name].is_connected
            else:
                status[server_name] = False
        return status

    async def close_all(self):
        """Close all persistent MCP server connections and clear cache."""
        logger.info("Closing all MCP server connections...")

        # Disconnect all persistent sessions sequentially to avoid context issues
        for server_name in list(self.persistent_sessions.keys()):
            try:
                await self.persistent_sessions[server_name].disconnect()
                logger.info(f"Disconnected from {server_name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {server_name}: {e}")

        for key in list(self.http_sessions.keys()):
            try:
                await self.http_sessions.pop(key).disconnect()
            except Exception as e:
                logger.error("Error disconnecting %s (%s): %s", key[0], key[1], e)

        # Clear all state
        self.persistent_sessions.clear()
        self.tools_cache.clear()

        logger.info("All MCP connections closed")


# An MCPClient owns persistent stdio child processes that only its creator closes, so
# exactly one may exist per process. The owner builds it and installs it here.
_process_client: Optional[MCPClient] = None


def build_mcp_client() -> Optional[MCPClient]:
    """Build a client, or None when the MCP SDK is not installed."""
    if not MCP_AVAILABLE:
        logger.error("MCP SDK not available. Install with: pip install mcp")
        return None
    return MCPClient(MCPService())


def set_process_mcp_client(client: Optional[MCPClient]) -> None:
    global _process_client
    _process_client = client


# None until an owner (the API lifespan, daemon startup) has installed a client.
def process_mcp_client() -> Optional[MCPClient]:
    return _process_client
