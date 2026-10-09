"""Tool risk: the direct-action taxonomy and the one gate that reads it.

Direct-action verbs make an MCP tool name destructive: calling it changes the
world (isolates a host, blocks an IP, kills a process) and a later read cannot
undo it. Three surfaces read the same predicate here so a new verb tightens
all of them at once:

- chat removes the tools from its reachable set (``chat_layers``) — it has no
  approval-resume path, so it recommends rather than detonates;
- the agent invoke boundary (``core.agents.tools_router``) refuses the call
  outright when no person is bound to it, unless the operator allow-listed
  the tool in ``response.tool_risk_overrides``;
- a workflow phase grant (``playbook_resolver``) drops the name rather than
  arming a call that would die at the gate.

A person is the API-signed principal on the call — never a model's confidence
(see the anti-spoofing rails on the approval queue). The allow-list is the
operator's per-tool escape hatch for teams who want direct agent action; it
never loosens chat, whose exclusion is its own decision.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional, Tuple

from core.integrations.atomic_red_team.descriptor import EXECUTE_IDS
from core.response.config import ResponseConfig, decision_rule

logger = logging.getLogger(__name__)

# Direct-action verbs that make an MCP tool destructive. Read by every
# surface above; kept in one place so they cannot drift apart.
DESTRUCTIVE_VERBS = frozenset(
    {
        "isolate",
        "unisolate",
        "contain",
        "quarantine",
        "block",
        "unblock",
        "kill",
        "terminate",
        "shutdown",
        "disable",
        "deactivate",
        "suspend",
        "delete",
        "remove",
        "purge",
        "wipe",
        "revoke",
        "ban",
        "remediate",
        "detonate",
        "reset",
        "release",
    }
)
# A read-only lead verb (get_isolation_status, list_blocked_ips) is safe even
# when a destructive noun follows, so it overrides the verb check.
READONLY_LEADS = frozenset(
    {
        "get",
        "list",
        "search",
        "describe",
        "fetch",
        "query",
        "show",
        "read",
        "lookup",
        "count",
        "stats",
        "status",
        "check",
    }
)


def is_destructive_mcp(name: str) -> bool:
    """True for a server-prefixed MCP tool that performs an irreversible action.

    Every token of the id is read, the server prefix included. Vendor tools
    arrive as ``{server}_{tool}`` and Vigil's own arrive bare, so there is no
    one prefix to strip — and stripping the first token off a bare name takes
    the verb, which is the whole of what this decides on: ``isolate_host``
    would be read as ``host``.

    A read-only lead verb wins outright; otherwise any destructive verb token
    marks it. Reading the prefix too can only over-drop, and that is the side to
    err on — a spurious drop means chat recommends the action instead of calling
    it, whereas a missed one is an ungated detonation.

    ART execute is named, not verb-matched: adding ``execute`` to the verb set
    would also drop ``splunk_execute``.
    """
    if name in EXECUTE_IDS:
        return True
    tokens = name.split("_")
    if not tokens:
        return False
    if tokens[0] in READONLY_LEADS:
        return False
    return any(tok in DESTRUCTIVE_VERBS for tok in tokens)


def destructive_refusal(
    tool: str,
    *,
    person_bound: bool,
    overrides: Iterable[str] = (),
) -> Optional[str]:
    """The #917 rule string when the invoke boundary must refuse this call.

    None means the call may run: the tool is not direct-action, a person is
    bound to it, or the operator allow-listed the name. Refusals are rendered
    through ``decision_rule`` like every other decision, so the failure a run
    records parses the same shape an approval row's reason does.
    """
    if not is_destructive_mcp(tool):
        return None
    if person_bound:
        return None
    if tool in overrides:
        return None
    return decision_rule("agent.tool_risk_no_person", tool)


def current_overrides() -> Tuple[str, ...]:
    """The operator's allow-list as the gate reads it, live per call.

    Env declares it (``DAEMON_TOOL_RISK_OVERRIDES``); ``ResponseConfig`` is the
    typed surface both the daemon's observe mode and this reader go through, so
    what is reported and what is enforced cannot drift. Fail-closed: a read
    that fails lists nothing — an unreadable setting must not read as an
    exemption, the same posture that holds containment on an unreadable
    protected-target read.
    """
    try:
        config = ResponseConfig.from_settings()
        return tuple(
            name.strip() for name in config.tool_risk_overrides if name.strip()
        )
    except Exception as exc:  # noqa: BLE001 - an unreadable setting exempts nothing
        logger.warning("tool_risk_overrides unreadable (%s); no tool is exempt", exc)
        return ()
