"""AgentCore Platform v1.0 - RET-C2-180 CandidateIngestRequirementLoadNode (outer pre_process slot).

Parse the incoming candidate/requirement payload (JSON-encoded in user_input:
{candidate_id, candidate_skills, required_skills, work_category, weekly_hours,
employer_registered, has_required_docs}). S-2 non-suppressible gate: reject
any raw candidate-identifying field (name/DOB/mynumber/passport/contact) -
this agent processes only anonymised profiles keyed by candidate_id.
"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import to_json
from src.services.service import detect_candidate_pii, normalize_input


class CandidateIngestRequirementLoadNode(FunctionNode):
    """Validate and parse the candidate/requirement payload; reject raw PII."""

    # Spec's original "VERIFIED_INTERNAL" is not a valid TrustLevel enum
    # member. INTERNAL is the correct value: only authenticated HR-system
    # (internal) callers may submit candidate data.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Checking the request...",
            metadata={"step": "pre_process"},
        )
        user_input = state.get("user_input", "")
        emit_trace_event(
            "hr_candidate_ingest_started",
            {"correlation_id": state.get("correlation_id", "")},
            state,
        )

        normalized, error = normalize_input(user_input)
        if error:
            emit_trace_event(
                "hr_candidate_ingest_rejected_invalid_input",
                {"reason": error, "correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"CandidateIngestRequirementLoadNode: {error}"],
            }

        pii_hits = detect_candidate_pii(normalized)
        if pii_hits:
            emit_trace_event(
                "hr_candidate_input_rejected_pii",
                {"reason_count": len(pii_hits), "correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "CandidateIngestRequirementLoadNode: raw candidate-identifying data detected - rejected, not processed"
                ],
            }

        try:
            payload = json.loads(normalized)
        except (TypeError, ValueError):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["CandidateIngestRequirementLoadNode: payload is not valid JSON"],
            }

        candidate_id = payload.get("candidate_id", "")
        if not candidate_id:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["CandidateIngestRequirementLoadNode: candidate_id missing"],
            }

        emit_trace_event("hr_candidate_ingested", {"candidate_id": candidate_id}, state)

        return {
            "candidate_id": candidate_id,
            "requirement_profile": to_json(payload),
            "status": AgentStatus.SUCCESS.value,
        }
