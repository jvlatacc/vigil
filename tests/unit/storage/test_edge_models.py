"""The edge models match the init SQL that compose and Helm install from.

compose builds edge_nodes / edge_policies / edge_journal_receipts from
``infra/database/init/40..42`` and never from ``create_all`` (the tables
already exist by then), while a dev database built through the storage_status
"create schema" endpoint gets them from these models alone. A column the SQL
has and the model lacks — or the reverse — ships a schema that disagrees with
itself depending on which path built it. The index direction is ratcheted
globally by ``tests/unit/_ratchets/test_init_sql_model_indexes.py``; this file
pins columns, primary keys, and check-constraint names per table.
"""

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

from core.storage.models import (
    EDGE_NODE_STATUSES,
    EDGE_POLICY_STATUSES,
    Base,
    EdgeJournalReceipt,
    EdgeNode,
    EdgePolicy,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
INIT_SQL = REPO / "infra" / "database" / "init"

EDGE_SQL_FILES = {
    "edge_nodes": "40_edge_nodes.sql",
    "edge_policies": "41_edge_policies.sql",
    "edge_journal_receipts": "42_edge_journal_receipts.sql",
}

EDGE_TABLES = {
    "edge_nodes": EdgeNode,
    "edge_policies": EdgePolicy,
    "edge_journal_receipts": EdgeJournalReceipt,
}

# Table-level clauses that are not column definitions when a body is split.
_TABLE_LEVEL = {"CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK"}


def _body(sql: str, table: str) -> str:
    """Inside the parentheses of ``CREATE TABLE IF NOT EXISTS <table> (…)``."""
    match = re.search(rf"CREATE TABLE IF NOT EXISTS {table}\s*\(", sql)
    assert match, f"{table}: no CREATE TABLE in the init SQL"
    depth = 0
    for position in range(match.end() - 1, len(sql)):
        if sql[position] == "(":
            depth += 1
        elif sql[position] == ")":
            depth -= 1
            if depth == 0:
                return sql[match.end() : position]
    raise AssertionError(f"{table}: unbalanced parentheses in the init SQL")


def _split_top_level(body: str) -> List[str]:
    """Split on commas outside parentheses and single-quoted strings."""
    parts: List[str] = []
    depth = 0
    quoted = False
    current: List[str] = []
    for character in body:
        if quoted:
            current.append(character)
            if character == "'":
                quoted = False
            continue
        if character == "'":
            quoted = True
            current.append(character)
        elif character == "(":
            depth += 1
            current.append(character)
        elif character == ")":
            depth -= 1
            current.append(character)
        elif character == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
    if "".join(current).strip():
        parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _parse_table(table: str) -> Tuple[Dict[str, bool], Set[str], Set[str]]:
    """(nullable by column, primary-key columns, check-constraint names) as
    the init SQL declares them."""
    sql = re.sub(
        r"--[^\n]*",
        "",
        (INIT_SQL / EDGE_SQL_FILES[table]).read_text(encoding="utf-8"),
    )
    body = _body(sql, table)
    nullable: Dict[str, bool] = {}
    primary_keys: Set[str] = set()
    constraints: Set[str] = set()
    for fragment in _split_top_level(body):
        first = fragment.split()[0].strip('"')
        if first.upper() in _TABLE_LEVEL:
            constraint = re.match(r"CONSTRAINT (\w+)", fragment)
            if constraint:
                constraints.add(constraint.group(1))
            primary = re.match(r"PRIMARY KEY \(([^)]+)\)", fragment)
            if primary:
                primary_keys.update(
                    column.strip().strip('"') for column in primary.group(1).split(",")
                )
            continue
        is_pk = "PRIMARY KEY" in fragment
        nullable[first] = "NOT NULL" not in fragment and not is_pk
        if is_pk:
            primary_keys.add(first)
    return nullable, primary_keys, constraints


def _sql_index_names(table: str) -> Set[str]:
    sql = re.sub(
        r"--[^\n]*",
        "",
        (INIT_SQL / EDGE_SQL_FILES[table]).read_text(encoding="utf-8"),
    )
    return set(re.findall(r"CREATE (?:UNIQUE )?INDEX (?:IF NOT EXISTS )?(\w+)", sql))


def test_edge_models_import_from_the_models_package():
    for model in (EdgeNode, EdgePolicy, EdgeJournalReceipt):
        assert (
            model.__tablename__ in Base.metadata.tables
        ), f"{model.__name__} is not registered on Base.metadata"
        assert Base.metadata.tables[model.__tablename__] is model.__table__
    assert EdgeNode.__tablename__ == "edge_nodes"
    assert EdgePolicy.__tablename__ == "edge_policies"
    assert EdgeJournalReceipt.__tablename__ == "edge_journal_receipts"
    import core.storage.models as models_package

    for name in ("EdgeNode", "EdgePolicy", "EdgeJournalReceipt"):
        assert name in models_package.__all__


def test_model_columns_match_the_init_sql():
    for table, model in EDGE_TABLES.items():
        sql_nullable, sql_pks, _ = _parse_table(table)
        model_columns = model.__table__.columns
        assert set(model_columns.keys()) == set(sql_nullable), (
            f"{table}: model columns {sorted(model_columns.keys())} disagree "
            f"with init SQL columns {sorted(sql_nullable)}"
        )
        for column in model_columns:
            assert column.nullable == sql_nullable[column.name], (
                f"{table}.{column.name}: model nullable={column.nullable}, "
                f"SQL nullable={sql_nullable[column.name]}"
            )
        model_pks = {c.name for c in model.__table__.primary_key}
        assert model_pks == sql_pks, (
            f"{table}: model primary key {sorted(model_pks)} disagrees with "
            f"init SQL {sorted(sql_pks)}"
        )


def test_model_check_constraints_match_the_init_sql():
    for table, model in EDGE_TABLES.items():
        _, _, sql_constraints = _parse_table(table)
        model_constraints = {
            c.name
            for c in model.__table__.constraints
            if c.name and c.name.startswith("ck_")
        }
        assert model_constraints == sql_constraints, (
            f"{table}: model check constraints {sorted(model_constraints)} "
            f"disagree with init SQL {sorted(sql_constraints)}"
        )


def test_model_indexes_match_the_init_sql():
    for table, model in EDGE_TABLES.items():
        sql_indexes = _sql_index_names(table)
        model_indexes = {i.name for i in model.__table__.indexes}
        assert model_indexes == sql_indexes, (
            f"{table}: model indexes {sorted(model_indexes)} disagree with "
            f"init SQL {sorted(sql_indexes)}"
        )


def test_status_vocabulary_matches_the_check_constraints():
    assert EDGE_NODE_STATUSES == ("active", "revoked")
    assert EDGE_POLICY_STATUSES == ("draft", "active", "revoked")
