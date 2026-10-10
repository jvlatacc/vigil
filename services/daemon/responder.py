"""Autonomous response handler for the SOC daemon."""

import asyncio
import ipaddress
import logging
import time
from typing import Any, Dict, Optional, Tuple

from core.agents.builtins import AgentId
from core.response.approval_service import (
    ActionStatus,
    ActionType,
    ApprovalService,
    Reversibility,
)
from core.response.autonomous_response_service import AutonomousResponseService
from core.response.config import (
    MtdConfig,
    is_internal_destination,
    is_recon_probe,
    mtd_route_decision,
    response_action_decision,
)
from core.response.guards import origin_statuses_for
from core.storage.connection import get_db_manager
from core.storage.models import MtdDecoyRegistry, MtdIpExclusion
from services.daemon.config import EscalationConfig, ResponseConfig

logger = logging.getLogger(__name__)


def _actionable_ip(value: Any) -> Optional[str]:
    """The host address in ``value``, or None for anything not worth acting on."""
    try:
        ip = ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if (
        ip.is_loopback
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_link_local
        or ip.is_reserved
    ):
        return None
    return str(ip)


def _first_actionable_ip(entity_context: Dict[str, Any]) -> Optional[str]:
    """The first actionable source address in the context, or None.

    The address comes from alert text. Only a routable-looking host address
    is acted on; a malformed or loopback/unspecified one is dropped. For
    honey-routing this is the attacker: the approval row's target and the
    identity its idempotency key names.
    """
    for candidate in entity_context.get("src_ips") or []:
        ip = _actionable_ip(candidate)
        if ip:
            return ip
    return None


def _first_internal_destination(entity_context: Dict[str, Any]) -> Optional[str]:
    """The first internal destination the probe aimed at, or None.

    A probe that scanned several addresses is a candidate through the
    first one of ours it touched; the pure decision re-verifies the
    address with the same predicate.
    """
    destinations = entity_context.get("dest_ips") or entity_context.get("dst_ips") or []
    if not destinations:
        single = entity_context.get("dest_ip") or entity_context.get("dst_ip")
        if single:
            destinations = [single]
    for candidate in destinations:
        ip = str(candidate).strip()
        if is_internal_destination(ip):
            return ip
    return None


def _mtd_ip_excluded(ip: Optional[str]) -> bool:
    """Whether ``ip`` sits on the never-route list, active rows only.

    Fail-closed like the other guard reads in the response path: an
    address whose exclusion status cannot be read is treated as excluded,
    because routing a production host is the one mistake this feature
    does not get to make.
    """
    if not ip:
        return False
    try:
        db = get_db_manager()
        with db.session_scope() as session:
            row = (
                session.query(MtdIpExclusion)
                .filter(MtdIpExclusion.ip == ip, MtdIpExclusion.status == "active")
                .first()
            )
            return row is not None
    except Exception as e:  # noqa: BLE001
        logger.error("Cannot read MTD exclusions; treating %s as excluded: %s", ip, e)
        return True


def _first_active_decoy() -> Optional[Dict[str, str]]:
    """The first active decoy in the registry, or None when it has no candidate.

    Selection is ``decoy_id`` order for determinism. The registry's kinds
    (ssh, http) exist to match the destination service a probe touched,
    but the response path carries no port or protocol identity yet — so
    this picks the first active decoy and records the kind it picked in
    the action's parameters; a kind-aware selection needs that
    destination-service model first.
    """
    try:
        db = get_db_manager()
        with db.session_scope() as session:
            row = (
                session.query(MtdDecoyRegistry)
                .filter(MtdDecoyRegistry.status == "active")
                .order_by(MtdDecoyRegistry.decoy_id)
                .first()
            )
            if row is None:
                return None
            return {
                "decoy_id": row.decoy_id,
                "kind": row.kind,
                "endpoint": row.endpoint,
            }
    except Exception as e:  # noqa: BLE001
        logger.error("Cannot read the MTD decoy registry; treating it as empty: %s", e)
        return None


