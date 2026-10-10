"""MCP service for managing MCP servers."""

import json
import logging
import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from core.config import vigil_path
from core.detections.detection_rules_service import DetectionRulesService
from core.integrations.integration_bridge_service import IntegrationBridgeService
from core.integrations.mcp.child_env import default_child_env
from core.integrations.mcp.packaged import installed_launch
from core.secrets import get_secret

logger = logging.getLogger(__name__)

# Stands in for "$" inside an already-substituted value (see _substitute_env_vars).
_LITERAL_DOLLAR = "\x00"


# One grammar for ${VAR} and ${VAR:-default} placeholders, shared by the
# substitution engine and the dormancy extraction below — a name one side can
# resolve must be a name the other side checks. The old split (uppercase-only
# here, any-name there) let a lowercase ${var} substitute to "" without ever
# appearing in the dormancy check.
_PLACEHOLDER_RE = re.compile(r"\$\{([^}:]+)(?::-((?:\$\{[^}]+\}|[^{}])*))?\}")

# Backwards-compatible alias: the extractor matches the same grammar the
# substitution engine does.
_ENV_PLACEHOLDER_RE = _PLACEHOLDER_RE

# The substitution grammar above is deliberately permissive (any-name
# ${var:-default}); a secret NAME must stay a strict env identifier. The
# client_secret_env check leans on this pattern, not on the substitution
# grammar, so loosening substitution can never let a malformed name through.
_STRICT_ENV_NAME_RE = re.compile(r"[A-Z_][A-Z0-9_]*")

# Placeholders that are path sentinels, not credentials — never treat as
# required env vars.
_PLACEHOLDER_BLACKLIST = {"workspaceFolder", "HOME", "PYTHONPATH", "VIGIL_DIR"}


def resolve_opt_in(name: str) -> Optional[str]:
    """Resolve a child-env opt-in name: ambient first, then the secret store.

    The ambient read is the process boundary the ENV001 ratchet allows here:
    the name reaches a spawned child only because that child's own config
    opted in via ``required_env_vars`` or a ``${VAR}`` reference.
    """
    ambient = os.environ.get(name)  # noqa: ENV001 - child env opt-in boundary
    return ambient or get_secret(name)


def extract_required_env_vars(
    raw_env: Dict[str, str], raw_args: List[str]
) -> List[str]:
    """Collect every ``${VAR}`` placeholder referenced by a server config.

    Scans the raw (pre-substitution) ``env`` values and ``args`` entries
    from ``mcp-config.json``. Returns a deduplicated, sorted list of
    placeholder names. These are treated as required by
    ``mcp_client.connect_to_server`` — if any resolve to empty, the
    server is considered dormant-by-design (not a connect failure).

    The scan uses the same grammar the substitution engine does (see
    ``_PLACEHOLDER_RE``): every name substitution could resolve is a name
    checked here, in either case. ``${VAR:-default}`` is skipped — it is
    self-satisfying and cannot silently substitute empty.

    Limitation (documented for follow-ups): this infers requirements
    from the config file. A server whose process quietly needs a
    credential that isn't referenced via ``${…}`` is invisible to us —
    list it in the entry's ``required_env_vars`` for ambient forwarding,
    or reference it via a placeholder.
    """
    found: set[str] = set()
    for value in list((raw_env or {}).values()) + list(raw_args or []):
        if not isinstance(value, str):
            continue
        for m in _ENV_PLACEHOLDER_RE.finditer(value):
            if m.group(2) is not None:
                # ${VAR:-default} is self-satisfying: substitution can always
                # resolve it to at least the default, so it can never
                # silently substitute empty and must not hold the server
                # dormant. Ambient forwarding for such a name goes through
                # the entry's explicit required_env_vars list.
                continue
            name = m.group(1)
            if name in _PLACEHOLDER_BLACKLIST:
                continue
            found.add(name)
    return sorted(found)


@dataclass(frozen=True)
class OAuthConnectorConfig:
    """A connector's OAuth client registration, declared in mcp-config.json.

    ``client_secret_env`` names the secret, it never carries the value: the
    value resolves through ``get_secret`` at use — the one credential-read
    channel.
    """

    client_id: str
    client_secret_env: Optional[str] = None
    scopes: Tuple[str, ...] = ()

    def client_secret(self) -> Optional[str]:
        """The registered secret, resolved through the credential channel."""
        if not self.client_secret_env:
            return None
        return get_secret(self.client_secret_env)


