"""CLI tests: env handling, --since, and --output — no database required.

The connection and fetch seams are module-level functions, so tests substitute
them directly; the unreachable-database test uses a refused local port and no
fixture data at all.
"""

import json

import pytest

from vigilmap.export import export_memory


@pytest.fixture
def no_db_env(monkeypatch):
    for var in (
        "DATABASE_URL",
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)


def test_missing_env_exits_non_zero_with_message(no_db_env, tmp_path, capsys):
    code = export_memory.main(["--output", str(tmp_path / "memory.json")])
    assert code == 2
    captured = capsys.readouterr()
    assert "DATABASE_URL" in captured.err
    assert "PGHOST" in captured.err  # names the alternative spelling too
    assert not (tmp_path / "memory.json").exists()


def test_unreachable_db_exits_non_zero_with_message(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://nobody@127.0.0.1:1/vigil?connect_timeout=1"
    )
    code = export_memory.main(["--output", str(tmp_path / "memory.json")])
    assert code == 2
    assert "could not connect" in capsys.readouterr().err


def test_invalid_since_exits_non_zero_with_message(no_db_env, tmp_path, capsys):
    code = export_memory.main(
        ["--output", str(tmp_path / "memory.json"), "--since", "last week"]
    )
    assert code == 2
    assert "ISO-8601" in capsys.readouterr().err


def test_queries_carry_since_on_the_timestamped_tables_only():
    with_since = export_memory.queries("2026-09-01")
    assert len(with_since) == 4
    for sql, params in with_since[:3]:
        assert params == ("2026-09-01",)
        assert "concluded_at >= %(since)s::timestamptz" in sql
    # The sources table has no clock of its own; the transform prunes it.
    sources_sql, sources_params = with_since[3]
    assert sources_params == ()
    assert "concluded_at" not in sources_sql

    without = export_memory.queries(None)
    for sql, params in without[:3]:
        assert params == (None,)
        assert "%(since)s::timestamptz IS NULL" in sql


def test_since_is_passed_through_to_the_fetch(no_db_env, tmp_path, monkeypatch, rows):
    seen = {}

    def fake_fetch(conn, since=None):
        seen["since"] = since
        return rows

    monkeypatch.setattr(export_memory, "connect", lambda: object())
    monkeypatch.setattr(export_memory, "fetch_rows", fake_fetch)
    export_memory.main(
        ["--output", str(tmp_path / "memory.json"), "--since", "2026-09-01"]
    )
    assert seen["since"] == "2026-09-01T00:00:00"


def test_output_writes_a_valid_document(no_db_env, tmp_path, capsys, monkeypatch, rows):
    monkeypatch.setattr(export_memory, "connect", lambda: object())
    monkeypatch.setattr(export_memory, "fetch_rows", lambda conn, since=None: rows)

    output = tmp_path / "memory.json"
    code = export_memory.main(["--output", str(output)])

    assert code == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schemaVersion"] == 1
    assert document["source"] == "export"
    assert len(document["nodes"]) == 17
    assert len(document["links"]) == 18
    assert "17 nodes" in capsys.readouterr().out


def test_fetch_rows_names_cursor_columns():
    class FakeCursor:
        description = [("id",), ("entity_key",)]

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def execute(self, sql, params=None):
            self.result = [(7, "domain:evildomain.com")]

        def fetchall(self):
            return self.result

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    fetched = export_memory.fetch_rows(FakeConn(), since=None)
    assert fetched["sightings"] == [{"id": 7, "entity_key": "domain:evildomain.com"}]


def test_parse_since_accepts_date_and_timestamp():
    assert export_memory._parse_since("2026-09-01") == "2026-09-01T00:00:00"
    assert (
        export_memory._parse_since("2026-09-01T14:00:00+00:00")
        == "2026-09-01T14:00:00+00:00"
    )
    assert export_memory._parse_since(None) is None
    assert export_memory._parse_since("") is None
