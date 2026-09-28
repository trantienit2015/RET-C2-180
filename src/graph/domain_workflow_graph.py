"""AgentCore Platform v1.0 - RET-C2-180 inner domain workflow graph.

Cat 2 inner graph: skill match + deterministic visa-eligibility check ->
scorecard generation. Instantiated by
HRCandidateScorecardGraphNode.get_subgraph() in graph.py.

Pipeline (linear, fail-fast on ERROR):
    START -> vector_match_eligibility_check -> scorecard_generate -> END
"""

from typing import Any

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from langgraph.graph import END, START

from src.nodes.scorecard_generate_node import ScorecardGenerateNode
from src.nodes.vector_match_node import VectorMatchEligibilityCheckNode
from src.schemas.state import State


class HRCandidateScorecardWorkflowGraph(BaseGraph):
    """Inner graph for the RET-C2-180 candidate-fit scorecard workflow."""

    @property
    def name(self) -> str:
        return "hr-candidate-scorecard-workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # No mandatory config.
        pass

    def register_nodes(self) -> None:
        # No super() - BaseGraph.register_nodes() is abstract.
        self._nodes["vector_match_eligibility_check"] = VectorMatchEligibilityCheckNode()
        self._nodes["scorecard_generate"] = ScorecardGenerateNode()

    def add_edges(self) -> None:
        self._sg.add_edge(START, "vector_match_eligibility_check")
        self._sg.add_conditional_edges(
            "vector_match_eligibility_check",
            lambda s: END if self._is_error(s) else "scorecard_generate",
            {"scorecard_generate": "scorecard_generate", END: END},
        )
        self._sg.add_edge("scorecard_generate", END)

    @staticmethod
    def _is_error(state: AgentState) -> bool:
        return state.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR.value)

    def route(self, state: AgentState) -> str:
        return END if self._is_error(state) else "scorecard_generate"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "requirement_profile": state.get("requirement_profile"),
            "match_result": state.get("match_result"),
            "eligibility_result": state.get("eligibility_result"),
            "scorecard": state.get("scorecard"),
            "output_confidence": state.get("output_confidence"),
            "output": state.get("scorecard"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
