"""AgentCore Platform v1.0 - RET-C2-180 state schema.

Retail HR Candidate Fit & Job Matching Scorecard Report Agent.
Flat TypedDict extension of AgentState (ADR-005). Structured payloads
(dict/list) are JSON-string-encoded before being stored in state fields.

PII SAFETY: candidate_id is a masked/anonymised reference only - raw PII
(name, DOB, mynumber, passport/residence-card number, contact info) MUST
NEVER be stored in State (checkpointed to DB - see the framework rules S-3/S-4).
"""

import json
from typing import Any, NotRequired

from framework.schemas.agent_state import AgentState


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class State(AgentState):
    """Agent state for RET-C2-180.

    candidate_id: masked/anonymised reference only - never raw PII.
    requirement_profile: JSON dict of the target job's requirement profile.
    match_result: JSON dict {skill_match_pct, fit_score, matched_skills, gaps}.
    eligibility_result: JSON dict {eligible, reason, required_docs, conditions}
      - produced by a DETERMINISTIC rule-based check, never LLM-generated
      (immigration eligibility is a legal determination).
    scorecard: JSON dict - the final evidence summary (decision support only,
      never a "recommended hire: yes/no" verdict).
    """

    candidate_id: NotRequired[str]
    requirement_profile: NotRequired[str]
    match_result: NotRequired[str]
    eligibility_result: NotRequired[str]
    scorecard: NotRequired[str]
    output_confidence: NotRequired[float]