def _mtd_recommended_verb(finding: Dict[str, Any]) -> str:
    """The verb the MTD band evaluates for this finding.

    Triage's own deceive verb, or the recon reading: T1046/T1595 tags say
    scan whatever calmer word triage chose, so the shared predicate
    upgrades them to deceive. Everything else passes through and is
    refused by the decision on ``mtd.no_deceive_verb``.
    """
    verb = (finding.get("recommended_action") or "").lower()
    if verb == "deceive" or is_recon_probe(finding.get("mitre_predictions") or {}):
        return "deceive"
    return verb


class AutonomousResponder:
    """Handles autonomous response actions with escalation."""

    def __init__(
        self,
        response_config: ResponseConfig,
        escalation_config: EscalationConfig,
        response_service: AutonomousResponseService,
        approvals: ApprovalService,
        mtd_config: Optional[MtdConfig] = None,
    ):
        self.response_config = response_config
        self.escalation_config = escalation_config
        # The MTD band, beside the response band. Default off: None (or an
        # unset MtdConfig) routes nothing and reads nothing.
        self.mtd_config = mtd_config or MtdConfig()
        self.input_queue: asyncio.Queue = asyncio.Queue()

        self._response_service = response_service
        self._approval_service = approvals
        if response_config.force_manual_approval:
            self._approval_service.set_force_manual_approval(True)

        # Stats
        self.stats = {
            "evaluated": 0,
            "auto_executed": 0,
            "reused": 0,
            "pending_approval": 0,
            "escalated": 0,
            "honey_routed": 0,
            "errors": 0,
        }

    async def run(self, shutdown_event: asyncio.Event):
        """Run the response handler loop."""
        logger.info("Autonomous responder starting...")

        # Start worker tasks
        workers = [
            asyncio.create_task(self._response_worker(shutdown_event)),
            asyncio.create_task(self._approved_action_executor(shutdown_event)),
        ]

        await shutdown_event.wait()

        for worker in workers:
            worker.cancel()

        await asyncio.gather(*workers, return_exceptions=True)
        logger.info("Autonomous responder stopped")

    async def _response_worker(self, shutdown_event: asyncio.Event):
        """Process response candidates from queue."""
        while not shutdown_event.is_set():
            try:
                try:
                    item = await asyncio.wait_for(self.input_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if item.get("type") == "response_candidate":
                    await self._evaluate_response(item["finding"])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Response worker error: {e}")
                self.stats["errors"] += 1

    async def _approved_action_executor(self, shutdown_event: asyncio.Event):
        """Periodically execute approved actions."""
        while not shutdown_event.is_set():
            try:
                if self.response_config.auto_response_enabled:
                    # Execute approved actions
                    results = self._response_service.execute_approved_actions()

                    for result in results:
                        if result.get("result", {}).get("success"):
                            self.stats["auto_executed"] += 1
                            logger.info(
                                f"Executed approved action: {result.get('action_id')}"
                            )
                        else:
                            logger.warning(f"Action execution failed: {result}")

            except Exception as e:
                logger.error(f"Action executor error: {e}")

            # Check every 30 seconds
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=30)
                break
            except asyncio.TimeoutError:
                pass

    async def _evaluate_response(self, finding: Dict[str, Any]):
        """Evaluate finding and determine response action."""
        finding_id = finding.get("finding_id", "unknown")
        self.stats["evaluated"] += 1

        logger.debug(f"Evaluating response for finding {finding_id}")

        severity = finding.get("severity", "medium").lower()
        confidence = finding.get("triage_confidence", 0.5)
        recommended_action = finding.get("recommended_action", "").lower()
        entity_context = finding.get("entity_context", {})

        decided = response_action_decision(
            severity, confidence, recommended_action, self.response_config
        )

        if decided:
            response_action, rule = decided

            # Check if escalation is needed
            should_escalate = self._should_escalate(severity, confidence)

            if should_escalate:
                await self._escalate_finding(finding, response_action)

            # Create response action
            if response_action in ["isolate", "block"]:
                await self._create_response_action(
                    finding, response_action, entity_context, rule
                )
        else:
            if not self.response_config.auto_response_enabled:
                logger.debug("Auto-response disabled, skipping")
            else:
                logger.debug(f"No response action needed for {finding_id}")

        # The MTD band sits beside the response band and is evaluated
        # whether or not containment fired: a recon probe is a deception
        # candidate below the containment line, not because of it. With
        # MTD off this returns before reading anything.
        await self._evaluate_mtd_route(finding, confidence)

    def _determine_action(
        self, severity: str, confidence: float, recommended: str
    ) -> Optional[Tuple[str, str]]:
        """``(action, rule)`` from :func:`response_action_decision` (#917)."""
        return response_action_decision(
            severity, confidence, recommended, self.response_config
        )

    def _should_escalate(self, severity: str, confidence: float) -> bool:
        """Determine if finding should be escalated."""
        if not self.escalation_config.enabled:
            return False

        return severity in self.escalation_config.escalate_severities

    async def _escalate_finding(
        self,
        finding: Dict[str, Any],
        action: str,
        guard_rule: Optional[str] = None,
    ):
        """Escalate finding via configured channels.

        ``guard_rule`` carries a guard hold's rationale (#944): the page says
        why auto-response did not act, so the reviewer starts from the gate
        that stopped it.
        """
        finding_id = finding.get("finding_id")
        severity = finding.get("severity", "unknown")
        title = finding.get("title", "Security Alert")

        message = self._build_escalation_message(finding, action)
        if guard_rule:
            message += f"\n\n**Held by guard:** {guard_rule}"

        # Slack escalation
        if self.escalation_config.slack_enabled:
            await self._send_slack_alert(message, severity)

        # PagerDuty escalation
        if self.escalation_config.pagerduty_enabled and severity in [
            "critical",
            "high",
        ]:
            await self._send_pagerduty_alert(title, message, severity)

        self.stats["escalated"] += 1
        logger.info(f"Escalated finding {finding_id} (severity: {severity})")

    def _build_escalation_message(self, finding: Dict[str, Any], action: str) -> str:
        """Build escalation message."""
        entity_context = finding.get("entity_context", {})

        parts = [
            f"**Finding ID:** {finding.get('finding_id')}",
            f"**Severity:** {finding.get('severity', 'unknown').upper()}",
            f"**Title:** {finding.get('title', 'N/A')}",
            f"**Source:** {finding.get('data_source', 'unknown')}",
            f"**Recommended Action:** {action.upper()}",
            "",
            "**Affected Entities:**",
        ]

        if entity_context.get("src_ips"):
            parts.append(f"- IPs: {', '.join(entity_context['src_ips'][:5])}")
        if entity_context.get("hostnames"):
            parts.append(f"- Hosts: {', '.join(entity_context['hostnames'][:5])}")
        if entity_context.get("usernames"):
            parts.append(f"- Users: {', '.join(entity_context['usernames'][:5])}")

        if finding.get("triage_reasoning"):
            parts.extend(["", f"**AI Assessment:** {finding['triage_reasoning']}"])

        return "\n".join(parts)

    async def _send_slack_alert(self, message: str, severity: str):
        """Send alert to Slack."""
        try:
            from core.config import get_integration_config

            config = get_integration_config("slack")
            token = config.get("bot_token")

            if not token:
                logger.warning("Slack not configured, skipping escalation")
                return

            import httpx

            color_map = {
                "critical": "#ff0000",
                "high": "#ff9900",
                "medium": "#ffcc00",
                "low": "#36a64f",
            }

            response = await asyncio.to_thread(
                httpx.post,
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "channel": self.escalation_config.slack_channel,
                    "attachments": [
                        {
                            "color": color_map.get(severity, "#808080"),
                            "title": f"🚨 SOC Alert - {severity.upper()}",
                            "text": message,
                            "footer": "AI-SOC Daemon",
                            "ts": time.time(),
                        }
                    ],
                },
                timeout=30,
                follow_redirects=True,
            )

            if response.status_code == 200 and response.json().get("ok"):
                logger.debug("Slack alert sent successfully")
            else:
                logger.error(f"Slack alert failed: {response.text}")

        except Exception as e:
            logger.error(f"Slack escalation error: {e}")

    async def _send_pagerduty_alert(self, title: str, details: str, severity: str):
        """Send alert to PagerDuty."""
        try:
            from core.config import get_integration_config

            config = get_integration_config("pagerduty")
            routing_key = config.get("routing_key") or config.get("integration_key")

            if not routing_key:
                logger.warning("PagerDuty not configured, skipping escalation")
                return

            import httpx

            pd_severity = self.escalation_config.pagerduty_severity_map.get(
                severity, "warning"
            )

            response = await asyncio.to_thread(
                httpx.post,
                "https://events.pagerduty.com/v2/enqueue",
                json={
                    "routing_key": routing_key,
                    "event_action": "trigger",
                    "payload": {
                        "summary": title,
                        "source": "ai-soc-daemon",
                        "severity": pd_severity,
                        "custom_details": {"details": details},
                    },
                },
                timeout=30,
                follow_redirects=True,
            )

            data = response.json()
            if data.get("status") == "success":
                logger.debug(f"PagerDuty alert triggered: {data.get('dedup_key')}")
            else:
                logger.error(f"PagerDuty alert failed: {data}")

        except Exception as e:
            logger.error(f"PagerDuty escalation error: {e}")

    async def _create_response_action(
        self,
        finding: Dict[str, Any],
        action_type: str,
        entity_context: Dict[str, Any],
        rule: str,
    ):
        """Create a response action (pending or auto-approved)."""
        finding_id = finding.get("finding_id")
        confidence = finding.get("triage_confidence", 0.5)

        # Get target
        hostname = None
        target_ip = _first_actionable_ip(entity_context)
        if entity_context.get("hostnames"):
            hostname = entity_context["hostnames"][0]

        if self.response_config.dry_run:
            # Dry run creates nothing — but it still asks the guards what
            # they would have said (#944, Verification row 8): the operator
            # sees every gate verdict without a containment or a quota slot
            # (spend_quota=False judges the windows, spends nothing).
            verdict = self._response_service.evaluate_guards(
                action_type,
                target_ip,
                hostname,
                origin_statuses_for(finding),
                spend_quota=False,
            )
            logger.info(
                f"[DRY RUN] Guard evaluation for {action_type}: "
                f"{verdict.state.value}; {verdict.rule}"
            )
            logger.info(
                f"[DRY RUN] Would create {action_type} action for finding "
                f"{finding.get('finding_id')}; {rule}"
            )
            return

        if not target_ip and not hostname:
            logger.warning(f"No target available for response action on {finding_id}")
            return

        # Build correlation data
        correlation_data = self._response_service.correlate_alerts(
            tempo_flow_alert=finding
        )

        # Create the action
        result = self._response_service.create_isolation_action(
            ip_address=target_ip or "unknown",
            hostname=hostname,
            confidence=confidence,
            reason=f"Automated response to {finding_id}; {rule}",
            evidence=[finding_id],
            correlation_data=correlation_data,
            evidence_origins=origin_statuses_for(finding),
        )

        if result:
            if result.get("status") == "executed" and result.get("reused"):
                self.stats["reused"] += 1
                logger.info(
                    f"Skipped {action_type} action for {finding_id}: target already isolated"
                )
            elif result.get("status") == "executed":
                self.stats["auto_executed"] += 1
                logger.info(f"Auto-executed {action_type} action for {finding_id}")
            elif result.get("status") == "pending_approval":
                self.stats["pending_approval"] += 1
                logger.info(f"Created pending {action_type} action for {finding_id}")
                # A held action escalates through the same Slack/PagerDuty
                # path as any other finding (#944, D1): the hold itself is
                # the signal — a spoofed finding held by the origin gate
                # usually has no severity worth escalating, and silence
                # would be the drop the guards exist to prevent. While the
                # breaker is OPEN the service claims the escalation once
                # per OPEN period, so a flood cannot page the queue flat.
                guard = result.get("guard")
                if guard and result.get("guard_escalate", False):
                    await self._escalate_finding(
                        finding, action_type, guard_rule=guard.get("rule")
                    )
            else:
                logger.warning(f"Action creation result: {result}")

    async def _evaluate_mtd_route(self, finding: Dict[str, Any], confidence: float):
        """Evaluate the MTD band and propose a honey-route when it fires.

        Runs beside ``response_action_decision`` on every evaluated finding
        while MTD is on, and returns before any read when it is off — a
        default install behaves exactly as before. The exclusion lookup
        runs before the decision because the pure function takes its
        verdict as an argument, and every refusal logs the decision rule
        that refused: an audit line for a route that was never taken.
        """
        if not self.mtd_config.enabled:
            return

        finding_id = finding.get("finding_id", "unknown")
        entity_context = finding.get("entity_context") or {}
        verb = _mtd_recommended_verb(finding)
        dest_ip = _first_internal_destination(entity_context)
        excluded = _mtd_ip_excluded(dest_ip)

        action, rule = mtd_route_decision(
            verb, confidence, dest_ip, self.mtd_config, excluded
        )
        if action != "honey_route":
            logger.info("MTD not routing %s: %s", finding_id, rule)
            return

        attacker_ip = _first_actionable_ip(entity_context)
        if not attacker_ip:
            logger.info("MTD not routing %s: mtd.no_attacker_ip", finding_id)
            return

        decoy = _first_active_decoy()
        if decoy is None:
            logger.info("MTD not routing %s: mtd.no_decoy_available", finding_id)
            return

        await self._create_honey_route_action(
            finding, attacker_ip, decoy, confidence, rule
        )

    async def _create_honey_route_action(
        self,
        finding: Dict[str, Any],
        attacker_ip: str,
        decoy: Dict[str, str],
        confidence: float,
        rule: str,
    ):
        """Create the honey-route proposal the MTD band decided on.

        The row is the decision plane's deliverable: reversible (unroute
        restores the normal path), keyed per attacker so repeated probes
        reuse the idempotent row instead of minting duplicates, and
        carrying the decoy and TTL the enforcement executor will need. No
        executor ships in this slice — an approved row is left for the
        enforcement executor exactly as an unknown action type is left
        for another executor today.
        """
        if self.response_config.dry_run:
            logger.info(
                "[DRY RUN] Would create honey_route action for finding %s "
                "(attacker %s into decoy %s); %s",
                finding.get("finding_id"),
                attacker_ip,
                decoy["decoy_id"],
                rule,
            )
            return

        action = self._approval_service.create_action(
            action_type=ActionType.HONEY_ROUTE,
            title=f"Honey-route {attacker_ip} into decoy environment",
            description=(
                f"Deception routing of a reconnaissance or lateral-movement "
                f"probe into decoy {decoy['decoy_id']} ({decoy['kind']}). The "
                f"attacker's flows are diverted to the decoy; production "
                f"destinations are untouched and the route is reversible."
            ),
            target=attacker_ip,
            confidence=confidence,
            reason=rule,
            evidence=[finding.get("finding_id", "unknown")],
            created_by=AgentId.AUTO_RESPONDER.value,
            parameters={
                "decoy_id": decoy["decoy_id"],
                "finding_id": finding.get("finding_id"),
                "session_ttl_seconds": self.mtd_config.session_ttl_seconds,
            },
            reversibility=Reversibility.REVERSIBLE,
            idempotency_key=f"honey_route:{attacker_ip}",
        )

        if action.status == ActionStatus.PENDING.value:
            self.stats["pending_approval"] += 1
            logger.info(
                "Honey-route %s for %s pending analyst approval",
                action.action_id,
                attacker_ip,
            )
        else:
            self.stats["honey_routed"] += 1
            logger.info(
                "Honey-route %s for %s into %s: %s; awaiting enforcement executor",
                action.action_id,
                attacker_ip,
                decoy["decoy_id"],
                action.status,
            )
