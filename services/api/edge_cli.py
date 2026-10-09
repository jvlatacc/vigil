"""Operator CLI for minting Warden enrollment tokens.

Lives on the API side, not in ``core/edge``: resolving the signing secret
goes through ``core.secrets``, and the edge domain stays import-pure so
``mypy core/edge`` (the Edge core gates job) checks only edge code.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

from core.edge.enrollment import (
    DEFAULT_TOKEN_TTL_HOURS,
    ENROLLMENT_SECRET_NAME,
    mint_enrollment_token,
)
from core.secrets import get_secret


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a Warden enrollment token.")
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--ttl-hours", type=int, default=DEFAULT_TOKEN_TTL_HOURS)
    args = parser.parse_args()
    signing_secret = get_secret(ENROLLMENT_SECRET_NAME)
    if not signing_secret:
        print(
            f"{ENROLLMENT_SECRET_NAME} is not configured; set it before minting.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    expiry = datetime.now(UTC) + timedelta(hours=args.ttl_hours)
    print(mint_enrollment_token(args.node_id, secret=signing_secret, expires_at=expiry))


if __name__ == "__main__":  # pragma: no cover - operator CLI
    main()
