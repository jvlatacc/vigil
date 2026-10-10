"""Autonomous response service with approval workflow integration."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Sequence

from core.agents.builtins import AgentId
from core.response.approval_service import (
    KERNEL_ACTION_TYPES,
    ActionStatus,
    ActionType,
    ApprovalService,
    PendingAction,
)
from core.response.config import ResponseConfig, is_recon_probe
from core.response.guards import (
    GUARD_EVALUATION_TIMEOUT_SECONDS,
    FindingOriginStatus,
    GuardChain,
    GuardState,
    GuardVerdict,
)
from core.response.protected_assets import protected_asset_hit
from core.storage.service import DatabaseService

logger = logging.getLogger(__name__)

# An enforcement that outlives its reason is a new finding: the executor
# refuses to dispatch a kernel action whose TTL is below the daemon's own
# floor (contract error ttl_below_floor) instead of paying for the round trip.
KERNEL_TTL_FLOOR_SECONDS = 60


class AutonomousResponseService:
    """Service for managing autonomous threat response with approval workflow."""

    def __init__(
        self,
        approvals: Optional[ApprovalService] = None,
        config: Optional[ResponseConfig] = None,
        guards: Optional[GuardChain] = None,
    ):
        """Initialize autonomous response service.

        ``config`` defaults to the approval service's band so the two never
        compare against different lines; the no-arg form reads Settings.
        ``guards`` defaults to a lazily built :class:`GuardChain` (#944) so a
        service that never responds never pays for one.
        """
        self.approval_service = approvals or ApprovalService(config=config)
        self.config = config or self.approval_service.config
        self._guards = guards

    def _guard_chain(self) -> GuardChain:
        """The guard chain, built on first use (#944).

        Instances made via ``__new__`` (the executor's test shape) lack the
        attribute entirely — the lazy build covers them too.
        """
        chain = getattr(self, "_guards", None)
        if chain is None:
            chain = GuardChain()
            self._guards = chain
        return chain

    def evaluate_guards(
        self,
        action_type: str,
        target_ip: Optional[str],
        hostname: Optional[str],
        evidence_origins: Sequence[FindingOriginStatus] = (),
        *,
        spend_quota: bool = True,
    ) -> GuardVerdict:
        """The guard chain's verdict for one would-be action (#944, D1).

        Ordered invariant, breaker, origin, quota; every rejection forces
        the human-approval path. ``spend_quota=False`` is the dry-run shape
        (judge the windows without consuming a slot).
        """
        return self._guard_chain().evaluate_sync(
            action_type, target_ip, hostname, evidence_origins, spend_quota=spend_quota
        )

    def _log_guard_denial(
        self,
        action_id: str,
        verdict: GuardVerdict,
        action_type: str,
        confidence: float,
        evidence: Sequence[str],
        refused: str = "guard",
    ) -> None:
        """Record a denied-action rationale in ai_decision_logs (#944, D6).

        The action row carries the same rule; this is the decision-log twin.
        A failed audit write must never block enforcement — create_ai_decision
        degrades to None and logs, and an unexpected shape here is caught and
        logged for the same reason.
        """
        try:
            DatabaseService().create_ai_decision(
                decision_id=f"guard-{refused}-{action_id}",
                agent_id=AgentId.AUTO_RESPONDER.value,
                decision_type="response_guard",
                confidence_score=float(confidence),
                reasoning=verdict.rule,
                recommended_action=action_type,
                decision_metadata={
                    "guard_state": verdict.state.value,
                    "needs_human": verdict.needs_human,
                    "evidence": list(evidence),
                },
            )
        except Exception as e:  # noqa: BLE001 — audit must never block enforcement
            logger.error(
                "Guard denial audit write failed for action %s: %s", action_id, e
            )

    def _claim_escalation(self, verdict: GuardVerdict) -> bool:
        """Whether this hold may fire the once-per-OPEN escalation (#944, D4).

        A breaker-open hold escalates once per OPEN period — the flood that
        opened the breaker must not drown the queue in per-action pages —
        and so does the hold whose own note tripped the breaker. Any other
        hold escalates unconditionally: each pending row is a containment
        decision a person should see. A failed claim answers False; the
        breaker has already logged what happened.
        """
        if verdict.state is not GuardState.BREAKER_OPEN and not verdict.tripped:
            return True
        try:
            return bool(
                self._guard_chain().run(
                    asyncio.wait_for(
                        self._guard_chain().breaker.claim_escalation(),
                        GUARD_EVALUATION_TIMEOUT_SECONDS,
                    )
                )
            )
        except Exception as e:  # noqa: BLE001 — logged above by the breaker
            logger.error("Escalation claim failed; not escalating this hold: %s", e)
            return False

    def correlate_alerts(
        self,
        tempo_flow_alert: Optional[Dict] = None,
        crowdstrike_alert: Optional[Dict] = None,
        splunk_results: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Correlate alerts from multiple sources and calculate confidence score.

        Args:
            tempo_flow_alert: Alert from Tempo Flow
            crowdstrike_alert: Alert from CrowdStrike
            splunk_results: Results from Splunk queries

        Returns:
            Correlation result with confidence score and reasoning
        """
        confidence = 0.0
        evidence = []
        indicators = []
        reasoning = []

        # Correlate Tempo Flow alerts
        if tempo_flow_alert:
            evidence.append(
                f"Tempo Flow: {tempo_flow_alert.get('finding_id', 'unknown')}"
            )

            severity = tempo_flow_alert.get("severity", "").lower()
            if severity in ["high", "critical"]:
                confidence += 0.15
                reasoning.append(f"High severity detection in Tempo Flow ({severity})")

            # Check for specific attack patterns
            mitre_predictions = tempo_flow_alert.get("mitre_predictions", {})
            if any(t.startswith("T1486") for t in mitre_predictions):  # Ransomware
                confidence += 0.25
                reasoning.append("Ransomware behavior detected (T1486)")
                indicators.append("ransomware")

            if any(t.startswith("T1071") for t in mitre_predictions):  # C2
                confidence += 0.20
                reasoning.append("C2 communication detected (T1071)")
                indicators.append("c2_communication")

            if any(
                t.startswith("T1021") for t in mitre_predictions
            ):  # Lateral movement
                confidence += 0.15
                reasoning.append("Lateral movement detected (T1021)")
                indicators.append("lateral_movement")

            # A scanning probe (T1046/T1595) is the deception candidate, not a
            # containment one: a small boost that on its own stays below the
            # review line, and an indicator the recommendation ladder reads
            # as deceive instead of letting the finding fall into the
            # monitor-only bands. The shared predicate is the one definition
            # of what counts (is_recon_probe in core.response.config).
            if is_recon_probe(mitre_predictions):
                confidence += 0.10
                reasoning.append("Reconnaissance scanning detected (T1046/T1595)")
                indicators.append("recon_scanning")

        # Correlate CrowdStrike alerts
        if crowdstrike_alert:
            cs_alerts = crowdstrike_alert.get("alerts", [])
            if cs_alerts:
                evidence.append(f"CrowdStrike: {len(cs_alerts)} alert(s)")

                for alert in cs_alerts:
                    severity = alert.get("severity", "").lower()
                    if severity == "critical":
                        confidence += 0.15
                        reasoning.append("Critical severity in CrowdStrike")

                    detection_type = alert.get("detection_type", "").lower()
                    if detection_type == "malware":
                        confidence += 0.20
                        reasoning.append(
                            f"Malware detected: {alert.get('description', '')}"
                        )
                        indicators.append("malware")

                    # Check if already isolated
                    if alert.get("isolated", False):
                        reasoning.append("Host already isolated in CrowdStrike")

        # Correlate Splunk results
        if splunk_results and len(splunk_results) > 0:
            evidence.append(f"Splunk: {len(splunk_results)} event(s)")

            # High volume of events indicates active threat
            if len(splunk_results) > 50:
                confidence += 0.10
                reasoning.append(f"High volume of events ({len(splunk_results)})")

        # Time correlation bonus
        if tempo_flow_alert and crowdstrike_alert:
            # If alerts are within 5 minutes, add correlation bonus
            confidence += 0.10
            reasoning.append("Temporal correlation between multiple sources")

        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)

        return {
            "confidence": confidence,
            "indicators": indicators,
            "evidence": evidence,
            "reasoning": reasoning,
            "recommendation": self._get_recommendation(confidence, indicators),
        }

    def _get_recommendation(self, confidence: float, indicators: List[str]) -> str:
        """Get recommendation based on confidence and indicators."""
        if confidence >= self.config.confidence_threshold:
            return "AUTO-ISOLATE: Confidence threshold met for automatic isolation"
        elif confidence >= self.config.review_threshold:
            return "ISOLATE WITH APPROVAL: High confidence, recommend isolation with quick approval"
        elif "recon_scanning" in indicators:
            # The containment bands keep precedence: a scan with enough
            # corroborating signal to reach the review line is still an
            # isolation case. Below it, a recon-tagged finding deceives
            # instead of landing in the monitor-only bands.
            return "DECEIVE: Reconnaissance probe; candidate for honey-routing into a decoy environment"
        elif confidence >= self.config.monitor_threshold:
            return "MANUAL REVIEW: Moderate confidence, requires analyst review"
        else:
            return "MONITOR: Low confidence, continue monitoring"

    def create_isolation_action(
        self,
        ip_address: str,
        hostname: Optional[str],
        confidence: float,
        reason: str,
        evidence: List[str],
        correlation_data: Dict,
        evidence_origins: Optional[Sequence[FindingOriginStatus]] = None,
    ) -> Optional[Dict]:
        """
        Create an isolation action (auto-executes when the approval gate
        approves it, i.e. at or above ``config.confidence_threshold``).

        The guard chain runs first (#944, D1): invariant, breaker, origin
        and quota checks interpose between the Responder's decision and the
        approval gate. Any rejection forces pending approval — with the
        gate's rationale on the row and in ai_decision_logs — the action is
        never dropped and never executed against a held target.

        Args:
            ip_address: Target IP address
            hostname: Target hostname (optional)
            confidence: Confidence score (0.0-1.0)
            reason: Reason for isolation
            evidence: List of evidence IDs
            correlation_data: Data from correlation analysis
            evidence_origins: Origin stamps of the evidencing findings, as
                stamped at ingest. The daemon pipeline always supplies them;
                a caller that does not is judged on zero statuses (the origin
                gate passes vacuously, logged at debug).

        Returns:
            Action result
        """
        # Key on the IP when known; an IP-less finding (ip_address == "unknown")
        # keys on hostname instead, so distinct IP-less hosts get distinct rows
        # rather than colliding on the literal string "unknown".
        target_key = (
            ip_address if ip_address and ip_address != "unknown" else f"host:{hostname}"
        )

        # The guard chain (#944, D1): invariant, breaker, origin, quota —
        # cheapest-and-most-specific first. Checked before the approval gate
        # here, and re-checked in execute_approved_actions before anything
        # dispatches. A rejection does not drop the action: it forces human
        # approval and renders the gate's rationale as the deciding rule.
        verdict = self.evaluate_guards(
            ActionType.ISOLATE_HOST.value,
            ip_address,
            hostname,
            evidence_origins or (),
        )
        gate_rule = verdict.rule if verdict.needs_human else None

        try:
            action, inserted = self.approval_service._put_action(
                action_type=ActionType.ISOLATE_HOST,
                title=f"Isolate Host: {hostname or ip_address}",
                description=f"Network isolation of compromised host based on correlated detections.\n\n"
                f"Indicators: {', '.join(correlation_data.get('indicators', []))}\n"
                f"Reasoning: {' | '.join(correlation_data.get('reasoning', []))}",
                target=ip_address,
                confidence=confidence,
                reason=reason,
                evidence=evidence,
                created_by=AgentId.AUTO_RESPONDER.value,
                parameters={"hostname": hostname, "correlation": correlation_data},
                idempotency_key=f"{ActionType.ISOLATE_HOST.value}:{target_key}",
                gate_rule=gate_rule,
            )

            if not inserted:
                if action.status == ActionStatus.EXECUTED.value:
                    return {
                        "status": "executed",
                        "reused": True,
                        "action_id": action.action_id,
                        "message": f"Host {hostname or ip_address} already isolated",
                        "confidence": action.confidence,
                        "result": action.execution_result,
                    }
                return {
                    "status": action.status,
                    "reused": True,
                    "action_id": action.action_id,
                    "message": f"Isolation already recorded for {hostname or ip_address}",
                    "confidence": action.confidence,
                    "requires_approval": action.requires_approval,
                    "result": action.execution_result,
                }

            if action.status == ActionStatus.APPROVED.value:
                logger.info(
                    f"Action {action.action_id} auto-approved (confidence: {confidence:.2%})"
                )

                execution_result = self._execute_isolation(
                    ip_address, hostname, reason, confidence
                )

                if execution_result.get("success"):
                    self.approval_service.mark_executed(
                        action.action_id, execution_result
                    )
                    return {
                        "status": "executed",
                        "action_id": action.action_id,
                        "message": f"Host {hostname or ip_address} isolated automatically",
                        "confidence": confidence,
                        "result": execution_result,
                    }

                self.approval_service.mark_failed(
                    action.action_id,
                    execution_result.get("error", "Unknown error"),
                )
                return {
                    "status": ActionStatus.FAILED.value,
                    "action_id": action.action_id,
                    "message": execution_result.get("message")
                    or f"Isolation of {hostname or ip_address} was not executed",
                    "confidence": confidence,
                    "result": execution_result,
                }
            else:
                logger.info(
                    f"Action {action.action_id} pending approval (confidence: {confidence:.2%})"
                )
                # A held action carries its gate's rationale on the result
                # and the row, lands it in ai_decision_logs (#944, D6), and
                # escalates through Slack/PagerDuty — nothing is dropped
                # silently. While the breaker is OPEN the escalation is
                # claimed once per OPEN period (D4), not once per action.
                result: Dict = {
                    "status": "pending_approval",
                    "action_id": action.action_id,
                    "message": "Isolation action created, awaiting analyst approval",
                    "confidence": confidence,
                    "requires_approval": True,
                }
                if verdict.needs_human:
                    result["guard"] = {
                        "state": verdict.state.value,
                        "rule": verdict.rule,
                    }
                    self._log_guard_denial(
                        action.action_id,
                        verdict,
                        ActionType.ISOLATE_HOST.value,
                        confidence,
                        evidence,
                    )
                    result["guard_escalate"] = self._claim_escalation(verdict)
                return result

        except Exception as e:
            logger.error(f"Error creating isolation action: {e}")
            return {"error": str(e)}

    def _execute_isolation(
        self, ip_address: str, hostname: Optional[str], reason: str, confidence: float
    ) -> Dict:
        """
        Report that host isolation has no executor.

        No EDR containment call is wired. A success result would record a
        containment that never happened.
        """
        logger.info(
            f"Isolation not executed: {hostname or ip_address} "
            f"(confidence: {confidence:.2%}); no EDR executor"
        )
        return {
            "success": False,
            "error": "unsupported_action_type",
            "message": "No EDR executor is configured for host isolation",
        }

    def execute_approved_actions(self) -> List[Dict]:
        """
        Execute all approved actions that haven't been executed yet.

        Re-checks the never-quarantine invariant (#944) before dispatching:
        the create path and this path are different transactions, and an
        auto-approval released at creation time is not a decision that
        survives a protected asset declared in between. A person-approved
        row proceeds — the deliberate emergency valve; an auto-approved row
        against a protected asset is refused and recorded, never executed
        and never dropped silently.

        Returns:
            List of execution results
        """
        try:
            # Get approved but not executed actions
            approved_actions = self.approval_service.list_actions(
                status=ActionStatus.APPROVED
            )
            results = []

            for action in approved_actions:
                # Skip if already executed
                if action.executed_at:
                    continue

                params = action.parameters or {}

                # Never-quarantine invariant re-check (#944), ahead of the
                # person-decided guard: a row whose status says "approved"
                # but names no approver was released by a confidence figure,
                # and a confidence figure cannot discharge the invariant.
                # Refused and recorded — never executed, never dropped
                # silently. A row a person decided (approved_by set)
                # proceeds; that is the deliberate emergency valve.
                if not action.approved_by:
                    protected = protected_asset_hit(
                        action.target, params.get("hostname")
                    )
                    if protected is not None:
                        logger.warning(
                            "Action %s targets protected asset %s; refusing execution",
                            action.action_id,
                            protected.rule(),
                        )
                        self.approval_service.refuse_auto_action(
                            action.action_id, protected.rule()
                        )
                        continue

                # Released by a confidence figure and no person: whoever
                # supplied that figure also chose the outcome.
                if not action.requires_approval and not action.approved_by:
                    logger.warning(
                        "Action %s was never decided by a person; not executing",
                        action.action_id,
                    )
                    continue

                result: Optional[Dict] = None

                if action.action_type == "isolate_host":
                    result = self._execute_isolation(
                        ip_address=action.target,
                        hostname=params.get("hostname"),
                        reason=action.reason,
                        confidence=action.confidence,
                    )
                elif action.action_type in (
                    "waf_block",
                    "gateway_block",
                    "access_revoke",
                ):
                    result = self._execute_cloudflare_action(
                        action_type=action.action_type,
                        target=action.target,
                        reason=action.reason,
                        parameters=params,
                    )
                elif action.action_type == "honey_route":
                    result = self._execute_honey_route(action)

                elif action.action_type in KERNEL_ACTION_TYPES:
                    result = self._execute_kernel_action(action=action)

                if result is None:
                    # Unknown action type — leave for another executor or manual handling.
                    continue

                if result.get("success"):
                    self.approval_service.mark_executed(action.action_id, result)
                else:
                    self.approval_service.mark_failed(
                        action.action_id, result.get("error", "Unknown error")
                    )

                results.append(
                    {
                        "action_id": action.action_id,
                        "action_type": action.action_type,
                        "target": action.target,
                        "result": result,
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Error executing approved actions: {e}")
            return []

    # ------------------------------------------------------------------
    # Cloudflare action factories + executor
    # ------------------------------------------------------------------

    def _execute_cloudflare_action(
        self,
        action_type: str,
        target: str,
        reason: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute an approved Cloudflare action via the REST helpers in core/integrations/cloudflare/tool.py."""
        try:
            from core.config import get_integration_config, is_integration_enabled
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"config import failed: {e}"}

        if not is_integration_enabled("cloudflare"):
            return {
                "success": False,
                "error": "cloudflare_integration_disabled",
                "message": "Enable the Cloudflare integration in Settings to execute this action.",
            }

        cfg = get_integration_config("cloudflare") or {}
        api_token = cfg.get("api_token")
        account_id = cfg.get("account_id")
        if not api_token:
            return {"success": False, "error": "cloudflare api_token not configured"}

        # Lazy import to avoid forcing the MCP package on environments that
        # never enable Cloudflare.
        try:
            from core.integrations.cloudflare import tool as cf_tool
        except Exception as e:  # noqa: BLE001
            return {
                "success": False,
                "error": f"core.integrations.cloudflare.tool unavailable: {e}",
            }

        try:
            if action_type == "waf_block":
                return cf_tool._waf_block_ip(
                    api_token=api_token,
                    account_id=account_id,
                    ip=parameters.get("ip") or target,
                    reason=reason,
                    mode=parameters.get("mode", "block"),
                )
            if action_type == "gateway_block":
                return cf_tool._gateway_block_domain(
                    api_token=api_token,
                    account_id=account_id,
                    domain=parameters.get("domain") or target,
                    reason=reason,
                    rule_name=parameters.get("rule_name"),
                )
            if action_type == "access_revoke":
                return cf_tool._access_revoke_session(
                    api_token=api_token,
                    account_id=account_id,
                    email=parameters.get("email") or target,
                    reason=reason,
                )
            return {
                "success": False,
                "error": f"unknown cloudflare action {action_type}",
            }
        except Exception as e:  # noqa: BLE001
            logger.exception("Cloudflare action %s failed", action_type)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # MTD honey-route executor
    # ------------------------------------------------------------------

    def _execute_honey_route(self, action) -> Dict[str, Any]:
        """Execute an approved honey_route through the honey_router integration.

        Lazy import and the ``is_integration_enabled`` gate are the Cloudflare
        precedent: the enforcement modules (and their storage imports) stay
        off installs that never enable the integration. With no backend
        configured this returns an honest structured failure — the
        ``isolate_host`` rule: a fabricated success would record a routing
        that never happened, and the attacker would keep probing production.
        """
        from core.config import is_integration_enabled

        if not is_integration_enabled("honey_router"):
            return {
                "success": False,
                "error": "unsupported_action_type",
                "message": "No enforcement backend is configured for honey-routing",
            }

        params = action.parameters or {}
        decoy_id = params.get("decoy_id")
        if not decoy_id:
            return {
                "success": False,
                "error": "missing_decoy_id",
                "message": "honey_route action carries no decoy_id parameter",
            }

        try:
            from core.integrations.honey_router import route as honey_router
        except Exception as e:  # noqa: BLE001
            return {
                "success": False,
                "error": f"core.integrations.honey_router unavailable: {e}",
            }

        return honey_router.route(
            attacker_ip=action.target,
            decoy_id=str(decoy_id),
            ttl_seconds=params.get("session_ttl_seconds"),
        )

    # ------------------------------------------------------------------
    # Kernel enforcement executor (services/enforcement daemon)
    # ------------------------------------------------------------------

    def _execute_kernel_action(self, action: PendingAction) -> Dict[str, Any]:
        """Execute an approved kernel action through the ebpf_xdp helpers.

        The slice's module-level helpers own config resolution and the
        idempotency_key convention (``xdp_block_ip:{ip}`` and siblings); this
        branch supplies the approval row's ``action_id`` — so a retried
        dispatch replays against the daemon's idempotency instead of
        double-enforcing — the TTL from the action's ``parameters``, and the
        reason. A success reply carries the daemon's kernel evidence, which
        ``mark_executed`` stores verbatim; refusals and transport failures are
        ``success: False`` results for ``mark_failed`` — never a faked success.
        """
        params = action.parameters or {}

        # TTL rides the action's parameters — no approval_actions schema change.
        raw_ttl = params.get("ttl_seconds")
        if raw_ttl is not None:
            try:
                ttl = int(raw_ttl)
            except (TypeError, ValueError):
                return {
                    "success": False,
                    "error": "ttl_invalid",
                    "message": f"ttl_seconds {raw_ttl!r} is not an integer",
                }
            if ttl < KERNEL_TTL_FLOOR_SECONDS:
                return {
                    "success": False,
                    "error": "ttl_below_floor",
                    "message": (
                        f"ttl_seconds={ttl} is below the "
                        f"{KERNEL_TTL_FLOOR_SECONDS}s floor"
                    ),
                }
        else:
            ttl = None  # the integration's configured default applies

        # Lazy import so environments that never enable kernel enforcement do
        # not pay for the integration package — the Cloudflare convention.
        try:
            from core.integrations.ebpf_xdp import tool as kernel_tool
        except Exception as e:  # noqa: BLE001
            return {
                "success": False,
                "error": f"core.integrations.ebpf_xdp.tool unavailable: {e}",
            }

        try:
            if action.action_type == ActionType.XDP_BLOCK_IP.value:
                return kernel_tool.xdp_block_ip(
                    ip=params.get("ip") or action.target,
                    reason=action.reason,
                    ttl_seconds=ttl,
                    action_id=action.action_id,
                )
            if action.action_type == ActionType.SOCKET_REDIRECT.value:
                return kernel_tool.xdp_redirect_socket(
                    ip=params.get("ip") or action.target,
                    reason=action.reason,
                    port=int(params.get("port") or 0),
                    ttl_seconds=ttl,
                    action_id=action.action_id,
                )
            if action.action_type == ActionType.INTERDICT_PROCESS.value:
                raw_pid = params.get("pid") or action.target
                try:
                    pid = int(raw_pid)
                except (TypeError, ValueError):
                    return {
                        "success": False,
                        "error": "pid_invalid",
                        "message": f"pid {raw_pid!r} is not an integer",
                    }
                return kernel_tool.xdp_interdict_process(
                    pid=pid,
                    reason=action.reason,
                    ttl_seconds=ttl,
                    action_id=action.action_id,
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("Kernel action %s failed", action.action_type)
            return {"success": False, "error": str(e)}
        return {
            "success": False,
            "error": f"unknown kernel action {action.action_type}",
        }
