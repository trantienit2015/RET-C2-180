"""AgentCore Platform v1.0 - RET-C2-180 VectorMatchEligibilityCheckNode (inner node).

Compute the candidate-requirement skill match, then run the DETERMINISTIC
育成就労 visa-eligibility rule check via eligibility_rules_tool() (a Tool
call, never LLM-generated - immigration eligibility is a legal
determination).
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import compute_skill_match, detect_candidate_pii, eligibility_rules_tool


class VectorMatchEligibilityCheckNode(FunctionNode):
    """Compute skill-match score and deterministic visa-eligibility verdict."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Inner subgraph seeds "user_input" (BaseGraph.invoke()), not
        # "requirement_profile" - only the outer graph's
        # CandidateIngestRequirementLoadNode sets that field, and outer state
        # fields do not cross the GraphNode subgraph boundary.
        emit_trace_event(
            "hr_candidate_vector_match_started",
            {"correlation_id": state.get("correlation_id", "")},
            state,
        )
        requirement_profile_raw = state.get("requirement_profile") or state.get("user_input", "")

        # pre_process -> main is unconditional: re-check raw candidate-PII
        # here too, don't trust that the outer node's rejection actually
        # stopped the pipeline before reaching this node.
        if isinstance(requirement_profile_raw, str):
            pii_hits = detect_candidate_pii(requirement_profile_raw)
            if pii_hits:
                emit_trace_event(
                    "hr_candidate_input_rejected_pii_inner_recheck", {"reason_count": len(pii_hits)}, state
                )
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [
                        "VectorMatchEligibilityCheckNode: raw candidate-identifying data detected - rejected, not processed"
                    ],
                }

        payload = (
            from_json(requirement_profile_raw, None)
            if isinstance(requirement_profile_raw, str)
            else requirement_profile_raw
        )

        if not payload:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "VectorMatchEligibilityCheckNode: requirement_profile missing - upstream not trusted blindly"
                ],
            }

        match_result = compute_skill_match(payload.get("candidate_skills", []), payload.get("required_skills", []))

        eligibility_result = None
        if "work_category" in payload:
            eligibility_result = eligibility_rules_tool(
                work_category=payload.get("work_category", ""),
                weekly_hours=payload.get("weekly_hours", 0),
                employer_registered=payload.get("employer_registered", False),
                has_required_docs=payload.get("has_required_docs", False),
            )

        return {
            "requirement_profile": to_json(payload),
            "match_result": to_json(match_result),
            "eligibility_result": to_json(eligibility_result),
            "status": AgentStatus.SUCCESS.value,
        }
