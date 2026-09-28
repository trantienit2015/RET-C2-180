"""AgentCore Platform v1.0 - RET-C2-180 outer graph (Cat 2).

Cat 2: outer AgentBaseGraph with the fixed 5-node backbone. Domain complexity
is encapsulated in HRCandidateScorecardGraphNode (the `main` slot), which
wraps the inner HRCandidateScorecardWorkflowGraph. Do NOT override
add_edges().

Backbone: initialize -> pre_process(CandidateIngestRequirementLoad) -> main(GraphNode)
          -> post_process(ReportFinalize) -> finalize

HRCandidateScorecardGraphNode lives here (not under src/nodes/) - the PB-6
invoke-order test only discovers BaseNode subclasses under src/nodes/, and a
GraphNode's __call__ intentionally skips the standard S-2/S-4/S-3 lifecycle
(gating is delegated to the inner subgraph).
"""

from typing import Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.post_process_node import ReportFinalizeNode
from src.nodes.pre_process_node import CandidateIngestRequirementLoadNode
from src.schemas.state import State


class HRCandidateScorecardGraphNode(GraphNode):
    """Wraps the inner HR candidate-fit scorecard workflow (Cat 2 composition)."""

    # S-1: outer main-slot wrapper is the first node to receive the caller's
    # input - must match config/agent.yaml's agent-level required_trust_level
    # (INTERNAL: only authenticated internal HR-system callers), not the
    # inner subgraph's ANONYMOUS default.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL
    # "propagate": re-raise inner errors as SubgraphError (fail fast - default).
    error_strategy: ClassVar[str] = "propagate"
    # No HITL in this template - decision-support boundary is enforced via
    # the S-3 output gate (no automated hiring action), not an interrupt.
    propagate_hitl: ClassVar[bool] = False

    def get_subgraph(self) -> AgentBaseGraph:
        from src.graph.domain_workflow_graph import HRCandidateScorecardWorkflowGraph

        sg = HRCandidateScorecardWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # Progress (non-terminal) event for the caller, emitted as the subgraph step
        # begins. Outside the Marketplace runtime this is a no-op emitter.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Working on the request...",
            metadata={"step": "main"},
        )
        emit_trace_event(
            "hr_candidate_scorecard_workflow_dispatched", {"correlation_id": state.get("correlation_id", "")}, state
        )
        value = state.get("requirement_profile", state.get("user_input", ""))
        return value if isinstance(value, str) else str(value)

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "hr_candidate_scorecard_workflow_completed",
            {"correlation_id": state.get("correlation_id", ""), "status": str(sub_result.get("status"))},
            state,
        )
        return {
            "requirement_profile": sub_result.get("requirement_profile"),
            "match_result": sub_result.get("match_result"),
            "eligibility_result": sub_result.get("eligibility_result"),
            "scorecard": sub_result.get("scorecard"),
            "output_confidence": sub_result.get("output_confidence"),
            "result": sub_result.get("output"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {}


class RETHRCandidateScorecardAgent(AgentBaseGraph):
    """RET-C2-180 - Retail HR Candidate Fit & Job Matching Scorecard Report Agent (Cat 2)."""

    @property
    def name(self) -> str:
        return "ret-c2-180"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize + finalize

        self._nodes["pre_process"] = CandidateIngestRequirementLoadNode()
        self._nodes["main"] = HRCandidateScorecardGraphNode()
        self._nodes["post_process"] = ReportFinalizeNode()

    # add_edges() is NOT overridden - backbone wiring belongs to the framework.


# Stable alias for the standalone entry point import (src/api/server.py).
Graph = RETHRCandidateScorecardAgent
