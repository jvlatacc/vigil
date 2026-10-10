"""The Reconciler: the reconnect half of the mesh — journal → control plane.

While the node defends its segment alone, every decision lands in the
hash-chained journal; the control plane hears about them only when the
link returns. This component pushes journal batches to the frozen
``POST /api/v1/edge/journal`` contract and advances a local watermark
from the server's receipts. The receipt range IS the dedupe: records at
or below the server-held watermark are never re-pushed, and a chain gap
is answered with the exact position to resume from — the contract has
no receipt-read endpoint, so the 409 resync is also how a restarted
warden (watermark 0, server still holding receipts) finds its place.

Per response:

- **200** — ``accepted_through`` is the new watermark (monotonic; the
  server's receipt is the authority). ``duplicate_ids`` are records the
  server declined to merge twice by idempotency key — counted, never
  retried: the watermark already moved past them. ``rejected`` records
  verified but failed the server's legality re-check — logged with
  their codes; the chain position advanced either way, so nothing is
  re-sent.
- **409** — the batch did not chain onto the server-held head: the
  watermark resyncs to ``server_last_seq`` and the next cycle resumes
  at ``resend_from`` (head + 1).
- **401/403** — the node's credentials are unknown or revoked. The
  reconciler never loosens on this: pushes stop (sticky halt — retrying
  rejected credentials cannot succeed) and revocation itself surfaces
  through the sync channel, the machine's only tightening input.
- **transport errors** — a miss, not a refusal; the next cycle retries.

Citation: a batch cites the node's current verified pack version — the
only version the control plane can judge legality against, because at
most one policy per node is active (the partial unique index on
``edge_policies``), so superseded versions cannot be resolved
server-side. Records made under an older version's envelope are pushed
under the current citation; the server's legality check judges each
record's action type against that envelope and refuses what it does
not allow — audit-faithful for the common case, fail-closed (never
merged, never laundered) for the rest.

Before any push, every record passes
``core.edge.journal.record_wire_error`` — the node-side pin of the
frozen wire shapes. A record the wire cannot carry would be worse than
an unpushed one: the server would refuse the whole batch and, with
contiguity, nothing behind it could ever merge. A failed pin halts the
drain (sticky, like the decision loop's revoked halt): the writer is
buggy, and the fix is a code change, not a retry.

The drain is mode-gated: pushes run in SYNCED (opportunistic deltas)
and RECONCILING (the post-partition drain); every other mode is a
partition, an expiry, or a halt — none of those is a reason to talk to
the control plane. Draining RECONCILING to empty completes it: the
machine returns to SYNCED only when the server has everything the node
did.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable

import httpx

from core.edge.journal import record_hash, record_wire_error
from services.warden.journal import Journal
from services.warden.metrics import WardenMetrics
from services.warden.modes import ModeMachine, OperatingMode
from services.warden.storage import PolicyStore

logger = logging.getLogger(__name__)

__all__ = ["Reconciler"]


class Reconciler:
    """Push the decision journal to the control plane on reconnect.

    Registered into the process like any component; ``tick`` is its
    body, callable directly in tests. The watermark is in-memory: a
    restart resyncs via the 409 path above.
    """

    def __init__(
        self,
        *,
        journal: Journal,
        store: PolicyStore,
        base_url: str,
        machine: ModeMachine,
        policy_version: Callable[[], int | None],
        batch_size: int,
        interval_seconds: float,
        clock: Callable[[], datetime],
        metrics: WardenMetrics,
        mode_observer: Callable[[str], None] | None = None,
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._journal = journal
        self._store = store
        self._base_url = base_url.rstrip("/")
        self._machine = machine
        self._policy_version = policy_version
        self._batch_size = batch_size
        self._interval = interval_seconds
        self._clock = clock
        self._metrics = metrics
        self._mode_observer = mode_observer
        self._timeout = timeout
        self._client = client
        self._acked = 0
        self._halted: str | None = None

    # ------------------------------------------------------------------
    # Component protocol
    # ------------------------------------------------------------------

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """The component task: tick on the interval until shutdown."""
        while not shutdown_event.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - the component survives to retry
                logger.exception("warden reconciler tick failed; continuing")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # The tick
    # ------------------------------------------------------------------

    async def tick(self) -> None:
        """One cycle: gate, batch, pin, push, absorb the receipt."""
        if self._halted is not None:
            self._metrics.reconcile_attempts.labels(outcome="halted").inc()
            return
        if self._machine.mode not in (OperatingMode.SYNCED, OperatingMode.RECONCILING):
            return
        pending = self._journal.records_after(self._acked)
        if not pending:
            self._complete_reconciling()
            return
        credentials = self._store.load_credentials()
        if credentials is None:
            # A node identity is how the server authorizes the merge; a
            # node without one cannot prove anything it journals.
            self._metrics.reconcile_attempts.labels(outcome="no-credentials").inc()
            logger.warning(
                "warden reconcile: no node credentials — cannot authenticate"
            )
            return
        node_id, token = credentials
        version = self._policy_version()
        if version is None:
            # Nothing to cite: the server would refuse the whole batch
            # (no active policy = no legality check possible).
            self._metrics.reconcile_attempts.labels(outcome="no-policy").inc()
            return
        batch = pending[: self._batch_size]
        for record in batch:
            error = record_wire_error(record)
            if error is not None:
                self._halted = f"record seq={record.get('seq')}: {error}"
                logger.error("warden reconcile halted: %s", self._halted)
                self._metrics.reconcile_attempts.labels(outcome="halted").inc()
                return
        try:
            response = await self._push(node_id, token, version, batch)
        except httpx.HTTPError as exc:
            self._metrics.reconcile_attempts.labels(outcome="transport").inc()
            logger.warning("warden reconcile: push failed (%s)", exc)
            return
        self._absorb(response)

    # ------------------------------------------------------------------
    # Push and absorb
    # ------------------------------------------------------------------

    async def _push(
        self, node_id: str, token: str, version: int, batch: list[dict[str, Any]]
    ) -> httpx.Response:
        last = batch[-1]
        return await self._http().post(
            f"{self._base_url}/api/v1/edge/journal",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "node_id": node_id,
                "policy_version": version,
                "chain_head": record_hash(last["prev_hash"], last),
                "records": batch,
            },
        )

    def _absorb(self, response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            self._metrics.reconcile_attempts.labels(outcome="auth").inc()
            self._halted = f"auth-refused-{response.status_code}"
            logger.error(
                "warden reconcile: control plane refused node credentials "
                "(%d) — stopping pushes; revocation surfaces via sync",
                response.status_code,
            )
            return
        if response.status_code == 409:
            self._metrics.reconcile_attempts.labels(outcome="gap").inc()
            body = self._json_body(response)
            if body is None:
                return
            server_last_seq = body.get("server_last_seq")
            if isinstance(server_last_seq, int) and server_last_seq > self._acked:
                self._acked = server_last_seq
            logger.warning(
                "warden reconcile: chain gap (%s: %s) — resuming from seq %d",
                body.get("reason"),
                body.get("detail"),
                self._acked + 1,
            )
            return
        if response.status_code != 200:
            self._metrics.reconcile_attempts.labels(outcome="http").inc()
            return
        body = self._json_body(response)
        if body is None:
            self._metrics.reconcile_attempts.labels(outcome="bad-response").inc()
            return
        accepted = body.get("accepted_through")
        if isinstance(accepted, int) and accepted > self._acked:
            self._acked = accepted
        duplicates = body.get("duplicate_ids")
        rejected = body.get("rejected")
        merged = body.get("merged_count")
        if isinstance(duplicates, list):
            self._metrics.reconcile_records.labels(result="duplicate").inc(
                len(duplicates)
            )
        if isinstance(rejected, list):
            self._metrics.reconcile_records.labels(result="rejected").inc(len(rejected))
            for item in rejected:
                logger.warning(
                    "warden reconcile: record seq=%s refused at merge (%s: %s)",
                    item.get("seq"),
                    item.get("code"),
                    item.get("detail"),
                )
        self._metrics.reconcile_records.labels(result="merged").inc(
            merged if isinstance(merged, int) else 0
        )
        logger.info(
            "warden reconcile: accepted through seq %d (merged %s, %s duplicate(s))",
            self._acked,
            merged,
            len(duplicates) if isinstance(duplicates, list) else "?",
        )
        self._complete_reconciling()

    # ------------------------------------------------------------------
    # State plumbing
    # ------------------------------------------------------------------

    def _complete_reconciling(self) -> None:
        """RECONCILING closes only on an empty drain — never before."""
        if self._journal.records_after(self._acked):
            return
        if self._machine.mode is OperatingMode.RECONCILING:
            self._machine.note_reconcile_complete()
            if self._mode_observer is not None:
                self._mode_observer(self._machine.mode.value)
            logger.info("warden reconcile: journal drained — SYNCED")

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    @staticmethod
    def _json_body(response: httpx.Response) -> dict[str, Any] | None:
        try:
            body = response.json()
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    # ------------------------------------------------------------------
    # Status surface (the process's status payload reads through these)
    # ------------------------------------------------------------------

    @property
    def acked_seq(self) -> int:
        """The server-acknowledged watermark (0 = nothing accepted yet)."""
        return self._acked

    @property
    def halted_reason(self) -> str | None:
        """Why the drain is pinned, when it is pinned."""
        return self._halted
