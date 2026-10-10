#!/usr/bin/env python3
"""Standalone episodic-memory exporter.

Reads Vigil's episodic memory — the tables in
``infra/database/init/26_episodic_memory.sql`` plus the verdict techniques
column from ``33_episodic_verdict_techniques.sql`` — and writes one
``MemoryGraphDocument``: the JSON shape vigilmap renders.

Connection is environment-only: ``DATABASE_URL``, or the standard ``PG*``
variables (psycopg2/libpq reads them itself). The app never connects to
anything; the read path in Vigil (per-key caps, read logging) is untouched.

``rows_to_document`` is the contract transform and is pure: row dicts in,
document out, no database, no ``core`` import, no I/O on that path.

Deliberately unread: ``episodic_distil_markers``. It is Distil bookkeeping
(counts, run ids) and the document contract has no node kind for it — emitting
it would invent vocabulary the app's validator rejects. Hunts are derived from
verdict and gap investigations; the ``episode`` kind stays sample-data-only
(spec art_ZBtJZ5HK, open question), which is what keeps this an exporter and
not a second distil.

The entity-key rule is THE one rule (``core/memory/entity_keys.py``): defang,
then case-fold, except ``arn``/``aws_key``. Stored keys are re-minted on the
way out (``normalise_key``) so a defanged stored variant still joins the
entity it was written for. ``key_rule.py`` is this module's only statement of
the rule.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:  # package use: from vigilmap.export import export_memory
    from .key_rule import ENTITY_KEY_TYPES, normalise_key
except ImportError:  # direct: python vigilmap/export/export_memory.py
    from key_rule import ENTITY_KEY_TYPES, normalise_key  # type: ignore[no-redef]

SCHEMA_VERSION = 1


class ExporterError(Exception):
    """A condition the operator can act on: bad env, bad --since, dead database."""


# --------------------------------------------------------------------------
# SQL. Four reads, each ordered by id so an export is a stable diff, not a
# shuffle. --since filters the three timestamped tables on concluded_at; the
# sources table has no clock of its own, and the transform only links sources
# to verdicts and sightings it actually emitted, so nothing dangles.
# --------------------------------------------------------------------------

_SIGHTINGS_SQL = """
    SELECT id, entity_key, investigation_kind, investigation_id, source_system,
           first_seen, last_seen, concluded_at
    FROM episodic_sightings
    WHERE (%(since)s::timestamptz IS NULL OR concluded_at >= %(since)s::timestamptz)
    ORDER BY id
"""

_VERDICTS_SQL = """
    SELECT id, investigation_kind, investigation_id, statement, outcome,
           rationale, subject_entities, first_seen, concluded_at, techniques
    FROM episodic_verdicts
    WHERE (%(since)s::timestamptz IS NULL OR concluded_at >= %(since)s::timestamptz)
    ORDER BY id
"""

_GAPS_SQL = """
    SELECT id, investigation_kind, investigation_id, statement, disposition,
           reason, subject_entities, concluded_at
    FROM episodic_gaps
    WHERE (%(since)s::timestamptz IS NULL OR concluded_at >= %(since)s::timestamptz)
    ORDER BY id
"""

_SOURCES_SQL = """
    SELECT verdict_id, source_system, stance, source_tier
    FROM episodic_verdict_sources
    ORDER BY verdict_id, source_system
"""


def queries(since: Optional[str]) -> Sequence[Tuple[str, Tuple[Any, ...]]]:
    """The four reads as (sql, params); ``since`` as an ISO-8601 string or None."""
    return [
        (_SIGHTINGS_SQL, (since,)),
        (_VERDICTS_SQL, (since,)),
        (_GAPS_SQL, (since,)),
        (_SOURCES_SQL, ()),
    ]


# --------------------------------------------------------------------------
# The pure transform: row dicts -> MemoryGraphDocument.
# --------------------------------------------------------------------------


def _iso(value: Any) -> Optional[str]:
    """A timestamp as the ISO-8601 string the contract wants, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _investigation_id(kind: str, inv_id: str) -> str:
    """The one spelling for an investigation: it is the hunt node's id too."""
    return f"investigation:{kind}:{inv_id}"


