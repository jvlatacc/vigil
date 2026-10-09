"""The permission vocabulary is pinned at 21 names, and dev mode grants all.

``AuthService.get_user_permissions``'s DEV_MODE map is the only place the
vocabulary is written out whole: the route ratchet names one permission per
route and the role seeds name several per role, but nothing else enumerates
the set. A permission that joins the engine must join that map or dev-mode
tooling and anything consuming the permissions payload silently disagree
with production about what exists. The RBAC additions (detections domain,
tool plane) join here deliberately, in step with the seeds.
"""

import pytest

from core.auth import auth_service
from core.auth.auth_service import AuthService

pytestmark = pytest.mark.unit

VOCABULARY = {
    # findings
    "findings.read",
    "findings.write",
    "findings.delete",
    # cases
    "cases.read",
    "cases.write",
    "cases.delete",
    "cases.assign",
    # detections (RBAC refactor)
    "detections.read",
    "detections.write",
    # integrations
    "integrations.read",
    "integrations.write",
    # users
    "users.read",
    "users.write",
    "users.delete",
    # settings
    "settings.read",
    "settings.write",
    # chat and the tool plane (RBAC refactor)
    "ai_chat.use",
    "tools.invoke",
    "mcp.use",
    "mcp.admin",
    # decisions
    "ai_decisions.approve",
}
def _dev_mode_permissions(monkeypatch) -> dict:
    # Patch the module-level helper, not Settings: conftest forces DEV_MODE off
    # for the whole suite, and the DEV_MODE branch answers before any database
    # is touched, so no store is needed.
    monkeypatch.setattr(auth_service, "_is_dev_mode", lambda: True)
    return AuthService.get_user_permissions("no-such-user")


def test_dev_mode_map_is_the_whole_vocabulary(monkeypatch):
    permissions = _dev_mode_permissions(monkeypatch)
    assert set(permissions) == VOCABULARY
    assert all(permissions.values())

