# RET-C2-180 - Unit tests: per-node success + error/edge paths.

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.pre_process_node import CandidateIngestRequirementLoadNode
from src.nodes.post_process_node import ReportFinalizeNode
from src.nodes.scorecard_generate_node import ScorecardGenerateNode
from src.nodes.vector_match_node import VectorMatchEligibilityCheckNode
from src.schemas.state import from_json, to_json

ELIGIBLE_PAYLOAD = {
    "candidate_id": "CAND-001",
    "candidate_skills": ["cash_register", "customer_service", "inventory"],
    "required_skills": ["cash_register", "customer_service", "inventory", "shift_scheduling"],
    "work_category": "retail",
    "weekly_hours": 30,
    "employer_registered": True,
    "has_required_docs": True,
}

INELIGIBLE_PAYLOAD = {**ELIGIBLE_PAYLOAD, "work_category": "office admin"}


class TestCandidateIngestRequirementLoadNode:
    def test_success(self):
        state = {"user_input": json.dumps(ELIGIBLE_PAYLOAD)}
        r = CandidateIngestRequirementLoadNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["candidate_id"] == "CAND-001"

    def test_empty_input_error(self):
        assert CandidateIngestRequirementLoadNode().execute({"user_input": ""})["status"] == AgentStatus.ERROR

    def test_raw_name_pii_rejected(self):
        state = {"user_input": '{"氏名": "山田太郎", "candidate_id": "CAND-002"}'}
        assert CandidateIngestRequirementLoadNode().execute(state)["status"] == AgentStatus.ERROR

    def test_mynumber_like_rejected(self):
        state = {"user_input": '{"note": "1234 5678 9012", "candidate_id": "CAND-003"}'}
        assert CandidateIngestRequirementLoadNode().execute(state)["status"] == AgentStatus.ERROR

    def test_invalid_json_error(self):
        assert CandidateIngestRequirementLoadNode().execute({"user_input": "not json"})["status"] == AgentStatus.ERROR

    def test_missing_candidate_id_error(self):
        state = {"user_input": json.dumps({"candidate_skills": []})}
        assert CandidateIngestRequirementLoadNode().execute(state)["status"] == AgentStatus.ERROR


class TestVectorMatchEligibilityCheckNode:
    def test_success_eligible(self):
        state = {"requirement_profile": to_json(ELIGIBLE_PAYLOAD)}
        r = VectorMatchEligibilityCheckNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        eligibility = from_json(r["eligibility_result"], {})
        assert eligibility["eligible"] is True

    def test_ineligible_work_category(self):
        state = {"requirement_profile": to_json(INELIGIBLE_PAYLOAD)}
        r = VectorMatchEligibilityCheckNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        eligibility = from_json(r["eligibility_result"], {})
        assert eligibility["eligible"] is False
        assert "work_category" in eligibility["reason"]

    def test_missing_requirement_profile_error(self):
        assert VectorMatchEligibilityCheckNode().execute({"requirement_profile": None, "user_input": ""})["status"] == AgentStatus.ERROR


class TestScorecardGenerateNode:
    def test_success_no_hire_phrase(self):
        match_result = {"skill_match_pct": 75.0, "fit_score": 0.75, "matched_skills": ["cash_register"], "gaps": ["shift_scheduling"]}
        state = {
            "candidate_id": "CAND-001",
            "match_result": to_json(match_result),
            "eligibility_result": to_json({"eligible": True, "reason": "ok", "required_docs": [], "conditions": []}),
        }
        r = ScorecardGenerateNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert "recommended hire" not in r["scorecard"].lower()

    def test_missing_candidate_id_error(self):
        state = {"candidate_id": "", "match_result": to_json({}), "eligibility_result": to_json(None)}
        assert ScorecardGenerateNode().execute(state)["status"] == AgentStatus.ERROR


class TestReportFinalizeNode:
    def test_success(self):
        state = {"scorecard": '{"candidate_id": "CAND-001", "fit_evidence": {}}'}
        r = ReportFinalizeNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS

    def test_extra_gate_blocks_pii_leak(self):
        bad_state = {"scorecard": '{"氏名": "山田太郎"}'}
        out = ReportFinalizeNode()._extra_security_gate_output(bad_state)
        assert out["status"] == AgentStatus.ERROR

    def test_extra_gate_blocks_automated_decision_phrase(self):
        bad_state = {"scorecard": '{"verdict": "recommended hire: yes"}'}
        out = ReportFinalizeNode()._extra_security_gate_output(bad_state)
        assert out["status"] == AgentStatus.ERROR

    def test_extra_gate_passthrough_clean_scorecard(self):
        good_state = {"scorecard": '{"candidate_id": "CAND-001", "fit_evidence": {}}'}
        assert ReportFinalizeNode()._extra_security_gate_output(good_state) is good_state


