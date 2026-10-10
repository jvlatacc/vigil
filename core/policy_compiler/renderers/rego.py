"""Rego renderer: the full predicate tree as a loadable OPA module.

The one renderer that expresses every match clause. Its semantics mirror
core/policy_compiler/evaluator.py exactly — including the fail-closed edges
(a missing input field makes the clause undefined, which makes the body
false, which is the evaluator's "no match") — so an OPA deployment that
loads this module and feeds it findings decides as Vigil would. Emitted in
OPA v1 syntax; needs an OPA release that parses it (>= 0.63).
"""

from __future__ import annotations

from core.policy_compiler.models import (
    ENTITY_CONTEXT_TYPE_BY_KEY,
    EntityTypeSet,
    PolicyIR,
    TechniqueSet,
)
from core.policy_compiler.renderers._common import provenance_header


def render_rego(policy: PolicyIR) -> str:
    body = _policy_rule(policy)
    helpers = _non_empty_helper() if policy.match.entity_context_types else ""
    header = provenance_header(policy, tool="OPA (Rego v1)")
    module = f"{header}\n\npackage vigil.compiled_policies\n\n{body}"
    if helpers:
        module = f"{module}\n\n{helpers}"
    return module + "\n"


def _policy_rule(policy: PolicyIR) -> str:
    conjuncts = ["not workflow_mismatch"]
    clauses = [
        f'workflow_mismatch if {{\n\tinput.workflow_id != "{policy.match.workflow_id}"\n}}'
    ]

    if policy.match.data_source is not None:
        for source in policy.match.data_source:
            clauses.append(
                f'data_source_matches if {{\n\tinput.data_source == "{source}"\n}}'
            )
        conjuncts.append("data_source_matches")

    techniques = policy.match.techniques
    if techniques is not None:
        conjuncts.extend(_technique_conjuncts(techniques, clauses))

    types = policy.match.entity_context_types
    if types is not None:
        conjuncts.extend(_type_conjuncts(types, clauses))

    rule_body = "\n".join(f"\t{conjunct}" for conjunct in conjuncts)
    parts = ["default policy_match := false", f"policy_match if {{\n{rule_body}\n}}"]
    parts.extend(clauses)
    return "\n\n".join(parts)


def _technique_conjuncts(techniques: TechniqueSet, clauses: list[str]) -> list[str]:
    """any_of becomes a disjunctive hit rule; all_of a conjunctive one."""
    conjuncts: list[str] = []
    if techniques.any_of:
        for technique in techniques.any_of:
            clauses.append(
                "techniques_any_of_hit if {\n"
                "\tis_object(input.mitre_predictions)\n"
                f'\tinput.mitre_predictions["{technique}"]\n'
                "}"
            )
        conjuncts.append("techniques_any_of_hit")
    if techniques.all_of:
        conditions = [
            f'input.mitre_predictions["{technique}"]' for technique in techniques.all_of
        ]
        clauses.append(
            "techniques_all_of_present if {\n"
            "\tis_object(input.mitre_predictions)\n"
            + "\n".join(f"\t{condition}" for condition in conditions)
            + "\n}"
        )
        conjuncts.append("techniques_all_of_present")
    return conjuncts


def _type_conjuncts(types: EntityTypeSet, clauses: list[str]) -> list[str]:
    """Entity TYPES are matched through their source KEY aliases.

    The daemon writes plural keys (src_ips); legacy singular keys are read
    too — the emitted rule tries every alias per type, mirroring
    ENTITY_CONTEXT_TYPE_BY_KEY in reverse. A missing or empty alias value is
    undefined/false in the body, which is the evaluator's fail-closed edge.
    """
    aliases: dict[str, list[str]] = {}
    for key, type_ in ENTITY_CONTEXT_TYPE_BY_KEY.items():
        aliases.setdefault(type_, []).append(key)

    conjuncts: list[str] = []
    if types.any_of:
        for type_ in types.any_of:
            for key in aliases.get(type_, [type_]):
                clauses.append(_type_present_rule(f"types_any_of_{type_}", key))
            conjuncts.append(f"types_any_of_{type_}")
    if types.all_of:
        for type_ in types.all_of:
            for key in aliases.get(type_, [type_]):
                clauses.append(_type_present_rule(f"type_present_{type_}", key))
            conjuncts.append(f"type_present_{type_}")
    return conjuncts


def _type_present_rule(rule_name: str, key: str) -> str:
    return (
        f"{rule_name} if {{\n"
        "\tis_object(input.entity_context)\n"
        f'\tnon_empty(input.entity_context["{key}"])\n'
        "}"
    )


def _non_empty_helper() -> str:
    return (
        "non_empty(value) if {\n\tis_array(value)\n\tcount(value) > 0\n}\n"
        '\nnon_empty(value) if {\n\tis_string(value)\n\tvalue != ""\n}\n'
        "\nnon_empty(value) if {\n\tis_object(value)\n\tcount(value) > 0\n}"
    )