def _truncated(text: str, cap: int = 64) -> str:
    return text if len(text) <= cap else text[: cap - 1] + "…"


def _entity_node(key: str, on_drop: Callable[[str], None]) -> Optional[Dict[str, Any]]:
    """Normalised entity node, or None when the key names no exportable type."""
    minted = normalise_key(key or "")
    if not minted:
        on_drop("empty-entity-key")
        return None
    kind, _, value = minted.partition(":")
    if kind not in ENTITY_KEY_TYPES:
        # A key minted outside the vocabulary is one no reader will ever
        # query; recall_contract calls it "an entity nobody has looked at".
        on_drop(f"unknown-entity-type:{kind}")
        return None
    return {
        "id": minted,
        "kind": "entity",
        "label": value,
        "entityType": kind,
        "entityKey": minted,
    }


def _sighting_node(row: Mapping[str, Any], entity_key_minted: str) -> Dict[str, Any]:
    return {
        "id": f"sighting-{row['id']}",
        "kind": "sighting",
        "label": f"sighting #{row['id']} · {row['source_system']}",
        "entityKey": entity_key_minted,
        "observedFrom": _iso(row["first_seen"]),
        "observedTo": _iso(row["last_seen"]),
        "investigationId": _investigation_id(
            row["investigation_kind"], row["investigation_id"]
        ),
        # No sourceTier: a sighting's window is observed by definition
        # (26_episodic_memory.sql), and the contract field is optional.
    }


def _verdict_node(row: Mapping[str, Any]) -> Dict[str, Any]:
    node: Dict[str, Any] = {
        "id": f"verdict-{row['id']}",
        "kind": "verdict",
        "label": _truncated(str(row["statement"])),
        "outcome": row["outcome"],
        "statement": str(row["statement"]),
        "investigationId": _investigation_id(
            row["investigation_kind"], row["investigation_id"]
        ),
        "concludedAt": _iso(row["concluded_at"]),
        # Technique ids are attributes on the verdict (33_*.sql), not nodes:
        # a technique is a label a verdict carries, not an actor in memory.
        "techniques": sorted({str(t) for t in (row.get("techniques") or [])}),
    }
    if row.get("rationale"):
        node["rationale"] = str(row["rationale"])
    return node


def _gap_node(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": f"gap-{row['id']}",
        "kind": "gap",
        "label": _truncated(str(row["statement"])),
        "disposition": row["disposition"],
        "reason": str(row["reason"]),
        "investigationId": _investigation_id(
            row["investigation_kind"], row["investigation_id"]
        ),
    }


