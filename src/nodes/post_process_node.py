"""AgentCore Platform v1.0 - RET-C2-180 ReportFinalizeNode (outer post_process slot).

S-3 output gate: non-suppressible re-check that the scorecard never leaked
raw candidate PII and never contains a "recommended hire: yes/no" automated
decision phrasing (HITL boundary - decision support only). Own-dict field
re-check only (S-3 self-consistency rule).
"""

import re
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.service import detect_candidate_pii

_AUTOMATED_HIRE_DECISION_RE = re.compile(r"(recommended hire|採用(すべき|推奨)|hire\s*[:：]\s*(yes|no))", re.IGNORECASE)


class ReportFinalizeNode(FunctionNode):
    """Validate the scorecard's PII safety and HITL decision-support boundary."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Preparing the result...",
            metadata={"step": "post_process"},
        )
        scorecard = state.get("scorecard", "")
        emit_trace_event(
            "report_finalize_started",
            {"correlation_id": state.get("correlation_id", "")},
            state,
        )

        if detect_candidate_pii(scorecard):
            emit_trace_event("report_finalize_pii_leak_blocked", {}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ReportFinalizeNode: scorecard contains raw candidate-identifying data - blocked (S-3)"],
            }

        if _AUTOMATED_HIRE_DECISION_RE.search(scorecard):
            emit_trace_event("report_finalize_automated_decision_blocked", {}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "ReportFinalizeNode: scorecard contains an automated hiring decision phrase - blocked (HITL boundary)"
                ],
            }

        return {
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """Non-suppressible re-check on the output dict's own field."""
        scorecard = state.get("scorecard", "")
        if detect_candidate_pii(scorecard) or _AUTOMATED_HIRE_DECISION_RE.search(scorecard):
            emit_trace_event("report_finalize_safety_recheck_blocked", {}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "ReportFinalizeNode: S-3 re-check blocked PII leak or automated hiring decision phrasing"
                ],
            }
        return state
