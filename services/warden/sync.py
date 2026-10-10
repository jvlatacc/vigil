"""PolicySync: pull, verify, and store the signed containment policy.

One sync cycle, in the fail-closed order the spec fixes:

1. **Credentials** — load from the store, or enroll with the one-time
   operator token (POST /api/v1/edge/enroll). No credentials and no token
   is a refusal, never a skip.
2. **Fetch** — GET /api/v1/edge/policy with the per-node bearer token.
   401/403 are the revocation signal (the only control-plane fact allowed
   to *tighten* behavior, handled by the mode machine); 404 is "no active
   policy yet"; anything else is a transport miss.
3. **Verify before parse** — the response's ``envelope`` is re-serialized
   deterministically and handed to ``load_policy_pack``, which verifies the
   DSSE signatures against the baked-in trust root before the payload is
   parsed, then applies the monotonic per-node version gate.
4. **Cross-check the storage hash** — the control plane records
   ``payload_hash`` alongside the stored envelope (its own integrity
   check); Warden refuses a pack whose verified payload does not match it,
   so a corrupted or forked control-plane row can never become authority.
5. **Store** — only a fully verified pack is persisted, and the watermark
   it installs is what the next cycle's version gate compares against.

The watermark's authority chain matters: it comes from the last pack this
process verified, or — on first start — from a stored policy that itself
re-verifies against the trust root. A stored policy that no longer
verifies is treated as tampering: the cycle refuses and keeps the refusal,
it never silently forgets the watermark (forgetting would let an old,
still-signed pack downgrade the node).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

import httpx

from core.edge.policy import ParsedPolicy, PolicyPack, VersionState, load_policy_pack
from core.edge.signing import deterministic_json
from services.warden.metrics import WardenMetrics
from services.warden.storage import PolicyStore

logger = logging.getLogger(__name__)

#: Rejection classes PolicySync produces itself. The P-* classes from
#: core/edge (version replay/fork, expiry, schema) pass through unchanged.
S_NO_CREDENTIALS = "S-NO-CREDENTIALS"
S_AUTH = "S-AUTH"
S_NO_POLICY = "S-NO-POLICY"
S_TRANSPORT = "S-TRANSPORT"
S_HTTP = "S-HTTP"
S_BAD_RESPONSE = "S-BAD-RESPONSE"
S_PAYLOAD_HASH = "P-PAYLOAD-HASH"
S_STORE_TAMPERED = "S-STORE-TAMPERED"


def _default_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class SyncOutcome:
    """One cycle's result, consumed by the mode machine.

    ``ok`` means a pack is verified and installed (changed or not).
    ``revoked`` marks an observed 401/403 — a tightening-only signal.
    """

    ok: bool
    changed: bool = False
    pack: PolicyPack | None = None
    codes: tuple[str, ...] = ()
    detail: str = ""
    revoked: bool = False
    http_status: int | None = None
    refused_stored: bool = field(default=False)

    @property
    def codes_text(self) -> str:
        return ",".join(self.codes) if self.codes else "none"


class PolicySync:
    """Fetch-verify-store cycle body. The mode machine owns the cadence."""

    def __init__(
        self,
        *,
        trust_root: dict,
        store: PolicyStore,
        base_url: str,
        enrollment_token: str | None,
        segment_labels: tuple[str, ...] = (),
        sync_timeout_seconds: float = 10.0,
        clock: Callable[[], datetime] | None = None,
        metrics: WardenMetrics | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._trust_root = trust_root
        self._store = store
        self._base_url = base_url.rstrip("/")
        self._enrollment_token = enrollment_token
        self._segment_labels = list(segment_labels)
        self._timeout = sync_timeout_seconds
        self._clock = clock or _default_clock
        self._metrics = metrics
        self._client = client
        # The watermark from the last pack this process verified. When the
        # stored file disagrees with it, the store is treated as tampered.
        self._watermark: VersionState | None = None

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    async def ensure_credentials(self) -> tuple[str, str] | None:
        """Load stored credentials or enroll; None means "cannot authenticate"."""
        stored = self._store.load_credentials()
        if stored is not None:
            return stored
        if not self._enrollment_token:
            return None
        node_id, token = await self._enroll()
        self._store.save_credentials(node_id, token)
        return node_id, token

    async def _enroll(self) -> tuple[str, str]:
        from core.edge.enrollment import validate_node_id

        response = await self._http().post(
            f"{self._base_url}/api/v1/edge/enroll",
            headers={"Authorization": f"Bearer {self._enrollment_token}"},
            json={"segment_labels": list(self._segment_labels)},
        )
        response.raise_for_status()
        doc = response.json()
        node_id = doc.get("node_id")
        token = doc.get("token")
        if not isinstance(node_id, str) or not isinstance(token, str) or not token:
            raise ValueError("enrollment response missing node_id/token")
        validate_node_id(node_id)
        logger.info("warden enrolled as %s", node_id)
        return node_id, token

    # ------------------------------------------------------------------
    # One sync cycle
    # ------------------------------------------------------------------

    async def sync_once(self) -> SyncOutcome:
        try:
            credentials = await self.ensure_credentials()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("warden sync: enrollment failed: %s", exc)
            self._count("enroll-failed")
            return SyncOutcome(ok=False, codes=(S_TRANSPORT,), detail=str(exc))
        if credentials is None:
            return SyncOutcome(
                ok=False,
                codes=(S_NO_CREDENTIALS,),
                detail=(
                    "no stored node credentials and no enrollment token — "
                    "issue WARDEN_ENROLLMENT_TOKEN to bootstrap this node"
                ),
            )
        _, token = credentials
        try:
            response = await self._fetch(token)
        except httpx.HTTPError as exc:
            logger.warning("warden sync: policy fetch failed: %s", exc)
            self._count("transport-error")
            return SyncOutcome(ok=False, codes=(S_TRANSPORT,), detail=str(exc))
        return self._absorb(response)

    async def _fetch(self, token: str) -> httpx.Response:
        return await self._http().get(
            f"{self._base_url}/api/v1/edge/policy",
            headers={"Authorization": f"Bearer {token}"},
        )

    def _absorb(self, response: httpx.Response) -> SyncOutcome:
        """Classify the fetch response and, when valid, install the pack."""
        if response.status_code in (401, 403):
            self._count("auth-refused")
            return SyncOutcome(
                ok=False,
                codes=(S_AUTH,),
                detail=(
                    f"control plane refused node credentials: "
                    f"{response.status_code}"
                ),
                revoked=True,
                http_status=response.status_code,
            )
        if response.status_code == 404:
            self._count("no-policy")
            return SyncOutcome(
                ok=False,
                codes=(S_NO_POLICY,),
                detail="control plane has no active policy for this node",
                http_status=404,
            )
        if response.status_code != 200:
            self._count("http-error")
            return SyncOutcome(
                ok=False,
                codes=(S_HTTP,),
                detail=f"policy fetch returned {response.status_code}",
                http_status=response.status_code,
            )
        try:
            doc = response.json()
        except ValueError:
            self._count("bad-response")
            return SyncOutcome(
                ok=False, codes=(S_BAD_RESPONSE,), detail="policy body is not JSON"
            )
        if not isinstance(doc, dict):
            self._count("bad-response")
            return SyncOutcome(
                ok=False,
                codes=(S_BAD_RESPONSE,),
                detail="policy body is not a JSON object",
            )
        return self._verify_and_store(doc)

    def _verify_and_store(self, doc: dict[str, Any]) -> SyncOutcome:
        envelope = doc.get("envelope")
        if not isinstance(envelope, dict):
            self._count("bad-response")
            return SyncOutcome(
                ok=False,
                codes=(S_BAD_RESPONSE,),
                detail="policy response has no envelope object",
            )
        envelope_bytes = deterministic_json(envelope)
        state = self._current_watermark()
        if isinstance(state, SyncOutcome):  # stored pack failed re-verification
            self._count("store-tampered")
            return state
        parsed = load_policy_pack(
            envelope_bytes, self._trust_root, now=self._clock(), state=state
        )
        if not parsed.ok or parsed.pack is None:
            self._count("refused")
            return SyncOutcome(
                ok=False,
                codes=tuple(parsed.codes) or ("S-REFUSED",),
                detail=self._errors_text(parsed),
            )
        pack = parsed.pack
        recorded_hash = doc.get("payload_hash")
        if recorded_hash != pack.payload_hash:
            self._count("refused")
            return SyncOutcome(
                ok=False,
                codes=(S_PAYLOAD_HASH,),
                detail=(
                    "verified payload does not match the control plane's "
                    "recorded payload_hash — stored policy is corrupt or forked"
                ),
            )
        changed = state is None or state != pack.version_state()
        self._watermark = pack.version_state()
        self._store.save_policy(doc)
        self._count("same" if not changed else "ok")
        return SyncOutcome(ok=True, changed=changed, pack=pack)

    # ------------------------------------------------------------------
    # Watermark authority
    # ------------------------------------------------------------------

    def _current_watermark(self) -> VersionState | SyncOutcome | None:
        """The version gate's starting point, a refusal, or None (no state).

        In-process memory wins: it is the last thing this process verified.
        On first start the stored policy is re-verified before its
        watermark is honored — verify-before-trust applies to our own disk.
        """
        if self._watermark is not None:
            return self._watermark
        stored = self._store.load_policy()
        if stored is None:
            return None
        envelope = stored.get("envelope")
        if not isinstance(envelope, dict):
            return SyncOutcome(
                ok=False,
                codes=(S_STORE_TAMPERED,),
                detail="stored policy has no envelope",
                refused_stored=True,
            )
        parsed = load_policy_pack(
            deterministic_json(envelope),
            self._trust_root,
            now=self._clock(),
            state=None,
        )
        if not parsed.ok or parsed.pack is None:
            temporal = {code for code, _ in parsed.errors}
            if temporal and temporal <= {"P-EXPIRED", "P-NOT-YET-VALID"}:
                # The signature was honest; the clock moved on. No watermark
                # to inherit — the fresh fetch decides (and an expired pack
                # re-presented now is refused by the semantic checks).
                return None
            return SyncOutcome(
                ok=False,
                codes=(S_STORE_TAMPERED, *temporal),
                detail="stored policy failed re-verification — possible tampering",
                refused_stored=True,
            )
        recorded_hash = stored.get("payload_hash")
        if recorded_hash != parsed.pack.payload_hash:
            return SyncOutcome(
                ok=False,
                codes=(S_STORE_TAMPERED,),
                detail="stored policy hash does not match its verified payload",
                refused_stored=True,
            )
        return parsed.pack.version_state()

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    def _http(self) -> httpx.AsyncClient:
        """The injected client, or an owned one created on first use."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        """Close the owned client (an injected one is the caller's to close)."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _count(self, outcome: str) -> None:
        if self._metrics is not None:
            self._metrics.sync_attempts.labels(outcome=outcome).inc()

    @staticmethod
    def _errors_text(parsed: ParsedPolicy) -> str:
        return "; ".join(f"{code}: {detail}" for code, detail in parsed.errors)
