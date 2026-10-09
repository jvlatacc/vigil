"""Compiled-policy ORM models: registration and parity with the init SQL.

The storage recipe makes the numbered SQL file and the ORM model two sources
of one schema; these tests keep the pair honest without a database.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint

from core.storage.models import (
    POLICY_MODES,
    POLICY_STATES,
    Base,
    CompiledPolicy,
    CompiledPolicyDecision,
)

pytestmark = pytest.mark.unit

SQL_FILE = (
    Path(__file__).resolve().parents[3]
    / "infra"
    / "database"
    / "init"
    / "40_compiled_policies.sql"
)


def _executable_sql() -> str:
    """The file without comment lines, so CHECK lists read as written."""
    return "\n".join(
        line
        for line in SQL_FILE.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    )


def _sql_create_block(sql: str, table: str) -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", sql, re.S)
    assert match is not None, f"{table} not found in the init SQL"
    return match.group(1)


def _sql_constraint_names(block: str) -> set[str]:
    return set(re.findall(r"CONSTRAINT (\w+)", block))


def _orm_constraint_names(model) -> set[str]:
    return {
        c.name
        for c in model.__table__.constraints
        if c.name and isinstance(c, (CheckConstraint, ForeignKeyConstraint))
    }


def test_both_models_register_on_the_metadata() -> None:
    assert CompiledPolicy.__table__.name == "compiled_policies"
    assert CompiledPolicyDecision.__table__.name == "compiled_policy_decisions"
    assert Base.metadata.tables["compiled_policies"] is CompiledPolicy.__table__
    assert (
        Base.metadata.tables["compiled_policy_decisions"]
        is CompiledPolicyDecision.__table__
    )


def test_orm_constraints_match_the_init_sql() -> None:
    sql = _executable_sql()
    for model, table in (
        (CompiledPolicy, "compiled_policies"),
        (CompiledPolicyDecision, "compiled_policy_decisions"),
    ):
        block = _sql_create_block(sql, table)
        sql_names = _sql_constraint_names(block)
        orm_names = _orm_constraint_names(model)
        assert orm_names == sql_names, (
            f"{table}: ORM and SQL disagree on named constraints — "
            f"ORM-only {sorted(orm_names - sql_names)}, "
            f"SQL-only {sorted(sql_names - orm_names)}"
        )


def test_orm_indexes_match_the_init_sql() -> None:
    sql = _executable_sql()
    sql_index_names = set(re.findall(r"CREATE INDEX IF NOT EXISTS (\w+)\s", sql))
    for model in (CompiledPolicy, CompiledPolicyDecision):
        orm_names = {i.name for i in model.__table__.indexes}
        assert orm_names <= sql_index_names, (
            f"{model.__table__.name}: model indexes the init SQL never creates "
            f"(create_all skips existing tables): {sorted(orm_names - sql_index_names)}"
        )


def test_vocabularies_match_the_sql_checks() -> None:
    sql = _executable_sql()
    state_list = re.search(
        r"state IN \((.*?)\)", _sql_create_block(sql, "compiled_policies"), re.S
    )
    assert state_list is not None
    sql_states = tuple(re.findall(r"'(\w+)'", state_list.group(1)))
    assert sql_states == POLICY_STATES

    decisions = _sql_create_block(sql, "compiled_policy_decisions")
    mode_list = re.search(r"mode IN \((.*?)\)", decisions, re.S)
    assert mode_list is not None
    assert tuple(re.findall(r"'(\w+)'", mode_list.group(1))) == POLICY_MODES


def test_decision_fks_cascade_findings_and_restrict_policies() -> None:
    fks = {
        c.name: c
        for c in CompiledPolicyDecision.__table__.constraints
        if isinstance(c, ForeignKeyConstraint)
    }
    finding_fk = fks["fk_compiled_policy_decisions_finding"]
    assert finding_fk.columns.keys() == ["finding_id"]
    assert finding_fk.ondelete == "CASCADE"

    policy_fk = fks["fk_compiled_policy_decisions_policy"]
    assert policy_fk.columns.keys() == ["policy_id", "policy_version"]
    assert policy_fk.ondelete == "RESTRICT"
    assert policy_fk.referred_table.name == "compiled_policies"
