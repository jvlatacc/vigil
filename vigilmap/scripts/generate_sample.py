#!/usr/bin/env python3
"""Generate the bundled VigilMap sample dataset (deterministic).

Writes the two-hunt "Ledger Lure" scenario as a MemoryGraphDocument (v1):

* hunt h-001 traces a phishing lure to initial access and C2 on a desktop;
* hunt h-002 assesses cloud credential exposure after the compromise.

The scenario covers every verdict outcome (proven, disproven, inconclusive,
handed_off, false_positive), every entity key type, at least one gap and one
learning episode, and links both hunts to their verdicts — the demo story the
explorer opens with, no Vigil install required.

Determinism: the scenario is hand-authored literal data, ordered by
construction; the only pseudo-random draw is the synthetic loader hash, from a
fixed seed. Running this twice produces byte-identical output — CI diffs the
generated file against the checked-in JSON to keep that true.

The entity-key rule is THE one rule (core/memory/entity_keys.py): defang-normalise,
then case-fold, except arn/aws_key. This module must not grow a second
normalisation rule — exactly the drift entity_keys.py exists to prevent. When
run inside the repo (its normal habitat, and CI's), it imports Vigil's own
mint; the inline copy below is a fallback for running outside a checkout.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:  # inside the repo checkout / venv: the canonical mint
    from core.memory.entity_keys import entity_key as mint
except ImportError:  # standalone: the stated copy, byte-for-byte in spirit
    import re

    def _defang(text: str) -> str:
        text = re.sub(r"\[\.\]|\(\.\)|\{\.\}", ".", text)
        text = re.sub(r"\bh(?:xx)p", "http", text, flags=re.IGNORECASE)
        text = re.sub(r"\[:\]", ":", text)
        text = re.sub(r"\[at\]", "@", text, flags=re.IGNORECASE)
        return text

    _CASE_SENSITIVE = {"arn", "aws_key"}

    def mint(entity_type: str, value: str) -> str:
        """``type:value`` — defang-normalise, then case-fold (arn/aws_key excepted)."""
        kind = (entity_type or "").strip().lower()
        text = _defang((value or "").strip())
        if not kind or not text:
            return ""
        if kind not in _CASE_SENSITIVE:
            text = text.lower()
        return f"{kind}:{text}"

SCHEMA_VERSION = 1
SOURCE = "sample"
# Fixed vintage for the fixed scenario: a sample document's generatedAt is a
# property of the dataset, not of when the generator ran (byte-identical rule).
GENERATED_AT = "2026-09-18T15:00:00Z"
SEED = 20260914

# --- entities: (alias, entity_type, raw value, human label) -----------------
# Keys are minted at build time so the dataset joins back to Vigil exactly as
# recall does. Labels keep the raw (pre-case-fold) value where they differ.
ENTITIES: List[Tuple[str, str, str, str]] = [
    ("lure_email", "email", "billing@netledger-invoices.com", "billing@netledger-invoices.com"),
    ("lure_url", "url", "https://netledger-invoices.com/invoice/0442/view", "invoice/0442 lure link"),
    ("lure_domain", "domain", "netledger-invoices.com", "netledger-invoices.com"),
    ("c2_domain", "domain", "cdn-metrics.com", "cdn-metrics.com"),
    ("c2_ip", "ip", "203.0.113.47", "203.0.113.47"),
    ("cdn_ip", "ip", "198.51.100.23", "198.51.100.23"),
    ("workstation", "host", "JW-DESKTOP", "JW-DESKTOP"),
    ("analyst_user", "user", "j.watson", "j.watson"),
    ("shell", "process", "powershell.exe", "powershell.exe"),
    ("loader_hash", "hash", "", "dropped loader"),  # value drawn from the seeded RNG below
    ("cloud_role", "arn", "arn:aws:iam::123456789012:role/Metrics-ReadOnly", "role/Metrics-ReadOnly"),
    ("cloud_key", "aws_key", "AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
    ("cve", "cve", "CVE-2026-24817", "CVE-2026-24817"),
]

INVESTIGATION_H1 = "inv-2026-0914-01"
INVESTIGATION_H2 = "inv-2026-0916-02"

# --- sightings ---------------------------------------------------------------
SIGHTINGS: List[Dict[str, Any]] = [
    {"id": "s-0001", "label": "lure email received", "entity": "lure_email",
     "observedFrom": "2026-09-14T08:12:04Z", "observedTo": "2026-09-14T08:12:04Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0002", "label": "lure link clicked", "entity": "lure_url",
     "observedFrom": "2026-09-14T08:19:31Z", "observedTo": "2026-09-14T08:19:31Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0003", "label": "lure domain resolved", "entity": "lure_domain",
     "observedFrom": "2026-09-14T08:19:33Z", "observedTo": "2026-09-14T08:19:33Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0004", "label": "loader dropped on JW-DESKTOP", "entity": "loader_hash",
     "observedFrom": "2026-09-14T08:21:10Z", "observedTo": "2026-09-14T08:21:10Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0005", "label": "powershell spawned by loader", "entity": "shell",
     "observedFrom": "2026-09-14T08:21:14Z", "observedTo": "2026-09-14T08:21:14Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0006", "label": "C2 domain resolved by beacon", "entity": "c2_domain",
     "observedFrom": "2026-09-14T09:00:02Z", "observedTo": "2026-09-14T09:00:02Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0007", "label": "C2 beacon to 203.0.113.47", "entity": "c2_ip",
     "observedFrom": "2026-09-14T09:02:44Z", "observedTo": "2026-09-14T09:02:44Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0008", "label": "beacon retry, jittered interval", "entity": "c2_ip",
     "observedFrom": "2026-09-14T11:47:09Z", "observedTo": "2026-09-14T11:47:09Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0009", "label": "second-stage fetch from 198.51.100.23", "entity": "cdn_ip",
     "observedFrom": "2026-09-14T12:05:51Z", "observedTo": "2026-09-14T12:05:51Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0010", "label": "anomalous logons as j.watson", "entity": "analyst_user",
     "observedFrom": "2026-09-14T12:30:00Z", "observedTo": "2026-09-14T12:36:41Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0011", "label": "check-in anomaly on JW-DESKTOP", "entity": "workstation",
     "observedFrom": "2026-09-14T12:31:12Z", "observedTo": "2026-09-14T12:31:12Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0012", "label": "lure domain registered (passive DNS)", "entity": "lure_domain",
     "observedFrom": "2026-09-13T00:00:00Z", "observedTo": "2026-09-13T23:59:59Z",
     "sourceTier": "asserted", "investigationId": INVESTIGATION_H1},
    {"id": "s-0013", "label": "role seen in CloudTrail, new ASN", "entity": "cloud_role",
     "observedFrom": "2026-09-16T03:12:27Z", "observedTo": "2026-09-16T03:12:27Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H2},
    {"id": "s-0014", "label": "access key used from new ASN", "entity": "cloud_key",
     "observedFrom": "2026-09-16T03:14:02Z", "observedTo": "2026-09-16T03:14:02Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H2},
    {"id": "s-0015", "label": "patch status checked on desktop", "entity": "cve",
     "observedFrom": "2026-09-16T04:00:00Z", "observedTo": "2026-09-16T04:00:00Z",
     "sourceTier": "asserted", "investigationId": INVESTIGATION_H2},
    {"id": "s-0016", "label": "shared-infra recheck of 198.51.100.23", "entity": "cdn_ip",
     "observedFrom": "2026-09-16T05:10:38Z", "observedTo": "2026-09-16T05:10:38Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H2},
    {"id": "s-0017", "label": "j.watson lockout events", "entity": "analyst_user",
     "observedFrom": "2026-09-16T06:00:19Z", "observedTo": "2026-09-16T06:00:19Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H2},
    {"id": "s-0018", "label": "beacon TTL variation", "entity": "c2_ip",
     "observedFrom": "2026-09-15T02:11:55Z", "observedTo": "2026-09-15T02:11:55Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
    {"id": "s-0019", "label": "whois privacy on C2 registration", "entity": "c2_domain",
     "observedFrom": "2026-09-13T00:00:00Z", "observedTo": "2026-09-13T23:59:59Z",
     "sourceTier": "asserted", "investigationId": INVESTIGATION_H1},
    {"id": "s-0020", "label": "scheduled-task persistence on JW-DESKTOP", "entity": "workstation",
     "observedFrom": "2026-09-15T13:20:07Z", "observedTo": "2026-09-15T13:20:07Z",
     "sourceTier": "observed", "investigationId": INVESTIGATION_H1},
]

# --- verdicts -----------------------------------------------------------------
VERDICTS: List[Dict[str, Any]] = [
    {"id": "v-0001", "label": "proven: lure led to C2 beaconing", "outcome": "proven",
     "statement": "Ransomware pre-staging via the Ledger Lure confirmed: the lure led to a "
                  "loader on JW-DESKTOP beaconing to cdn-metrics.com / 203.0.113.47 under "
                  "account j.watson.",
     "rationale": "Loader hash, beacon timing, and account anomalies corroborate across "
                  "three independent sources.",
     "subjects": ["c2_domain", "c2_ip", "analyst_user"],
     "techniques": ["T1566", "T1059.001", "T1071"],
     "evidence": ["s-0004", "s-0006", "s-0007"],
     "hunt": "h-001", "concludedAt": "2026-09-15T17:02:00Z", "investigationId": INVESTIGATION_H1},
    {"id": "v-0002", "label": "disproven: lure domain used for BEC", "outcome": "disproven",
     "statement": "The lure domain saw no business-email-compromise activity beyond the "
                  "initial lure; no mailbox rules or fraud attempts found.",
     "rationale": "Mailbox audit over the window shows no rule creation or forwarding.",
     "subjects": ["lure_domain"],
     "evidence": ["s-0012"],
     "hunt": "h-001", "concludedAt": "2026-09-15T16:10:00Z", "investigationId": INVESTIGATION_H1},
    {"id": "v-0003", "label": "inconclusive: role assumed from second ASN", "outcome": "inconclusive",
     "statement": "Cannot confirm whether the Metrics-ReadOnly role was actually assumed; "
                  "CloudTrail lacked data-event coverage for the window.",
     "rationale": "Management events only; no data events retained.",
     "subjects": ["cloud_role", "cloud_key"],
     "evidence": ["s-0013", "s-0014"],
     "hunt": "h-002", "concludedAt": "2026-09-18T14:30:00Z", "investigationId": INVESTIGATION_H2},
    {"id": "v-0004", "label": "handed_off: CVE-2026-24817 remediation", "outcome": "handed_off",
     "statement": "Unpatched CVE-2026-24817 on JW-DESKTOP referred to the infrastructure "
                  "remediation queue.",
     "rationale": "Patch ownership sits with endpoint management.",
     "subjects": ["cve"],
     "evidence": [],
     "hunt": "h-002", "concludedAt": "2026-09-18T15:00:00Z", "investigationId": INVESTIGATION_H2},
    {"id": "v-0005", "label": "false_positive: second-stage IP", "outcome": "false_positive",
     "statement": "198.51.100.23 is a shared CDN edge, not attacker infrastructure; the "
                  "second-stage fetch was benign asset loading.",
     "rationale": "The IP serves the same ASN as the lure site's font CDN across unrelated "
                  "tenants.",
     "subjects": ["cdn_ip"],
     "evidence": ["s-0009"],
     "hunt": "h-001", "concludedAt": "2026-09-15T15:45:00Z", "investigationId": INVESTIGATION_H1},
]

# --- gaps ----------------------------------------------------------------------
GAPS: List[Dict[str, Any]] = [
    {"id": "g-0001", "label": "gap: DNS telemetry retention", "disposition": "deferred",
     "reason": "No DNS resolution telemetry retained for the 08:00-09:00 window; beacon "
               "scheduling unconfirmed.",
     "subjects": ["c2_domain"], "hunt": "h-001", "investigationId": INVESTIGATION_H1},
    {"id": "g-0002", "label": "gap: role assumption unverified", "disposition": "monitoring",
     "reason": "No data-event trail for AssumeRole; watch CloudTrail additions and re-hunt "
               "if the key recurs.",
     "subjects": ["cloud_role"], "hunt": "h-002", "investigationId": INVESTIGATION_H2},
]

# --- hunts ----------------------------------------------------------------------
HUNTS: List[Dict[str, Any]] = [
    {"id": "h-001", "label": "hunt h-001: Ledger Lure initial access",
     "objective": "Trace the Ledger Lure phishing email to initial access and C2 on JW-DESKTOP.",
     "startedAt": "2026-09-14T08:30:00Z", "endedAt": "2026-09-15T17:02:00Z"},
    {"id": "h-002", "label": "hunt h-002: cloud credential exposure",
     "objective": "Assess credential persistence and cloud exposure after the Ledger Lure "
                  "compromise.",
     "startedAt": "2026-09-16T03:30:00Z", "endedAt": "2026-09-18T15:00:00Z"},
]

# --- learning episode -------------------------------------------------------------
EPISODES: List[Dict[str, Any]] = [
    {"id": "e-0001", "label": "learning: lure-to-C2 registration lag",
     "summary": "Distilled after h-001: lure domains registered within 48h of first send now "
                "auto-correlate with fresh C2 infrastructure.",
     "occurredAt": "2026-09-15T17:30:00Z", "entities": ["lure_domain", "c2_domain"]},
]


def _entity_keys() -> Dict[str, str]:
    """Alias → minted entity key, with the seeded draw for the loader hash."""
    rng = random.Random(SEED)
    loader_hash = rng.randbytes(32).hex()
    keys: Dict[str, str] = {}
    for alias, entity_type, value, _label in ENTITIES:
        resolved = loader_hash if alias == "loader_hash" else value
        key = mint(entity_type, resolved)
        if not key:
            raise ValueError(f"entity {alias!r} minted an empty key; value unusable")
        keys[alias] = key
    return keys


def build_document() -> Dict[str, Any]:
    """Pure transform: scenario literals → MemoryGraphDocument dict.

    Unit-testable without touching the filesystem.
    """
    keys = _entity_keys()

    nodes: List[Dict[str, Any]] = []
    entity_ids: Dict[str, str] = {}

    for alias, entity_type, value, label in ENTITIES:
        resolved = keys[alias]
        entity_ids[alias] = resolved
        nodes.append({"id": resolved, "kind": "entity", "label": label,
                      "entityType": entity_type, "entityKey": resolved})

    for s in SIGHTINGS:
        nodes.append({"id": s["id"], "kind": "sighting", "label": s["label"],
                      "entityKey": entity_ids[s["entity"]],
                      "observedFrom": s["observedFrom"], "observedTo": s["observedTo"],
                      "sourceTier": s["sourceTier"], "investigationId": s["investigationId"]})

    for v in VERDICTS:
        verdict_node: Dict[str, Any] = {
            "id": v["id"], "kind": "verdict", "label": v["label"],
            "outcome": v["outcome"], "statement": v["statement"],
            "rationale": v["rationale"],
            "investigationId": v["investigationId"],
            "concludedAt": v["concludedAt"],
        }
        if v.get("techniques"):
            verdict_node["techniques"] = v["techniques"]
        nodes.append(verdict_node)

    for g in GAPS:
        nodes.append({"id": g["id"], "kind": "gap", "label": g["label"],
                      "disposition": g["disposition"], "reason": g["reason"],
                      "investigationId": g["investigationId"]})

    for h in HUNTS:
        nodes.append({"id": h["id"], "kind": "hunt", "label": h["label"],
                      "objective": h["objective"],
                      "startedAt": h["startedAt"], "endedAt": h["endedAt"]})

    for e in EPISODES:
        nodes.append({"id": e["id"], "kind": "episode", "label": e["label"],
                      "summary": e["summary"], "occurredAt": e["occurredAt"]})

    # Links in the link-table's order: sighting-of, verdict-subject, verdict-source,
    # gap-subject, hunt-verdict, hunt-gap, episode-entity.
    links: List[Dict[str, str]] = []
    links += [{"source": s["id"], "target": entity_ids[s["entity"]], "relation": "sighting-of"}
              for s in SIGHTINGS]
    links += [{"source": v["id"], "target": entity_ids[a], "relation": "verdict-subject"}
              for v in VERDICTS for a in v["subjects"]]
    links += [{"source": v["id"], "target": s, "relation": "verdict-source"}
              for v in VERDICTS for s in v["evidence"]]
    links += [{"source": g["id"], "target": entity_ids[a], "relation": "gap-subject"}
              for g in GAPS for a in g["subjects"]]
    links += [{"source": v["hunt"], "target": v["id"], "relation": "hunt-verdict"}
              for v in VERDICTS]
    links += [{"source": g["hunt"], "target": g["id"], "relation": "hunt-gap"} for g in GAPS]
    links += [{"source": e["id"], "target": entity_ids[a], "relation": "episode-entity"}
              for e in EPISODES for a in e["entities"]]

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": GENERATED_AT,
        "source": SOURCE,
        "nodes": nodes,
        "links": links,
    }


def check_document(doc: Dict[str, Any]) -> None:
    """Producer-side self-check: a scenario that breaks the contract fails loudly here."""
    node_ids = [n["id"] for n in doc["nodes"]]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("duplicate node ids")
    by_id = {n["id"]: n for n in doc["nodes"]}

    for link in doc["links"]:
        for endpoint in ("source", "target"):
            if link[endpoint] not in by_id:
                raise ValueError(f"dangling link endpoint: {link}")
        if by_id[link["source"]]["kind"] == "sighting" and link["relation"] == "sighting-of":
            if by_id[link["target"]]["kind"] != "entity":
                raise ValueError(f"sighting-of target must be entity: {link}")

    sighting_of = sum(1 for l in doc["links"] if l["relation"] == "sighting-of")
    sightings = sum(1 for n in doc["nodes"] if n["kind"] == "sighting")
    if sighting_of != sightings:
        raise ValueError(f"each sighting needs exactly one sighting-of ({sightings} sightings, "
                         f"{sighting_of} links)")

    subjects_by_verdict: Dict[str, int] = {}
    for link in doc["links"]:
        if link["relation"] == "verdict-subject":
            subjects_by_verdict[link["source"]] = subjects_by_verdict.get(link["source"], 0) + 1
    for verdict_id, count in subjects_by_verdict.items():
        if not 1 <= count <= 3:
            raise ValueError(f"verdict {verdict_id} names {count} subjects; contract allows 1-3")

    for node in doc["nodes"]:
        if node["kind"] == "entity" and not node["entityKey"].startswith(node["entityType"] + ":"):
            raise ValueError(f"entity key does not start with its type: {node['id']}")

    outcomes = {n["outcome"] for n in doc["nodes"] if n["kind"] == "verdict"}
    expected_outcomes = {"proven", "disproven", "inconclusive", "handed_off", "false_positive"}
    if outcomes != expected_outcomes:
        raise ValueError(f"scenario must cover all five outcomes; found {sorted(outcomes)}")

    entity_types = {n["entityType"] for n in doc["nodes"] if n["kind"] == "entity"}
    expected_types = {"ip", "domain", "host", "url", "email", "hash", "arn", "aws_key",
                      "user", "process", "cve"}
    if entity_types != expected_types:
        raise ValueError(f"scenario must cover all eleven entity types; missing "
                         f"{sorted(expected_types - entity_types)}")

    if not any(n["kind"] == "gap" for n in doc["nodes"]):
        raise ValueError("scenario must include at least one gap")
    if not any(n["kind"] == "episode" for n in doc["nodes"]):
        raise ValueError("scenario must include at least one episode")

    hunts_with_verdicts = {l["source"] for l in doc["links"] if l["relation"] == "hunt-verdict"}
    hunt_ids = {n["id"] for n in doc["nodes"] if n["kind"] == "hunt"}
    if hunts_with_verdicts != hunt_ids:
        raise ValueError(f"hunts without verdicts: {sorted(hunt_ids - hunts_with_verdicts)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "public" / "data" / "sample-memory.json"),
        help="output path (default: vigilmap/public/data/sample-memory.json)",
    )
    args = parser.parse_args()

    doc = build_document()
    check_document(doc)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    out_path.write_text(payload, encoding="utf-8")

    kinds: Dict[str, int] = {}
    for node in doc["nodes"]:
        kinds[node["kind"]] = kinds.get(node["kind"], 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(kinds.items()))
    print(f"wrote {out_path} ({len(doc['nodes'])} nodes [{summary}], {len(doc['links'])} links)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
