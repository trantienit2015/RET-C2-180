"""AgentCore Platform v1.0 - RET-C2-180 ScorecardGenerateNode (inner node).

Format the final fit-evidence scorecard around the deterministic match and
eligibility results via format_scorecard() - a deterministic, template-based
formatter (src/services/service.py), not an LLM call. It never generates the
eligibility verdict itself and never emits a "recommended hire" phrase.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import compute_confidence, format_scorecard


class ScorecardGenerateNode(FunctionNode):
    """Generate the fit-evidence scorecard (decision support only)."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # The outer pre_process node's candidate_id does not cross the
        # GraphNode subgraph boundary (only requirement_profile/user_input
        # do - the inner graph only receives the extract_input() payload). Fall
        # back to re-deriving it from requirement_profile inside the inner
        # graph.
        candidate_id = state.get("candidate_id") or from_json(state.get("requirement_profile"), {}).get(
            "candidate_id", ""
        )
        match_result = from_json(state.get("match_result"), {})
        eligibility_result = from_json(state.get("eligibility_result"), None)

        if not candidate_id:
            emit_trace_event("scorecard_error", {"reason": "missing_candidate_id"}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ScorecardGenerateNode: candidate_id missing - upstream not trusted blindly"],
            }

        scorecard = format_scorecard(candidate_id, match_result, eligibility_result)
        confidence = compute_confidence(match_result)

        emit_trace_event("scorecard_generated", {"candidate_id": candidate_id, "confidence": confidence}, state)

        return {
            "scorecard": to_json(scorecard),
            "output_confidence": confidence,
            "status": AgentStatus.SUCCESS.value,
        }
