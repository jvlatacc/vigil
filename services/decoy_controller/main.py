"""The decoy-controller HTTP surface.

Five authenticated verb groups plus one unauthenticated health check, per
the spec's controller contract. Auth is a constant-time Bearer-token
comparison; with no token configured every request is denied — an
enforcement plane never trusts whoever can reach the port.

The TTL reaper is the controller-side lease enforcement: one asyncio task,
``sweep_interval`` cadence, removes expired rules from the registry and
syncs the driver. It exists so a redirect's lifetime is enforced by the
component that created it, not by the caller's bookkeeping.
"""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from services.decoy_controller.config import ControllerConfig
from services.decoy_controller.drivers import SteeringDriver, build_driver
from services.decoy_controller.registry import RegistryFull, RuleRegistry

logger = logging.getLogger(__name__)


class SteerBody(BaseModel):
    """The body Vigil's ControllerBackend sends — one lease's scope."""

    lease_id: str = Field(min_length=1, max_length=128)
    source_ip: str
    destination_ips: List[str] = Field(min_length=1, max_length=32)
    ports: List[int] = Field(min_length=1, max_length=64)
    ttl_seconds: int = Field(ge=1, le=7 * 24 * 3600)

    @field_validator("source_ip", "destination_ips")
    @classmethod
    def _routable_ips(cls, value):
        values = [value] if isinstance(value, str) else value
        for item in values:
            try:
                ipaddress.ip_address(item)
            except ValueError as e:
                raise ValueError(f"not a routable IP: {item!r}") from e
        return value

    @field_validator("ports")
    @classmethod
    def _sane_ports(cls, value: List[int]) -> List[int]:
        for port in value:
            if not (1 <= port <= 65535):
                raise ValueError(f"port out of range: {port}")
        return value


class DrainBody(BaseModel):
    reason: str = Field(default="operator kill-switch", max_length=512)


class DecoyController:
    """The service core: registry + driver + the operations they answer."""

    def __init__(self, config: ControllerConfig, driver: SteeringDriver) -> None:
        self.config = config
        self.driver = driver
        self.registry = RuleRegistry(max_rules=config.max_rules)

    async def steer(self, body: SteerBody) -> Dict[str, Any]:
        """Upsert one lease's redirect. Renewal is the same call."""
        ttl = min(body.ttl_seconds, self.config.max_ttl)
        if self.registry.get(body.lease_id) is not None:
            self.registry.renew(body.lease_id, ttl)
        else:
            self.registry.upsert(
                lease_id=body.lease_id,
                source_ip=body.source_ip,
                destination_ips=body.destination_ips,
                ports=body.ports,
                ttl_seconds=ttl,
            )
        refs = await asyncio.to_thread(self.driver.sync, self.registry.all())
        rule = self.registry.get(body.lease_id)
        if rule is None:
            # Unreachable: upsert-or-renew above always leaves a row. A
            # defensive guard keeps the Optional honest.
            raise RuntimeError(f"registry lost lease {body.lease_id} mid-steer")
        ref = refs.get(body.lease_id, "")
        if rule.ref != ref:
            self.registry.set_ref(body.lease_id, ref)
        logger.info(
            "Steered lease %s: %s ports %s -> decoys (ttl %ss)",
            body.lease_id,
            body.source_ip,
            body.ports,
            ttl,
        )
        return {
            "applied": True,
            "lease_id": body.lease_id,
            "ref": ref,
            "ttl_seconds": ttl,
            "ttl_capped": body.ttl_seconds > self.config.max_ttl,
            "expires_at": self.registry.get(body.lease_id).expires_at,  # type: ignore[union-attr]
        }

    async def unsteer(self, lease_id: str) -> Dict[str, Any]:
        """Remove one lease's redirect; removing an unknown lease succeeds."""
        removed_rule = self.registry.remove(lease_id)
        if removed_rule is None:
            return {"removed": False, "lease_id": lease_id}
        await asyncio.to_thread(self.driver.sync, self.registry.all())
        logger.info("Unsteered lease %s", lease_id)
        return {"removed": True, "lease_id": lease_id}

    async def drain(self, reason: str) -> Dict[str, Any]:
        """Remove every rule. The kill-switch path — works alone."""
        removed = self.registry.clear()
        await asyncio.to_thread(self.driver.sync, self.registry.all())
        logger.warning("Drain (%s): removed %d rule(s)", reason, len(removed))
        return {"removed": removed, "count": len(removed), "reason": reason}

    async def reconcile(self) -> Dict[str, Any]:
        """What the controller currently holds — a pure read, idempotent."""
        rules = self.registry.all()
        return {
            "driver": self.driver.name,
            "count": len(rules),
            "rules": [rule.as_dict() for rule in rules],
        }

    async def reap(self, now: Optional[float] = None) -> List[str]:
        """Drop expired leases and converge the plane. Returns their ids."""
        expired = self.registry.expired(now)
        for rule in expired:
            self.registry.remove(rule.lease_id)
        if expired:
            await asyncio.to_thread(self.driver.sync, self.registry.all())
            for rule in expired:
                logger.info("Lease %s expired; redirect removed", rule.lease_id)
        return [rule.lease_id for rule in expired]


