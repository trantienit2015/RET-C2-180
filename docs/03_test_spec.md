# RET-C2-180 — Test Specification

## Test Strategy

Deterministic-core: no LLM required for the eligibility determination
(mandatory — legal determination); scorecard formatting is deterministic
too, full suite runs offline.

## Unit Tests (`tests/unit/test_nodes.py`)

| Node | Cases |
|---|---|
| CandidateIngestRequirementLoadNode | success (candidate_id + requirement_profile parsed); empty input→ERROR; raw PII field (name/mynumber)→ERROR; invalid JSON→ERROR; missing candidate_id→ERROR |
| VectorMatchEligibilityCheckNode | success (match_result + eligibility_result computed); eligible=True case; eligible=False case (wrong work_category); missing requirement_profile→ERROR |
| ScorecardGenerateNode | success (scorecard with disclaimer, no "recommended hire" phrase); missing candidate_id→ERROR |
| ReportFinalizeNode | success; PII-leak blocked (non-suppressible hook); automated-decision-phrase blocked (non-suppressible hook) |

## Integration Tests (`tests/integration/test_graph.py`)

| ID | Test | Expected |
|---|---|---|
| I-1 | candidate payload with matching skills + eligible work category | pipeline completes (≥4 nodes); scorecard present, no automated hire verdict |
| I-2 | candidate payload with ineligible work category | pipeline completes; eligibility_flag.eligible=False with reason |
| I-3 | empty input | ERROR |
| I-4 | payload embedding raw candidate name/mynumber | ERROR (rejected, not processed) |

> Per the S-2 gate's effect on the success path, integration tests
> assert pipeline-completion invariants rather than an exact terminal status
> for KB/match-dependent cases — unit tests already pin the success-path
> logic deterministically.

## Proof-of-Boundary Tests (`tests/proof_of_boundary/`)

| PB-ID | Boundary | Test | Expected Result |
|-------|----------|------|----------------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass |
| PB-6 | Invoke execution order | S-1 → node_start → S-2 → execute → S-3 → node_complete | Order verified |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result |
|-------|------|-------|----------------|
| BL-01 | skill match scoring | candidate has 3/4 required skills | skill_match_pct=75.0 |
| BL-02 | eligibility rule — work category rejection | work_category="office admin" | eligible=False, reason cites work_category |
| BL-03 | eligibility rule — hours ceiling | weekly_hours=45 | eligible=False, reason cites hours ceiling |
| BL-04 | no automated hire phrasing | any successful scorecard | scorecard never contains "recommended hire"/"採用推奨" |

## Non-suppressible output tests (critical)

- Raw candidate PII (name, DOB, mynumber, passport/residence-card, contact
  info) is always rejected at input before any processing (unit + I-4).
- The scorecard never leaks raw PII and never contains an automated hiring
  decision phrase (unit + BL-04) — decision support only, HITL boundary.
- The post_process S-3 hook re-checks `scorecard`'s own field only (S-3 hook
  self-consistency rule) — never cross-references separate state fields read
  independently.
- Eligibility determination is always produced by the deterministic
  `eligibility_rules_tool()`, never by the LLM formatting step (unit BL-02/BL-03).

## Test Execution Summary
- Execution date: 2026-07-08
- Total tests: see CI `run-tests` job output
- Coverage: deterministic-core, no LLM dependency

## 1. Deployment path tests

### TC-DEP-01 Marketplace entry point identity — `tests/unit/test_cli_entry_point.py`

| Case | Expected |
|---|---|
| Identity is concrete | `agent_name` / `namespace` are non-empty and not the runner default |
| Identity matches the HTTP entry point | the values equal what `src/api/server.py` passes to `secrets_factory`; where that entry point provisions no secrets, they equal the manifest `namespace` and the lower-cased template id |
| The runner call uses the constants | `run_agent_marketplace` is called with the module constants, not inline literals |

### TC-DEP-02 Standalone entry point boundary — `tests/proof_of_boundary/test_server_llm_injection.py`

| Case | Expected |
|---|---|
| Boots with no credential provisioned | the module imports and the app/agent objects are constructed |
| External bearer never reaches the internal level | resolves to the verified-external level |
| Staging runner credential reaches the internal level | resolves to the internal level |
| Wrong or missing bearer while auth is enabled | rejected with 401 |
