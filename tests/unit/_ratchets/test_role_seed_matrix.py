"""Every system role carries the RBAC refactor's permission matrix, thrice.

The five-role seed lives in three places that must not drift: the INSERT in
``infra/database/init/06_auth_tables.sql`` (initdb and
``scripts/seed_reference_data.py``), the same INSERT in
``scripts/init_roles.py``, and the chart's bundled copy under
``infra/helm/vigil/files/database-init/`` -- CI diffs the directories, so a
drift there fails only after a push. The seeds add new permissions with
``ON CONFLICT (role_id) DO NOTHING``, which never touches a role that already
exists -- so they also carry an upgrade merge that adds the new keys to
existing system roles; without it a gate naming a new permission would deny
every user on an upgraded deployment. This pins the matrix, the agreement
between the sites, and both idempotency mechanisms.
"""

import json
import re
from pathlib import Path

import pytest

from core.auth import auth_service
from core.auth.auth_service import AuthService

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
ROLE_SEEDS = REPO / "scripts" / "init_roles.py"
AUTH_SQL = REPO / "infra" / "database" / "init" / "06_auth_tables.sql"
# The chart bundles a byte-identical copy: Helm can only read files inside the
# chart directory, and drift here would ship the chart a different schema than
# the compose stack (CI's "Verify db-init SQL copies are in sync" step).
CHART_SQL = REPO / "infra" / "helm" / "vigil" / "files" / "database-init" / "06_auth_tables.sql"
SEED_SITES = (ROLE_SEEDS, AUTH_SQL, CHART_SQL)

# The RBAC refactor's additions, per role (the blueprint's matrix):
# viewer holds none of the tool-plane three; analysts get invoke + use;
# manager and admin get all five.
ADDITIONS = {
    "role-viewer": {
        "detections.read": False,
        "detections.write": False,
        "tools.invoke": False,
        "mcp.use": False,
        "mcp.admin": False,
    },
    "role-analyst": {
        "detections.read": False,
        "detections.write": False,
        "tools.invoke": True,
        "mcp.use": True,
        "mcp.admin": False,
    },
    "role-senior-analyst": {
        "detections.read": False,
        "detections.write": False,
        "tools.invoke": True,
        "mcp.use": True,
        "mcp.admin": False,
    },
    "role-manager": {
        "detections.read": True,
        "detections.write": True,
        "tools.invoke": True,
        "mcp.use": True,
        "mcp.admin": True,
    },
    "role-admin": {
        "detections.read": True,
        "detections.write": True,
        "tools.invoke": True,
        "mcp.use": True,
        "mcp.admin": True,
    },
}

# The seeded JSON blocks are flat maps, so the first } closes the object.
_ROLE_INSERT_RE = re.compile(
    r"\('(role-[a-z-]+)', '[^']*', '[^']*', '(\{.*?\})', (?:true|false)\)",
    re.DOTALL,
)
_UPGRADE_MERGE_RE = re.compile(
    r"UPDATE roles SET permissions = permissions \|\| '(\{.*?\})'::jsonb"
    r"\s+WHERE role_id = '(role-[a-z-]+)' AND is_system_role",
    re.DOTALL,
)


def _seeded_roles(text: str) -> dict:
    roles = {}
    for role_id, permissions_json in _ROLE_INSERT_RE.findall(text):
        roles[role_id] = json.loads(permissions_json)
    return roles


def test_all_seed_sites_agree():
    seeded = [_seeded_roles(path.read_text(encoding="utf-8")) for path in SEED_SITES]
    assert all(site == seeded[0] for site in seeded[1:])


def test_all_five_roles_are_seeded():
    assert set(ADDITIONS) <= set(_seeded_roles(ROLE_SEEDS.read_text(encoding="utf-8")))


def test_every_role_carries_the_specd_matrix():
    roles = _seeded_roles(ROLE_SEEDS.read_text(encoding="utf-8"))
    for role_id, expected in ADDITIONS.items():
        seeded = {key: roles[role_id][key] for key in expected}
        assert seeded == expected, f"{role_id} diverges from the spec'd matrix"


def test_the_seeded_upgrade_merge_carries_the_same_matrix():
    text = AUTH_SQL.read_text(encoding="utf-8")
    merges = {
        role_id: json.loads(permissions_json)
        for permissions_json, role_id in _UPGRADE_MERGE_RE.findall(text)
    }
    assert merges == ADDITIONS


def test_every_seed_site_is_idempotent():
    for path in SEED_SITES:
        text = path.read_text(encoding="utf-8")
        assert "ON CONFLICT (role_id) DO NOTHING" in text, path
        # One upgrade merge per role: re-running restamps the same canonical
        # values, never a second copy of a key.
        assert len(_UPGRADE_MERGE_RE.findall(text)) == len(ADDITIONS), path


def test_no_seed_names_a_permission_the_vocabulary_lacks(monkeypatch):
    monkeypatch.setattr(auth_service, "_is_dev_mode", lambda: True)
    vocabulary = set(AuthService.get_user_permissions("no-such-user"))
    roles = _seeded_roles(ROLE_SEEDS.read_text(encoding="utf-8"))
    unknown = {
        key for permissions in roles.values() for key in permissions
    } - vocabulary
    assert not unknown


def test_the_admin_seed_equals_the_whole_vocabulary(monkeypatch):
    monkeypatch.setattr(auth_service, "_is_dev_mode", lambda: True)
    vocabulary = AuthService.get_user_permissions("no-such-user")
    roles = _seeded_roles(ROLE_SEEDS.read_text(encoding="utf-8"))
    assert roles["role-admin"] == vocabulary