def _to_dt(value: Any) -> Optional[datetime]:
    """Coerce a row timestamp (datetime or ISO string) to an aware datetime.

    Psycopg2 hands back datetimes for timestamptz columns, but the transform
    also runs over plain dicts (tests, fixtures, future callers) — so strings
    are first-class here. Naive values get UTC attached so min/max cannot
    TypeError across mixed sources.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _hunt_node(kind: str, inv_id: str, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """The context node for one investigation.

    Started from the earliest window its verdicts and gaps opened, ended at
    the last conclusion. Built from verdicts and gaps only: the link table
    gives a hunt nothing to anchor a sighting with, and a linkless hunt node
    is one the app would prune as an orphan.
    """
    started = [
        dt for dt in (_to_dt(r.get("first_seen")) for r in rows) if dt is not None
    ]
    ended = [
        dt for dt in (_to_dt(r.get("concluded_at")) for r in rows) if dt is not None
    ]
    return {
        "id": _investigation_id(kind, inv_id),
        "kind": "hunt",
        "label": f"{kind}: {inv_id}",
        "objective": f"{kind} investigation {inv_id}",
        "startedAt": _iso(min(started)) if started else None,
        "endedAt": _iso(max(ended)) if ended else None,
    }


def rows_to_document(
    sightings: List[Dict[str, Any]],
    verdicts: List[Dict[str, Any]],
    verdict_sources: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
    source: str,
    generated_at: str,
    on_drop: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Row dicts -> a validated-shape ``MemoryGraphDocument``.

    Pure: no database, no environment, no I/O. Links are emitted only between
    nodes this document actually carries, so no ``--since`` combination can
    produce a dangling link. ``on_drop`` (optional) receives a category per
    unusable key or unanchored row — the CLI reports the counts, tests assert
    them, and neither is silent.
    """
    drop: Callable[[str], None] = on_drop or (lambda _category: None)
    nodes: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    seen_links: set = set()

    def link(source_id: str, target_id: str, relation: str) -> None:
        marker = (source_id, target_id, relation)
        if marker not in seen_links:
            seen_links.add(marker)
            links.append(
                {"source": source_id, "target": target_id, "relation": relation}
            )

    # Entities first: every other node joins on them, so an entity that did
    # not survive the vocabulary filter takes its referencing rows with it.
    # None is cached as "dropped" so a repeated bad key is reported once.
    entity_nodes: Dict[str, Optional[Dict[str, Any]]] = {}

    def entity_for(key: str) -> Optional[Dict[str, Any]]:
        minted = normalise_key(key or "")
        if minted in entity_nodes:
            return entity_nodes[minted]
        # _entity_node owns the drop categories (empty key vs unknown type);
        # its None is cached too, so a repeated bad key is reported once.
        node = _entity_node(key, drop)
        entity_nodes[minted] = node
        return node

    # Sightings (one entity each — exactly one sighting-of link, or the
    # sighting is unanchored and goes with its entity).
    sighting_index: Dict[Tuple[str, str], Dict[str, List[str]]] = {}
    for row in sightings:
        entity = entity_for(row.get("entity_key", ""))
        if entity is None:
            drop(f"sighting-{row['id']}:unanchored")
            continue
        nodes.append(_sighting_node(row, entity["id"]))
        link(f"sighting-{row['id']}", entity["id"], "sighting-of")
        investigation = _investigation_id(
            row["investigation_kind"], row["investigation_id"]
        )
        by_system = sighting_index.setdefault(investigation, {})
        by_system.setdefault(str(row["source_system"]), []).append(
            f"sighting-{row['id']}"
        )

    # Verdicts: subjects 0..n (the schema keeps empty legitimate — "is there
    # any lateral movement at all" names none), sources joined on the
    # investigation + source_system the data actually shares.
    for row in verdicts:
        verdict_id = f"verdict-{row['id']}"
        nodes.append(_verdict_node(row))
        for subject in row.get("subject_entities") or []:
            entity = entity_for(subject)
            if entity is not None:
                link(verdict_id, entity["id"], "verdict-subject")
        for vs in verdict_sources:
            if vs["verdict_id"] != row["id"]:
                continue
            for sighting_id in sighting_index.get(
                _investigation_id(row["investigation_kind"], row["investigation_id"]),
                {},
            ).get(str(vs["source_system"]), []):
                link(verdict_id, sighting_id, "verdict-source")

    # Gaps.
    for row in gaps:
        gap_id = f"gap-{row['id']}"
        nodes.append(_gap_node(row))
        for subject in row.get("subject_entities") or []:
            entity = entity_for(subject)
            if entity is not None:
                link(gap_id, entity["id"], "gap-subject")

    # Hunt context, derived from the investigations verdicts and gaps name.
    hunts: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for row in verdicts:
        hunts.setdefault(
            (row["investigation_kind"], row["investigation_id"]), []
        ).append(row)
    for row in gaps:
        hunts.setdefault(
            (row["investigation_kind"], row["investigation_id"]), []
        ).append(row)
    for (kind, inv_id), rows in hunts.items():
        hunt_node = _hunt_node(kind, inv_id, rows)
        nodes.append(hunt_node)
        for row in rows:
            link(
                hunt_node["id"],
                f"verdict-{row['id']}" if "outcome" in row else f"gap-{row['id']}",
                "hunt-verdict" if "outcome" in row else "hunt-gap",
            )

    # Entities join last: entity_for minted them on demand as rows named them,
    # and the cache deduped every recurrence to one node.
    nodes.extend(node for node in entity_nodes.values() if node is not None)

    nodes.sort(key=lambda n: (n["kind"], n["id"]))
    links.sort(key=lambda edge: (edge["relation"], edge["source"], edge["target"]))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "source": source,
        "nodes": nodes,
        "links": links,
    }