# S-1 trust-gate reject coverage — S-1 trust-gate reject coverage.
# CandidateIngestRequirementLoadNode, VectorMatchEligibilityCheckNode, ScorecardGenerateNode,
# ReportFinalizeNode all declare required_trust_level=INTERNAL, but existing tests above call
# .execute(state) directly, bypassing BaseNode.__call__()'s S-1 trust gate.
class TestTrustGateReject:
    def test_candidate_ingest_rejects_insufficient_trust(self):
        state = {"user_input": json.dumps(ELIGIBLE_PAYLOAD), "caller_trust_level": TrustLevel.ANONYMOUS.value}
        result = CandidateIngestRequirementLoadNode()(state)
        assert str(result["status"]).lower().endswith("error")
        assert any("trust gate denied" in msg.lower() for msg in result.get("error_log", []))

    def test_candidate_ingest_succeeds_with_sufficient_trust(self):
        state = {"user_input": json.dumps(ELIGIBLE_PAYLOAD), "caller_trust_level": TrustLevel.INTERNAL.value}
        result = CandidateIngestRequirementLoadNode()(state)
        assert result["status"] == AgentStatus.SUCCESS.value

    def test_vector_match_rejects_insufficient_trust(self):
        state = {"requirement_profile": to_json(ELIGIBLE_PAYLOAD), "caller_trust_level": TrustLevel.ANONYMOUS.value}
        result = VectorMatchEligibilityCheckNode()(state)
        assert str(result["status"]).lower().endswith("error")
        assert any("trust gate denied" in msg.lower() for msg in result.get("error_log", []))

    def test_vector_match_succeeds_with_sufficient_trust(self):
        state = {"requirement_profile": to_json(ELIGIBLE_PAYLOAD), "caller_trust_level": TrustLevel.INTERNAL.value}
        result = VectorMatchEligibilityCheckNode()(state)
        assert result["status"] == AgentStatus.SUCCESS.value

    def test_scorecard_generate_rejects_insufficient_trust(self):
        match_result = {"skill_match_pct": 75.0, "fit_score": 0.75, "matched_skills": ["cash_register"], "gaps": ["shift_scheduling"]}
        state = {
            "candidate_id": "CAND-001",
            "match_result": to_json(match_result),
            "eligibility_result": to_json({"eligible": True, "reason": "ok", "required_docs": [], "conditions": []}),
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
        }
        result = ScorecardGenerateNode()(state)
        assert str(result["status"]).lower().endswith("error")
        assert any("trust gate denied" in msg.lower() for msg in result.get("error_log", []))

    def test_scorecard_generate_succeeds_with_sufficient_trust(self):
        match_result = {"skill_match_pct": 75.0, "fit_score": 0.75, "matched_skills": ["cash_register"], "gaps": ["shift_scheduling"]}
        state = {
            "candidate_id": "CAND-001",
            "match_result": to_json(match_result),
            "eligibility_result": to_json({"eligible": True, "reason": "ok", "required_docs": [], "conditions": []}),
            "caller_trust_level": TrustLevel.INTERNAL.value,
        }
        result = ScorecardGenerateNode()(state)
        assert result["status"] == AgentStatus.SUCCESS.value

    def test_report_finalize_rejects_insufficient_trust(self):
        state = {"scorecard": '{"candidate_id": "CAND-001", "fit_evidence": {}}', "caller_trust_level": TrustLevel.ANONYMOUS.value}
        result = ReportFinalizeNode()(state)
        assert str(result["status"]).lower().endswith("error")
        assert any("trust gate denied" in msg.lower() for msg in result.get("error_log", []))

    def test_report_finalize_succeeds_with_sufficient_trust(self):
        # S-1 clearance only — S-3 output re-check inspects the node's own result dict, not the
        # input state.
        state = {"scorecard": '{"candidate_id": "CAND-001", "fit_evidence": {}}', "caller_trust_level": TrustLevel.INTERNAL.value}
        result = ReportFinalizeNode()(state)
        assert not any("trust gate denied" in msg.lower() for msg in result.get("error_log", []))


# S-4 emit_trace_event coverage — every execute() return path must emit at least one domain
# event, and each event's payload must be counts/correlation_id only (never raw candidate
# content/PII). Patches are applied in each node module's own namespace (the module already did
# `from shared.utils.audit_logger import emit_trace_event`, so patching the shared module does
# not intercept the call).
_SENSITIVE_MARKERS = ("candidate_skills", "required_skills", "山田太郎", "氏名", "residence_card")


