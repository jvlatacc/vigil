"""Edge migration ratchet: up and down must both be clean.

The init SQL files carry an embedded ``-- down:`` statement per file (the
convention this suite pins). These tests execute the up statements, exercise
the ORM against the result, then run the down statements and assert the
tables are gone — and that up is repeatable. If a future edit breaks the
down path, or adds a column the ORM does not know, this suite fails before
an operator ever finds out mid-rollback.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import text

from core.storage.connection import get_db_manager
from core.storage.models import EdgeBundle, EdgeNode

pytestmark = pytest.mark.external_service

REPO_ROOT = Path(__file__).resolve().parents[3]

EDGE_NODE_ID = "gw-test-01"


@pytest.fixture(autouse=True)
def _restore_orm_schema():
    """This suite deliberately drops tables to prove `down` works; give the
    session-scoped throwaway database its ORM schema back after each test
    (create_all is idempotent — it only builds what is missing)."""
    yield
    get_db_manager().create_tables()


def _parse_migration(filename: str) -> tuple[list[str], list[str]]:
    """Split an init SQL file into up statements and its ``-- down:`` ones."""
    path = REPO_ROOT / "infra" / "database" / "init" / filename
    down_statements: list[str] = []
    up_lines: list[str] = []
    for line in path.read_text().splitlines():
        match = re.match(r"^--\s*down:\s*(.+)$", line.strip())
        if match:
            down_statements.append(match.group(1).strip())
        else:
            up_lines.append(line)
    up_sql = re.sub(r"--[^\n]*", "", "\n".join(up_lines))
    up_statements = [s.strip() for s in up_sql.split(";") if s.strip()]
    return up_statements, down_statements


def _run(manager, statements: list[str]) -> None:
    with manager.engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def _table_exists(manager, table: str) -> bool:
    with manager.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :t)"
            ),
            {"t": table},
        ).scalar()
    return bool(row)


def _columns(manager, table: str) -> set[str]:
    with manager.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t"
            ),
            {"t": table},
        ).fetchall()
    return {r[0] for r in rows}


class TestEdgeNodesMigration:
    def test_up_creates_schema_the_orm_declares(self):
        manager = get_db_manager()
        up, _ = _parse_migration("40_edge_nodes.sql")
        _run(manager, ["DROP TABLE IF EXISTS edge_nodes"])
        try:
            _run(manager, up)
            assert _table_exists(manager, "edge_nodes")
            columns = _columns(manager, "edge_nodes")
            expected = {
                "node_id",
                "segment_scope",
                "credential_hash",
                "status",
                "enrolled_at",
                "last_seen",
                "last_boot_id",
                "last_bundle_version",
                "revoked_at",
                "revoked_by",
                "revoke_reason",
            }
            missing = expected - columns
            assert not missing, f"migration is missing ORM columns: {missing}"
        finally:
            _run(manager, ["DROP TABLE IF EXISTS edge_nodes"])

    def test_orm_round_trip_on_migrated_table(self):
        manager = get_db_manager()
        up, down = _parse_migration("40_edge_nodes.sql")
        _run(manager, down)
        try:
            _run(manager, up)
            with manager.session_scope() as session:
                node = EdgeNode(
                    node_id=EDGE_NODE_ID,
                    segment_scope={"vpc": "vpc-1", "cidrs": ["10.42.0.0/16"]},
                    credential_hash="a" * 64,
                )
                session.add(node)
            with manager.session_scope() as session:
                row = session.get(EdgeNode, EDGE_NODE_ID)
                assert row is not None
                assert dict(row.segment_scope)["vpc"] == "vpc-1"
                assert row.status == "active"
            # Upsert path: re-enroll updates the same row.
            with manager.session_scope() as session:
                row = session.get(EdgeNode, EDGE_NODE_ID)
                row.credential_hash = "b" * 64
                row.status = "revoked"
                row.revoked_at = row.enrolled_at
            with manager.session_scope() as session:
                assert session.query(EdgeNode).count() == 1
        finally:
            _run(manager, down)

    def test_down_drops_and_up_is_repeatable(self):
        manager = get_db_manager()
        up, down = _parse_migration("40_edge_nodes.sql")
        _run(manager, up)
        _run(manager, down)
        assert not _table_exists(manager, "edge_nodes")
        _run(manager, up)
        assert _table_exists(manager, "edge_nodes")
        _run(manager, down)
        assert not _table_exists(manager, "edge_nodes")

    def test_revocation_check_constraint_holds(self):
        manager = get_db_manager()
        up, down = _parse_migration("40_edge_nodes.sql")
        _run(manager, down)
        try:
            _run(manager, up)
            with pytest.raises(Exception):
                with manager.engine.begin() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO edge_nodes (node_id, credential_hash, "
                            "status, revoked_at) VALUES ('x', 'h', 'revoked', NULL)"
                        )
                    )
        finally:
            _run(manager, down)


class TestEdgeBundlesMigration:
    def test_up_creates_composite_key_table(self):
        manager = get_db_manager()
        up, _ = _parse_migration("41_edge_bundles.sql")
        _run(manager, ["DROP TABLE IF EXISTS edge_bundles"])
        try:
            _run(manager, up)
            assert _table_exists(manager, "edge_bundles")
            columns = _columns(manager, "edge_bundles")
            assert {
                "bundle_id",
                "version",
                "segment_scope",
                "autonomy_tier",
                "envelope",
                "payload",
                "signed_at",
                "signed_by",
            } <= columns
        finally:
            _run(manager, ["DROP TABLE IF EXISTS edge_bundles"])

    def test_orm_round_trip_and_version_immutability_shape(self):
        manager = get_db_manager()
        up, down = _parse_migration("41_edge_bundles.sql")
        _run(manager, down)
        try:
            _run(manager, up)
            envelope = {"payloadType": "application/vnd.vigil.edge.bundle+json"}
            payload = {"bundle_id": "edge-pol-test", "version": 1}
            with manager.session_scope() as session:
                session.add(
                    EdgeBundle(
                        bundle_id="edge-pol-test",
                        version=1,
                        segment_scope={"vpc": "vpc-1"},
                        autonomy_tier="tier2",
                        envelope=envelope,
                        payload=payload,
                        signed_by="test",
                    )
                )
            with manager.session_scope() as session:
                row = (
                    session.query(EdgeBundle)
                    .filter(EdgeBundle.bundle_id == "edge-pol-test")
                    .one()
                )
                assert row.payload["version"] == 1
                assert row.autonomy_tier == "tier2"
            # Same id, new version = a new row; the old one never changes.
            with manager.session_scope() as session:
                session.add(
                    EdgeBundle(
                        bundle_id="edge-pol-test",
                        version=2,
                        segment_scope={"vpc": "vpc-1"},
                        autonomy_tier="tier2",
                        envelope=envelope,
                        payload={"bundle_id": "edge-pol-test", "version": 2},
                        signed_by="test",
                    )
                )
            with manager.session_scope() as session:
                versions = [
                    r.version
                    for r in session.query(EdgeBundle)
                    .filter(EdgeBundle.bundle_id == "edge-pol-test")
                    .order_by(EdgeBundle.version)
                ]
                assert versions == [1, 2]
        finally:
            _run(manager, down)

    def test_down_drops_and_up_is_repeatable(self):
        manager = get_db_manager()
        up, down = _parse_migration("41_edge_bundles.sql")
        _run(manager, up)
        _run(manager, down)
        assert not _table_exists(manager, "edge_bundles")