def verify_token(token: str, presented: Optional[str]) -> bool:
    """Constant-time comparison — never ``==`` on credentials."""
    if not token or not presented:
        return False
    return hmac.compare_digest(presented, token)


def create_app(
    config: Optional[ControllerConfig] = None,
    driver: Optional[SteeringDriver] = None,
) -> FastAPI:
    """Build the app. ``driver`` injection keeps tests on the memory driver."""
    config = config or ControllerConfig.from_env()
    controller = DecoyController(config, driver or build_driver(config))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if config.boot_drain:
            await asyncio.to_thread(controller.driver.boot)
        reaper = asyncio.create_task(_reap_loop(controller))
        app.state.reaper = reaper
        logger.info(
            "Decoy controller up: driver=%s max_rules=%d max_ttl=%ds token=%s",
            controller.driver.name,
            config.max_rules,
            config.max_ttl,
            "set" if config.token else "NOT SET (all requests denied)",
        )
        yield
        reaper.cancel()

    app = FastAPI(title="Vigil decoy-controller", lifespan=lifespan)

    def require_token(authorization: Optional[str] = Header(default=None)) -> None:
        presented = None
        if authorization:
            scheme, _, credential = authorization.partition(" ")
            if scheme.lower() == "bearer":
                presented = credential.strip()
        if not verify_token(config.token, presented):
            raise HTTPException(
                status_code=401,
                detail="missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        # Unauthenticated on purpose (container healthcheck); deliberately
        # dataless — driver name only, never rule or lease detail.
        return {"status": "ok", "driver": controller.driver.name}

    @app.post("/steer", dependencies=[Depends(require_token)])
    async def steer(body: SteerBody) -> Dict[str, Any]:
        try:
            return await controller.steer(body)
        except RegistryFull as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except RuntimeError as e:
            # Driver/program failure: the plane may not match the registry.
            # 502 — the caller marks the lease failed; routing is fail-open.
            raise HTTPException(status_code=502, detail=f"driver error: {e}") from e

    @app.delete("/steer/{lease_id}", dependencies=[Depends(require_token)])
    async def unsteer(lease_id: str) -> Dict[str, Any]:
        return await controller.unsteer(lease_id)

    @app.get("/steer/{lease_id}", dependencies=[Depends(require_token)])
    async def steer_status(lease_id: str) -> Dict[str, Any]:
        rule = controller.registry.get(lease_id)
        if rule is None:
            raise HTTPException(status_code=404, detail=f"unknown lease: {lease_id}")
        return {"rule": rule.as_dict(), "driver": controller.driver.name}

    @app.get("/reconcile", dependencies=[Depends(require_token)])
    async def reconcile() -> Dict[str, Any]:
        return await controller.reconcile()

    @app.post("/drain", dependencies=[Depends(require_token)])
    async def drain(body: Optional[DrainBody] = None) -> Dict[str, Any]:
        reason = body.reason if body else "operator kill-switch"
        return await controller.drain(reason)

    app.state.controller = controller
    return app


async def _reap_loop(controller: DecoyController) -> None:
    """Controller-side TTL enforcement, forever (cancelled on shutdown)."""
    while True:
        await asyncio.sleep(controller.config.sweep_interval)
        try:
            await controller.reap()
        except Exception:  # noqa: BLE001 — a failed reap must not kill the
            # reaper; expired leases are caught on the next tick.
            logger.exception("TTL reap failed; retrying next tick")


def main() -> None:
    import uvicorn

    config = ControllerConfig.from_env()
    uvicorn.run(
        create_app(config),
        host=config.host,
        port=config.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