def _no_sensitive_payload(calls):
    for _event, payload, _state in calls:
        blob = json.dumps(payload, ensure_ascii=False)
        assert not any(marker in blob for marker in _SENSITIVE_MARKERS)


class TestEmitTraceEventCoverage:
    def test_candidate_ingest_emits_on_success(self, monkeypatch):
        import src.nodes.pre_process_node as mod

        calls = []
        monkeypatch.setattr(mod, "emit_trace_event", lambda e, p, s: calls.append((e, p, s)))
        mod.CandidateIngestRequirementLoadNode().execute({"user_input": json.dumps(ELIGIBLE_PAYLOAD)})
        assert len(calls) >= 1
        _no_sensitive_payload(calls)

    def test_candidate_ingest_emits_on_invalid_input_error(self, monkeypatch):
        import src.nodes.pre_process_node as mod

        calls = []
        monkeypatch.setattr(mod, "emit_trace_event", lambda e, p, s: calls.append((e, p, s)))
        mod.CandidateIngestRequirementLoadNode().execute({"user_input": ""})
        assert len(calls) >= 1
        _no_sensitive_payload(calls)

    def test_candidate_ingest_emits_on_invalid_json_error(self, monkeypatch):
        import src.nodes.pre_process_node as mod

        calls = []
        monkeypatch.setattr(mod, "emit_trace_event", lambda e, p, s: calls.append((e, p, s)))
        mod.CandidateIngestRequirementLoadNode().execute({"user_input": "not json"})
        assert len(calls) >= 1
        _no_sensitive_payload(calls)

    def test_vector_match_emits_on_success(self, monkeypatch):
        import src.nodes.vector_match_node as mod

        calls = []
        monkeypatch.setattr(mod, "emit_trace_event", lambda e, p, s: calls.append((e, p, s)))
        mod.VectorMatchEligibilityCheckNode().execute({"requirement_profile": to_json(ELIGIBLE_PAYLOAD)})
        assert len(calls) >= 1
        _no_sensitive_payload(calls)

    def test_vector_match_emits_on_missing_requirement_profile_error(self, monkeypatch):
        import src.nodes.vector_match_node as mod

        calls = []
        monkeypatch.setattr(mod, "emit_trace_event", lambda e, p, s: calls.append((e, p, s)))
        mod.VectorMatchEligibilityCheckNode().execute({"requirement_profile": None, "user_input": ""})
        assert len(calls) >= 1
        _no_sensitive_payload(calls)

    def test_scorecard_generate_emits_on_success(self, monkeypatch):
        import src.nodes.scorecard_generate_node as mod

        calls = []
        monkeypatch.setattr(mod, "emit_trace_event", lambda e, p, s: calls.append((e, p, s)))
        match_result = {"skill_match_pct": 75.0, "fit_score": 0.75, "matched_skills": [], "gaps": []}
        state = {
            "candidate_id": "CAND-001",
            "match_result": to_json(match_result),
            "eligibility_result": to_json({"eligible": True, "reason": "ok", "required_docs": [], "conditions": []}),
        }
        mod.ScorecardGenerateNode().execute(state)
        assert len(calls) >= 1
        _no_sensitive_payload(calls)

    def test_scorecard_generate_emits_on_missing_candidate_id_error(self, monkeypatch):
        import src.nodes.scorecard_generate_node as mod

        calls = []
        monkeypatch.setattr(mod, "emit_trace_event", lambda e, p, s: calls.append((e, p, s)))
        state = {"candidate_id": "", "match_result": to_json({}), "eligibility_result": to_json(None)}
        mod.ScorecardGenerateNode().execute(state)
        assert len(calls) >= 1
        _no_sensitive_payload(calls)

    def test_report_finalize_emits_on_success(self, monkeypatch):
        import src.nodes.post_process_node as mod

        calls = []
        monkeypatch.setattr(mod, "emit_trace_event", lambda e, p, s: calls.append((e, p, s)))
        state = {"scorecard": '{"candidate_id": "CAND-001", "fit_evidence": {}}'}
        mod.ReportFinalizeNode().execute(state)
        assert len(calls) >= 1
        _no_sensitive_payload(calls)

    def test_report_finalize_emits_on_pii_leak_blocked(self, monkeypatch):
        import src.nodes.post_process_node as mod

        calls = []
        monkeypatch.setattr(mod, "emit_trace_event", lambda e, p, s: calls.append((e, p, s)))
        state = {"scorecard": '{"氏名": "山田太郎"}'}
        mod.ReportFinalizeNode().execute(state)
        assert len(calls) >= 1
        _no_sensitive_payload(calls)
