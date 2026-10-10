"""Seed the compose edge e2e: publish a signed tier-2 bundle and mint the
enrollment token, writing the daemon's bootstrap files to a shared directory.

Runs as a one-shot container beside the backend — the backend image carries
``core/`` and the service env carries the POSTGRES_* wiring — with the repo's
``scripts/`` and the e2e work directory bind-mounted:

    docker compose run --rm --no-deps \\
        -v "$REPO/scripts:/seed:ro" -v "$WORK:/edge-e2e" \\
        -e VIGIL_EDGE_SIGNING_KEY_FILE=/edge-e2e/signing-key.pem \\
        -e VIGIL_EDGE_ENROLLMENT_SECRET=... \\
        -e VIGIL_EDGE_SEGMENT_SCOPE='{"vpc": "vpc-compose-e2e", ...}' \\
        backend python /seed/edge_compose_seed.py --node-id gw-e2e-1 --out /edge-e2e

Outputs (in --out):
    trust-root.dsse.json   the DSSE trust root for the daemon (host mounts it)
    edge.env               compose interpolation file for the `edge` service

Idempotent across runs on a persistent database: the bundle version is
max(existing)+1 for the bundle id, and re-enrollment rotates the node
credential by design.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import timedelta

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import func, select

from core.edge import bundles, registry, signing
from core.edge.signing import MAX_BUNDLE_VALIDITY, utcnow
from core.storage.connection import get_db_manager
from core.storage.models import EdgeBundle

DEFAULT_SCOPE = (
    '{"vpc": "vpc-compose-e2e", "cidrs": ["10.42.0.0/16"],'
    ' "node_selector": {"vigil.ai/edge-role": "gateway"}}'
)


def build_document(scope: dict, ttl_seconds: int, version: int, parent: int) -> dict:
    """The spec's example bundle, sized for the e2e: one egress C2 rule,
    nftables containment, a five-second block TTL so the revert is visible
    without a wait."""
    now = utcnow()
    return {
        "bundle_id": "edge-pol-compose-e2e",
        "edge_schema_version": 1,
        "segment_scope": scope,
        "version": version,
        **({"parent_version": parent} if parent else {}),
        "not_before": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "min_edge_version": "1.0.0",
        "autonomy_tier": "tier2",
        "decision": {
            "auto_act_confidence": 0.92,
            "escalate_confidence": 0.85,
            "max_actions_per_hour": 60,
            "max_active_blocks": 24,
            "default_block_ttl_seconds": ttl_seconds,
        },
        "allowed_actions": [
            {
                "action_type": "block_ip",
                "executor": "nftables",
                "params": {"max_ttl_seconds": 3600},
            },
            {
                "action_type": "block_domain",
                "executor": "nftables",
                "params": {"max_ttl_seconds": 3600},
            },
        ],
        "rules": [
            {
                "rule_id": "c2-egress-active",
                "match": {
                    "direction": "egress",
                    "ioc_set": "c2-active",
                    "dest_kind": "ip",
                },
                "severity_floor": "high",
            }
        ],
        "ioc_sets": {
            "c2-active": {
                "kind": "cidr",
                "entries": ["203.0.113.0/24"],
                "source": "edge-compose-e2e",
            }
        },
        "revocations": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--out", default="/edge-e2e")
    parser.add_argument("--ttl-seconds", type=int, default=5)
    parser.add_argument(
        "--scope",
        default=os.environ.get("VIGIL_EDGE_SEGMENT_SCOPE") or DEFAULT_SCOPE,
        help="Segment scope JSON; must match the daemon's VIGIL_EDGE_SEGMENT_SCOPE",
    )
    args = parser.parse_args()

    key_file = os.environ.get("VIGIL_EDGE_SIGNING_KEY_FILE") or ""
    if not key_file:
        print("VIGIL_EDGE_SIGNING_KEY_FILE is required", file=sys.stderr)
        return 2
    private_key = signing.load_signing_key(key_file)
    public_raw = private_key.public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw
    )
    public_b64 = base64.b64encode(public_raw).decode()

    # The trust root the daemon verifies against — same key, TUF-shaped
    # (version + validity window), exactly what publish_bundle's self-check
    # builds for itself.
    trust_root = signing.build_trust_root(
        public_b64,
        version=1,
        issued_at=utcnow(),
        expires_at=utcnow() + MAX_BUNDLE_VALIDITY,
    )

    scope = json.loads(args.scope)
    # Standalone entry: the manager is normally initialized by the API app's
    # lifespan; a one-shot script must do it (and close it) itself.
    db = get_db_manager()
    db.initialize()
    with db.session_scope() as session:
        latest = session.scalar(
            select(func.max(EdgeBundle.version)).where(
                EdgeBundle.bundle_id == "edge-pol-compose-e2e"
            )
        )
    version = (latest or 0) + 1
    document = build_document(scope, args.ttl_seconds, version, latest or 0)

    row = bundles.publish_bundle(document, private_key)
    token = registry.mint_enrollment_token(args.node_id)
    db.close()

    os.makedirs(args.out, exist_ok=True)
    trust_path = os.path.join(args.out, "trust-root.dsse.json")
    with open(trust_path, "w") as handle:
        json.dump(trust_root, handle, indent=2, sort_keys=True)
        handle.write("\n")
    env_path = os.path.join(args.out, "edge.env")
    with open(env_path, "w") as handle:
        handle.write(f"VIGIL_EDGE_NODE_ID={args.node_id}\n")
        handle.write(f"VIGIL_EDGE_ENROLLMENT_TOKEN={token}\n")
        handle.write(f"VIGIL_EDGE_SEGMENT_SCOPE={args.scope}\n")

    print(
        f"seeded: bundle {row.bundle_id} v{row.version} (tier2, ttl "
        f"{args.ttl_seconds}s), node {args.node_id}, trust root {trust_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