class MCPServer:
    """Represents an MCP server process."""

    def __init__(
        self,
        name: str,
        command: Optional[str],
        args: List[str],
        cwd: str,
        env: Dict[str, str],
        required_env_vars: Optional[List[str]] = None,
        http_url: Optional[str] = None,
        oauth: Optional[OAuthConnectorConfig] = None,
    ):
        self.name = name
        self.command = command
        self.args = args
        self.cwd = cwd
        self.env = env
        # Credential placeholders declared in mcp-config.json for this
        # server. Read by mcp_client.connect_to_server at connect time.
        self.required_env_vars: List[str] = list(required_env_vars or [])
        # An HTTP-capable connector dispatches over Streamable HTTP instead
        # of a spawned child; ``oauth`` carries its client registration and
        # is None for a connector that accepts a static bearer or none.
        self.http_url: Optional[str] = http_url
        self.oauth: Optional[OAuthConnectorConfig] = oauth

    @property
    def is_http(self) -> bool:
        """Whether this connector dispatches over Streamable HTTP."""
        return self.http_url is not None


class MCPService:
    """Service for managing MCP servers."""

    # A filename, not a path: resolving at class-definition time is what crashed
    # the daemon in #695, and would pin the read path while the write path
    # resolves fresh.
    _STATE_FILENAME = "mcp_server_enabled.json"

    def __init__(
        self,
        project_root: Optional[Path] = None,
        integration_bridge: Optional[IntegrationBridgeService] = None,
        detection_rules: Optional[DetectionRulesService] = None,
    ):
        """
        Initialize the MCP service.

        Args:
            project_root: Optional project root path. Defaults to the repo root,
                which is where ``mcp-config.json`` and ``venv/`` live.
        """
        if project_root is None:
            # core/integrations/mcp/service.py -> repo root is four levels up.
            project_root = Path(__file__).resolve().parents[3]

        self._integration_bridge = integration_bridge or IntegrationBridgeService()
        self._detection_rules = detection_rules or DetectionRulesService()
        self.project_root = Path(project_root)
        self.venv_path = self.project_root / "venv"

        # Determine Python executable
        if platform.system() == "Windows":
            self.python_exe = self.venv_path / "Scripts" / "python.exe"
        else:
            self.python_exe = self.venv_path / "bin" / "python"
        if not self.python_exe.is_file():
            self.python_exe = Path(sys.executable)

        # Load enabled state (servers default to disabled)
        self._enabled_servers: Dict[str, bool] = self._load_enabled_state()

        # Initialize servers
        self.servers: Dict[str, MCPServer] = {}
        self._initialize_servers()

    # ---- Enabled / Disabled state persistence ----

    def _load_enabled_state(self) -> Dict[str, bool]:
        """Load the enabled/disabled state from disk. Returns empty dict if no file."""
        try:
            state_file = vigil_path(self._STATE_FILENAME)
            if state_file.exists():
                with open(state_file, "r") as f:
                    data = json.load(f)
                return data.get("enabled", {})
        except Exception as e:
            logger.warning(f"Could not load MCP enabled state: {e}")
        return {}

    def _save_enabled_state(self) -> None:
        """Persist the enabled/disabled state to disk."""
        try:
            write_path = vigil_path(self._STATE_FILENAME, write=True)
            with open(write_path, "w") as f:
                json.dump({"enabled": self._enabled_servers}, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save MCP enabled state: {e}")

    # Internal/platform servers that should be on by default.
    #
    # Vigil's own server is not here: it is not a server Vigil connects to but
    # functions in this process, registered by core.integrations.mcp.in_process
    # and reachable whether or not anything is enabled.
    _DEFAULT_ENABLED = {
        "security-detections",
        # The self-hosted SIEM a hunt reads through telemetry_search -- the
        # customer's own Splunk, the expected telemetry path, not an optional
        # add-on. Safe to default-on: it declares no env placeholder (its config
        # comes from Settings via resolve(), #1113), so with nothing configured
        # it starts and answers "Splunk not configured", not failing a boot.
        "splunk-selfhosted",
    }

    def is_server_enabled(self, server_name: str) -> bool:
        """Check whether a server is enabled. Internal platform servers default to True; all others default to False."""
        return self._enabled_servers.get(
            server_name,
            server_name in self._DEFAULT_ENABLED,
        )

    def set_server_enabled(self, server_name: str, enabled: bool) -> bool:
        """
        Enable or disable a server and persist the change.

        Returns True if the server exists, False otherwise.
        """
        if server_name not in self.servers:
            return False
        self._enabled_servers[server_name] = enabled
        self._save_enabled_state()
        logger.info(f"Server '{server_name}' {'enabled' if enabled else 'disabled'}")
        return True

    def get_all_enabled_states(self) -> Dict[str, bool]:
        """Return a dict of server_name -> enabled for every known server."""
        return {name: self.is_server_enabled(name) for name in self.servers}

    def _substitute_env_vars(
        self, value: str, env: Optional[Mapping[str, str]] = None
    ) -> str:
        """Expand ``${VAR}`` and ``${VAR:-default}`` in a config string.

        Resolves against ``env`` — the environment the child is actually spawned
        with — so anything the spawn site pinned there is seen rather than
        collapsed to an empty string. A name the reduced env lacks falls
        through to the secret store.

        Only the template is expanded. A resolved value is spliced in as plain
        text, so a stored value that itself contains ``${...}`` (a saved
        connector URL, say) cannot name another variable or secret to read.

        This is the trust-full form: both env values and stored secrets may
        flow into the result. It is for the child's *environment*; strings
        bound for argv go through ``_substitute_public_value``.
        """
        source: Mapping[str, str] = os.environ if env is None else env  # noqa: ENV001
        return self._expand(value, source, from_secrets=True, keep_unresolved=False)

    def _substitute_public_value(self, value: str, env: Mapping[str, str]) -> str:
        """Expand ``${VAR}`` in argv-bound strings — env-declared values only.

        The secret store is never consulted (E3): a resolved credential must
        not land in argv, where ``/proc/<pid>/cmdline`` reads it out to every
        same-UID process on the host. A placeholder that resolves to nothing
        here stays literal, so a child that expands ``${VAR}`` from its own
        environment — mcp-remote does exactly that for ``--header`` values —
        keeps its template intact.
        """
        return self._expand(value, env, from_secrets=False, keep_unresolved=True)

    def _expand(
        self,
        value: str,
        source: Mapping[str, str],
        *,
        from_secrets: bool,
        keep_unresolved: bool,
    ) -> str:
        def replace_var(match):
            var_name = match.group(1)
            default = match.group(2)
            # A non-empty export wins; empty counts as unset, as in bash ${VAR:-d}
            # and everywhere else credentials resolve.
            env_val = source.get(var_name)
            if not env_val and from_secrets:
                env_val = get_secret(var_name)
            if env_val:
                return env_val.replace("$", _LITERAL_DOLLAR)
            if default is not None:
                return self._expand(
                    default,
                    source,
                    from_secrets=from_secrets,
                    keep_unresolved=keep_unresolved,
                ).replace("$", _LITERAL_DOLLAR)
            return match.group(0) if keep_unresolved else ""

        # Repeat only to unwind nested defaults; resolved values carry no "$"
        # until the end, so they are never matched again.
        prev = None
        while prev != value:
            prev = value
            value = _PLACEHOLDER_RE.sub(replace_var, value)

        return value.replace(_LITERAL_DOLLAR, "$")

    def reload_server_configs(self) -> None:
        """Rebuild server configs so a connectorUrl saved after startup is
        re-substituted into the init-time-cached spawn args."""
        self._initialize_servers()

    def _http_server_config(
        self, server_name: str, server_config: Mapping
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Parse one HTTP-capable connector entry.

        Returns ``(config, None)`` when the entry declares a well-formed
        ``http`` block, ``(None, None)`` when the entry is a stdio server,
        and ``(None, reason)`` for a malformed http block — malformed must
        skip the server rather than fall through to stdio parsing, which
        would spawn a pointless default command.
        """
        http_cfg = server_config.get("http")
        if not isinstance(http_cfg, dict) or not http_cfg:
            return None, None

        # Substitution sources mirror the stdio path: the backend's own
        # environment, so `${CONNECTOR_MCP_URL}` from an integration's
        # connectorUrl resolves exactly as it does for a spawned server.
        # Read-only use — no child env is built here (nothing spawns), so
        # the CA-bundle forwarding the child-env ratchet requires does not
        # apply to this site.
        env = (
            os.environ
        )  # noqa: ENV001 - read-only substitution source; no child env built

        raw_url = str(http_cfg.get("url") or "")
        url = self._substitute_env_vars(raw_url, env)

        raw_auth = http_cfg.get("auth") or {}
        if not isinstance(raw_auth, dict):
            raw_auth = {}
        auth_type = raw_auth.get("type")
        raw_client_id = str(raw_auth.get("client_id") or "")

        error = None
        if not raw_url or not url:
            error = "http.url is missing or empty"
        elif auth_type != "oauth":
            error = "http.auth.type must be 'oauth' (only the MCP authorization model is supported)"
        elif not raw_client_id or not self._substitute_env_vars(raw_client_id, env):
            error = "http.auth.client_id is missing or empty"
        if error:
            return None, error

        client_id = self._substitute_env_vars(raw_client_id, env)
        raw_secret_env = raw_auth.get("client_secret_env")
        client_secret_env = str(raw_secret_env).strip() if raw_secret_env else None
        # Secret values are never declared inline: the entry names the
        # secret's env var, and the value resolves through get_secret.
        if raw_secret_env and not _STRICT_ENV_NAME_RE.fullmatch(
            client_secret_env or ""
        ):
            return None, "http.auth.client_secret_env must name an env var"

        scopes = tuple(str(s) for s in raw_auth.get("scopes") or [])
        required = extract_required_env_vars({}, [raw_url, raw_client_id])
        if client_secret_env:
            required = sorted(set(required) | {client_secret_env})

        return (
            {
                "name": server_name,
                "command": None,
                "args": [],
                "cwd": str(self.project_root),
                "env": {},
                "required_env_vars": required,
                "http_url": url,
                "oauth": OAuthConnectorConfig(
                    client_id=client_id,
                    client_secret_env=client_secret_env,
                    scopes=scopes,
                ),
            },
            None,
        )

    def _initialize_servers(self):
        """
        Initialize MCP server configurations from mcp-config.json.

        Loads server configurations dynamically from the mcp-config.json file
        to ensure consistency with MCP integration workflows.
        Also includes servers for enabled integrations.
        """
        python_exe_str = str(self.python_exe)
        project_path_str = str(self.project_root)

        # Resolve ${<ID>_MCP_URL} placeholders from integration connectorUrls
        # (see derive_remote_mcp_env). Best-effort.
        try:
            self._integration_bridge.derive_remote_mcp_env()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("remote MCP env derivation skipped: %s", e)

        # Load servers from mcp-config.json
        mcp_config_path = self.project_root / "mcp-config.json"
        server_configs = []

        if mcp_config_path.exists():
            try:
                with open(mcp_config_path, "r") as f:
                    mcp_config = json.load(f)

                for server_name, server_config in mcp_config.get(
                    "mcpServers", {}
                ).items():
                    # Skip comment keys
                    if server_name.startswith("_comment"):
                        continue

                    # An HTTP-capable connector declares an "http" block
                    # instead of a spawn command: it dispatches over
                    # Streamable HTTP (see client.py) and must be handled
                    # here, before any stdio parsing could misread it.
                    http_entry, http_error = self._http_server_config(
                        server_name, server_config
                    )
                    if http_error:
                        logger.error(
                            "Skipping MCP server %s: %s", server_name, http_error
                        )
                        continue
                    if http_entry is not None:
                        server_configs.append(http_entry)
                        continue

                    # Convert config format from mcp-config.json to our internal format
                    command = server_config.get("command", "python")

                    # Use venv python if command is just "python" or "python3"
                    if command in ["python", "python3"]:
                        command = python_exe_str

                    # Get cwd, replace ${workspaceFolder} with actual path
                    cwd = server_config.get("cwd", project_path_str)
                    if "${workspaceFolder}" in cwd:
                        cwd = cwd.replace("${workspaceFolder}", project_path_str)

                    # Get environment variables and substitute ${VAR_NAME} patterns
                    raw_env_strs = {
                        k: str(v)
                        for k, v in (server_config.get("env") or {}).items()
                        if not k.startswith("_")
                    }
                    # Deny-by-default child environment: the SDK's
                    # safe-to-inherit names plus the CA bundle, then only what
                    # this server's own config declares or explicitly opts into
                    # below. The backend's process environment — JWT_SECRET_KEY,
                    # AGENT_INTERNAL_TOKEN, POSTGRES_*, integration tokens — does
                    # not pass through: one compromised community package must
                    # not equal full-platform compromise. Vigil's own tools run
                    # in-process and read the DB there, so no shipped entry
                    # needs database variables.
                    env = {
                        **default_child_env(),
                        # An mcp-config.json entry may refer to ${VIGIL_DIR}; unset, it
                        # would substitute to "" and root child paths at "/".
                        "VIGIL_DIR": str(vigil_path()),
                        "PYTHONPATH": project_path_str,
                    }
                    raw_args = list(server_config.get("args") or [])

                    # Capture declared credential placeholders *before*
                    # substitution collapses missing vars to empty strings
                    # — used by mcp_client to short-circuit connect when
                    # required credentials aren't set.
                    required_env_vars = extract_required_env_vars(
                        raw_env_strs, raw_args
                    )

                    # Explicit per-server opt-in (required_env_vars in the
                    # entry) plus every name the entry's own placeholders
                    # reference: those are forwarded from the backend
                    # environment or the secret store, so declared
                    # substitution below can see them. The store fallback
                    # mirrors the dormancy gate — a credential may live in
                    # secrets.enc instead of an export. Anything the config
                    # neither names nor lists stays out: the deny-by-default
                    # boundary above is not a hole for whatever else happens
                    # to be exported.
                    explicit_opt_ins = list(
                        server_config.get("required_env_vars") or []
                    )
                    opt_in_names: set[str] = set()
                    for var in explicit_opt_ins + required_env_vars:
                        if var in env:
                            continue
                        value = resolve_opt_in(var)
                        if value:
                            env[var] = value
                            opt_in_names.add(var)

                    # Declared config env is substituted against this reduced
                    # environment — now including the opted-in names — not
                    # os.environ; unset names fall through to the secret
                    # store, never to a wholesale env copy.
                    env.update(
                        {
                            k: self._substitute_env_vars(v, env)
                            for k, v in raw_env_strs.items()
                        }
                    )
                    # A name the env block declares is part of the declared
                    # environment, not an ambient opt-in: docker-style "-e
                    # KEY=value" argv interpolation depends on it (see the
                    # okta entry). Only purely opt-in names stay out of argv
                    # interpolation.
                    opt_in_names -= set(raw_env_strs)

                    # argv interpolation is the public channel: it sees the
                    # declared environment but never the ambient opt-ins, so
                    # an opt-in-only credential stays a literal ${VAR} in args
                    # for the child to expand from its own environment (E3 —
                    # see the loglm entry in mcp-config.json).
                    public_env = {k: v for k, v in env.items() if k not in opt_in_names}
                    args = [
                        self._substitute_public_value(arg, public_env)
                        for arg in raw_args
                    ]

                    # Launch the image's baked copy of a pinned npx/uvx entry
                    # instead of downloading it; anything not baked is as declared.
                    command, args = installed_launch(command, args)

                    server_configs.append(
                        {
                            "name": server_name,
                            "command": command,
                            "args": args,
                            "cwd": cwd,
                            "env": env,
                            "required_env_vars": required_env_vars,
                        }
                    )

                logger.info(
                    f"Loaded {len(server_configs)} servers from mcp-config.json"
                )
            except Exception as e:
                logger.error(f"Error loading mcp-config.json: {e}")
                server_configs = []
        else:
            logger.warning("mcp-config.json not found")
            server_configs = []

        # Dynamically update security-detections server env vars from DetectionRulesService
        for config in server_configs:
            if config["name"] == "security-detections":
                config = self._enrich_security_detections_env(config)
            server = MCPServer(**config)
            self.servers[config["name"]] = server

    def _enrich_security_detections_env(self, config: Dict) -> Dict:
        """
        Enrich the security-detections MCP server config with dynamic env vars
        from DetectionRulesService. This allows the MCP server to pick up
        newly added/removed rule sources without manual config editing.
        """
        try:
            dynamic_env = self._detection_rules.get_mcp_env_vars()

            if dynamic_env:
                # Override static env vars with dynamic ones
                config["env"] = config.get("env", {}).copy()
                config["env"].update(dynamic_env)
                logger.info(
                    f"Enriched security-detections env with {len(dynamic_env)} dynamic vars: {list(dynamic_env.keys())}"
                )
            else:
                logger.info(
                    "No dynamic env vars from DetectionRulesService (no ready sources)"
                )
        except Exception as e:
            logger.warning(f"Could not enrich security-detections env vars: {e}")

        return config

    def list_servers(self) -> List[str]:
        """
        List all available servers.

        Returns:
            List of server names.
        """
        return list(self.servers.keys())
