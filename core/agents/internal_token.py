# The secret the tiers prove themselves with, named in one place. Deliberately free
# of any web framework: the BullMQ worker dispatches over this contract too, and it
# has no business importing FastAPI to read a header it will only ever send.

from __future__ import annotations

from typing import Dict

from core.secrets import get_secret

TOKEN_SECRET = "AGENT_INTERNAL_TOKEN"


# The outbound half of the contract internal_auth.authorise() checks on arrival.
def bearer_header() -> Dict[str, str]:
    token = get_secret(TOKEN_SECRET)
    # Refused rather than sent empty: at the far end an unauthenticated call reads
    # as a caller with a bad token, and the deployment fault is what needs saying.
    if not token:
        raise RuntimeError(f"{TOKEN_SECRET} is not configured")
    return {"Authorization": f"Bearer {token}"}