# --------------------------------------------------------------------------
# CLI: environment -> connection -> rows -> document -> file.
# --------------------------------------------------------------------------


def connect() -> Any:
    """Open the export connection from DATABASE_URL or the PG* variables."""
    dsn = os.environ.get("DATABASE_URL")
    pg_env = {"PGHOST", "PGDATABASE", "PGUSER"} & set(os.environ)
    if not dsn and not pg_env:
        raise ExporterError(
            "no database configured. Set DATABASE_URL, or the standard PGHOST / "
            "PGPORT / PGDATABASE / PGUSER / PGPASSWORD variables for the Vigil "
            "Postgres instance. The exporter reads episodic memory; it never writes."
        )
    import psycopg2  # the transform path and the env check need no driver

    try:
        return psycopg2.connect(dsn) if dsn else psycopg2.connect()
    except psycopg2.Error as exc:
        raise ExporterError(
            "could not connect to the Vigil database — check DATABASE_URL (or "
            f"the PG* variables) and that the database is reachable: {exc}"
        ) from exc


def _named_rows(cur: Any) -> List[Dict[str, Any]]:
    """Cursor rows as dicts, named by cur.description (works with a fake cursor too)."""
    columns = [column[0] for column in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_rows(
    conn: Any, since: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """The four reads against a live connection, each ordered by id."""
    try:
        with conn.cursor() as cur:
            (
                (sightings_sql, sightings_params),
                (verdicts_sql, verdicts_params),
                (
                    gaps_sql,
                    gaps_params,
                ),
                (sources_sql, sources_params),
            ) = queries(since)
            cur.execute(sightings_sql, sightings_params)
            sightings = _named_rows(cur)
            cur.execute(verdicts_sql, verdicts_params)
            verdicts = _named_rows(cur)
            cur.execute(gaps_sql, gaps_params)
            gaps = _named_rows(cur)
            cur.execute(sources_sql, sources_params)
            sources = _named_rows(cur)
    except Exception as exc:
        raise ExporterError(
            f"could not read the episodic memory tables — is this a Vigil "
            f"database with 26_episodic_memory.sql applied? ({exc})"
        ) from exc
    return {
        "sightings": sightings,
        "verdicts": verdicts,
        "verdict_sources": sources,
        "gaps": gaps,
    }


def _parse_since(since: Optional[str]) -> Optional[str]:
    if not since:
        return None
    try:
        return datetime.fromisoformat(since).isoformat()
    except ValueError:
        raise ExporterError(
            f"--since {since!r} is not an ISO-8601 date or timestamp "
            "(try 2026-09-01 or 2026-09-01T14:00:00Z)"
        ) from None


def _run(argv: Optional[Sequence[str]]) -> int:
    parser = argparse.ArgumentParser(
        prog="export_memory",
        description=(
            "Export Vigil's episodic memory to a MemoryGraphDocument for "
            "vigilmap. Reads only; connection via DATABASE_URL or PG* env."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="path to write the MemoryGraphDocument JSON to",
    )
    parser.add_argument(
        "--since",
        help="only rows concluded on or after this ISO-8601 instant",
    )
    args = parser.parse_args(argv)

    since = _parse_since(args.since)
    rows = fetch_rows(connect(), since)

    drops: List[str] = []
    document = rows_to_document(
        rows["sightings"],
        rows["verdicts"],
        rows["verdict_sources"],
        rows["gaps"],
        source="export",
        generated_at=datetime.now().astimezone().isoformat(),
        on_drop=drops.append,
    )
    if drops:
        counts: Dict[str, int] = {}
        for category in drops:
            counts[category] = counts.get(category, 0) + 1
        summary = ", ".join(f"{count} {name}" for name, count in sorted(counts.items()))
        print(
            f"export_memory: dropped {summary} — keys or rows that join to "
            "nothing a reader can query",
            file=sys.stderr,
        )

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(
        f"export_memory: wrote {args.output} — {len(document['nodes'])} nodes, "
        f"{len(document['links'])} links"
    )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return _run(argv)
    except ExporterError as exc:
        print(f"export_memory: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
