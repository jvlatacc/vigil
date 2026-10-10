"""The lease registry: durable per-attacker redirect state.

A lease is the pipeline's first rollback machinery. The ``approval_actions``
row records the decision; the lease row — here, in Postgres where the daemon,
the API and the console can all see it — records the redirect itself: its
scope, its backend, its TTL countdown, and the unsteer result when it ends.
Nothing about a redirect lives in process memory, because the processes do
not share any.

Lifecycle: ``mint`` writes a ``pending`` lease when an approved honey-route
action reaches its executor; ``steer_lease`` programs the backend and marks
it ``active`` (or ``failed`` — traffic was never touched); ``release`` runs
the unsteer and records the rollback; ``sweep`` drives expiry, renewal under
the max-duration cap, the kill-switch, and orphaned rows. Every path is
fail-open: a backend outage marks rows failed and leaves production routing
alone.
"""

import asyncio
import concurrent.futures
import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional

from core.deception.backends import SteerScope, build_backend
from core.deception.config import DeceptionConfig
from core.time import utcnow

logger = logging.getLogger(__name__)

# Lease statuses that still need reconciliation; released/failed are terminal.
OPEN_LEASE_STATUSES = ("pending", "active")


def run_backend_call(awaitable: Any) -> Dict[str, Any]:
    """Run an async steering call from the pipeline's sync executors.

    ``execute_approved_actions`` and the inline auto-approve path are sync —
    the daemon's 30-second sweep and ``create_isolation_action`` call them
    without a loop — while the :class:`~core.deception.backends.SteeringBackend`
    protocol is async so real backends can do non-blocking IO. With no loop
    running, ``asyncio.run`` is exact; with one running (the daemon sweep),
    the coroutine runs to completion on a worker thread's own loop, which is
    no worse than the sync Cloudflare executor's blocking HTTP.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, awaitable).result()


class DeceptionLeaseService:
    """Owns the lease lifecycle: mint → steer → (renew | release)."""

    def __init__(
        self,
        config: Optional[DeceptionConfig] = None,
        backend: Optional[Any] = None,
    ):
        self.config = config or DeceptionConfig.resolved()
        self.backend = (
            backend if backend is not None else build_backend(self.config.backend)
        )

    # ------------------------------------------------------------------
    # Row primitives (sync)
    # ------------------------------------------------------------------

    def _model(self):
        from core.storage.models import DeceptionLease

        return DeceptionLease

    def get(self, lease_id: str) -> Optional[Any]:
        """The lease row, or None."""
        from core.storage.connection import get_db_manager

        DeceptionLease = self._model()
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                row = session.get(DeceptionLease, lease_id)
                if row is None:
                    return None
                session.expunge(row)
                return row
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to read deception lease %s: %s", lease_id, e)
            return None

    def by_action(self, action_id: str) -> Optional[Any]:
        """The lease an approval action minted, if any."""
        from sqlalchemy import select

        from core.storage.connection import get_db_manager

        DeceptionLease = self._model()
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                row = session.execute(
                    select(DeceptionLease)
                    .where(DeceptionLease.action_id == action_id)
                    .order_by(DeceptionLease.created_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    return None
                session.expunge(row)
                return row
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to read lease for action %s: %s", action_id, e)
            return None

    def open_by_attacker(self, attacker_ip: str) -> Optional[Any]:
        """An attacker's live lease, if one exists."""
        from sqlalchemy import select

        from core.storage.connection import get_db_manager

        DeceptionLease = self._model()
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                row = session.execute(
                    select(DeceptionLease)
                    .where(
                        DeceptionLease.attacker_ip == attacker_ip,
                        DeceptionLease.status.in_(OPEN_LEASE_STATUSES),
                    )
                    .order_by(DeceptionLease.created_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    return None
                session.expunge(row)
                return row
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to read open lease for %s: %s", attacker_ip, e)
            return None

    def list_leases(
        self, statuses: Optional[List[str]] = None, limit: int = 200
    ) -> List[Any]:
        """Lease rows newest-first, optionally filtered by status."""
        from sqlalchemy import select

        from core.storage.connection import get_db_manager

        DeceptionLease = self._model()
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                query = (
                    select(DeceptionLease)
                    .order_by(DeceptionLease.created_at.desc())
                    .limit(limit)
                )
                if statuses:
                    query = query.where(DeceptionLease.status.in_(statuses))
                rows = list(session.execute(query).scalars().all())
                for row in rows:
                    session.expunge(row)
                return rows
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to list deception leases: %s", e)
            return []

    def mint(
        self,
        *,
        attacker_ip: str,
        destination_ips: List[str],
        ports: List[int],
        action_id: Optional[str],
        ttl_seconds: int,
        backend: Optional[str] = None,
        now=None,
    ) -> str:
        """Write the pending lease row and return its id."""
        from core.storage.connection import get_db_manager

        DeceptionLease = self._model()
        now = now or utcnow()
        lease_id = f"lease-{uuid.uuid4().hex[:16]}"
        db = get_db_manager()
        with db.session_scope() as session:
            session.add(
                DeceptionLease(
                    lease_id=lease_id,
                    attacker_ip=attacker_ip,
                    action_id=action_id,
                    destination_ips=destination_ips,
                    ports=ports,
                    status="pending",
                    backend=backend or self.backend.name,
                    ttl_seconds=ttl_seconds,
                    created_at=now,
                )
            )
        return lease_id

    def _update(self, lease_id: str, **columns: Any) -> None:
        from core.storage.connection import get_db_manager

        DeceptionLease = self._model()
        db = get_db_manager()
        with db.session_scope() as session:
            row = session.get(DeceptionLease, lease_id)
            if row is None:
                logger.error("Deception lease %s vanished mid-update", lease_id)
                return
            for key, value in columns.items():
                setattr(row, key, value)

    def prune_probes(self, now=None) -> int:
        """Drop probe evidence older than twice the corroboration window.

        The sweep task calls this so the deception tables stay bounded
        without a second scheduled task owning the same clock.
        """
        from core.deception.signals import DeceptionSignalService

        return DeceptionSignalService(config=self.config).prune(now=now)

    # ------------------------------------------------------------------
    # Steering — async (the backend protocol is async)
    # ------------------------------------------------------------------

    def scope_for(self, row, ttl_seconds: Optional[int] = None) -> SteerScope:
        """The :class:`SteerScope` that programs one redirect."""
        return SteerScope(
            source_ip=row.attacker_ip,
            destination_ips=list(row.destination_ips or []),
            ports=[int(p) for p in (row.ports or [])],
            ttl_seconds=(
                ttl_seconds if ttl_seconds is not None else int(row.ttl_seconds or 0)
            ),
            lease_id=row.lease_id,
        )

    async def steer_lease(
        self, lease_id: str, ttl_seconds: Optional[int] = None, now=None
    ) -> Dict[str, Any]:
        """Program the backend for a pending lease and mark it active.

        Failure marks the lease failed — nothing was routed — and returns the
        standard ``{success, error?, message?}`` shape. Kill-switch active is
        a refusal, not a failure of the backend.
        """
        from core.deception.signals import DeceptionSignalService

        row = self.get(lease_id)
        if row is None:
            return {"success": False, "error": f"lease {lease_id} not found"}
        if row.status == "active":
            # Steer is an upsert; already-active is only re-programming.
            pass
        elif row.status not in ("pending",):
            return {
                "success": False,
                "error": f"lease {lease_id} is {row.status}; not steerable",
            }

        signals = DeceptionSignalService(config=self.config)
        if signals.kill_switch_active(now=now):
            self._update(
                lease_id,
                status="released",
                released_at=now or utcnow(),
                release_reason="kill_switch",
                rollback_result={
                    "success": True,
                    "backend_ref": None,
                    "message": "never steered",
                },
            )
            return {
                "success": False,
                "error": "kill_switch_active",
                "message": "Deception kill switch is on; the lease was not steered.",
            }

        ttl = int(ttl_seconds if ttl_seconds is not None else row.ttl_seconds)
        scope = self.scope_for(row, ttl)
        now = now or utcnow()
        result = await self.backend.steer(scope)
        if result.get("success"):
            self._update(
                lease_id,
                status="active",
                started_at=now,
                expires_at=now + timedelta(seconds=ttl),
                backend=result.get("backend", self.backend.name),
                backend_ref=result.get("backend_ref"),
                ttl_seconds=ttl,
            )
            logger.info(
                "Honey-route lease %s active: %s ports %s -> decoys (ttl %ss)",
                lease_id,
                scope["source_ip"],
                scope["ports"],
                ttl,
            )
        else:
            self._update(
                lease_id,
                status="failed",
                released_at=now,
                release_reason=f"steer failed: {result.get('error', 'unknown')}",
            )
            logger.warning(
                "Honey-route lease %s failed to steer: %s",
                lease_id,
                result.get("error"),
            )
        return result

    async def release(
        self,
        lease_id: str,
        reason: str,
        now=None,
        unsteer: bool = True,
    ) -> Dict[str, Any]:
        """Unsteer a lease and record the rollback. Terminal rows stay put.

        Returns ``{success, released?, ...}``; ``success`` is the unsteer
        outcome, ``released`` whether this call did the releasing. A release
        always wins over the row's previous state — the switch's job is to
        end redirects, whatever the audit shows afterwards.
        """
        now = now or utcnow()
        row = self.get(lease_id)
        if row is None:
            return {"success": False, "error": f"lease {lease_id} not found"}
        if row.status in ("released", "failed"):
            return {
                "success": True,
                "released": False,
                "message": f"lease {lease_id} already {row.status}",
            }

        rollback: Dict[str, Any] = {"skipped": True, "reason": "unsteer not requested"}
        if unsteer:
            try:
                rollback = await self.backend.unsteer(lease_id, row.backend_ref)
            except Exception as e:  # noqa: BLE001 — a rollback outage is logged,
                # never raised past the sweep: the row still records the attempt.
                logger.error("Unsteer of lease %s failed: %s", lease_id, e)
                rollback = {"success": False, "error": str(e)}

        self._update(
            lease_id,
            status="released",
            released_at=now,
            release_reason=reason,
            rollback_result=rollback,
        )
        logger.info("Honey-route lease %s released (%s)", lease_id, reason)
        return {
            "success": bool(rollback.get("success", True)),
            "released": True,
            "lease_id": lease_id,
            "rollback": rollback,
        }

    # ------------------------------------------------------------------
    # Sweep — expiry, renewal, kill-switch, orphans
    # ------------------------------------------------------------------

    async def sweep(
        self, now=None, signals: Optional[Any] = None
    ) -> Dict[str, List[str]]:
        """Reconcile every open lease once.

        Kill-switch first: when it is tripped, every open lease is released
        (unsteered) and nothing renews. Then orphaned pending rows — the
        executor died between mint and steer — and expired actives are
        released, and corroborated actives are renewed under the
        max-duration cap. Returns ids by outcome for the caller's counters.
        """
        from core.deception.signals import DeceptionSignalService

        now = now or utcnow()
        signals = signals or DeceptionSignalService(config=self.config)
        out: Dict[str, List[str]] = {
            "released": [],
            "renewed": [],
            "expired": [],
            "failed": [],
        }

        try:
            if signals.kill_switch_active(now=now):
                for row in self.list_leases(statuses=list(OPEN_LEASE_STATUSES)):
                    result = await self.release(
                        row.lease_id,
                        "kill_switch",
                        now=now,
                        unsteer=row.status == "active",
                    )
                    (
                        out["released"] if result.get("released") else out["failed"]
                    ).append(row.lease_id)
                return out
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Deception kill-switch check failed; continuing expiry sweep: %s", e
            )

        # Orphaned pending rows: minted but never steered (executor died
        # mid-step). Past the TTL they would only ever have had, they are
        # released; the unsteer is best-effort against a backend that may
        # never have been programmed.
        stale_pending = now - timedelta(seconds=2 * max(self.config.ttl_seconds, 1))
        for row in self.list_leases(statuses=["pending"]):
            if row.created_at and row.created_at < stale_pending:
                result = await self.release(row.lease_id, "orphaned_pending", now=now)
                (out["released"] if result.get("released") else out["failed"]).append(
                    row.lease_id
                )

        for row in self.list_leases(statuses=["active"]):
            try:
                if row.expires_at and row.expires_at <= now:
                    result = await self.release(row.lease_id, "ttl_expired", now=now)
                    if result.get("released"):
                        out["expired"].append(row.lease_id)
                    else:
                        out["failed"].append(row.lease_id)
                    continue

                # Renewal: corroborated and close enough to expiry that
                # extending now is meaningful (past half the TTL), still
                # under the max-duration cap.
                if row.expires_at and row.started_at:
                    remaining = (row.expires_at - now).total_seconds()
                    if remaining > max(self.config.ttl_seconds, 1) / 2:
                        continue
                    if not signals.is_corroborated(row.attacker_ip, now=now):
                        continue
                    cap = row.started_at + timedelta(
                        seconds=self.config.max_duration_seconds
                    )
                    new_expiry = min(
                        now + timedelta(seconds=self.config.ttl_seconds), cap
                    )
                    if new_expiry <= now:
                        result = await self.release(
                            row.lease_id, "max_duration", now=now
                        )
                        if result.get("released"):
                            out["expired"].append(row.lease_id)
                        else:
                            out["failed"].append(row.lease_id)
                        continue

                    ttl = int((new_expiry - now).total_seconds())
                    scope = self.scope_for(row, ttl)
                    result = await self.backend.steer(scope)
                    if result.get("success"):
                        self._update(
                            row.lease_id,
                            expires_at=new_expiry,
                            ttl_seconds=ttl,
                            renewal_count=int(row.renewal_count or 0) + 1,
                            backend_ref=result.get("backend_ref", row.backend_ref),
                        )
                        out["renewed"].append(row.lease_id)
                    else:
                        out["failed"].append(row.lease_id)
                        logger.warning(
                            "Renewal steer for lease %s failed: %s",
                            row.lease_id,
                            result.get("error"),
                        )
            except Exception as e:  # noqa: BLE001 — one bad lease never stops
                # the sweep; the next tick re-reads it.
                logger.error("Deception sweep failed for lease %s: %s", row.lease_id, e)
                out["failed"].append(row.lease_id)

        return out
