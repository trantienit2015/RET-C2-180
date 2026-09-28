# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `RETHRCandidateScorecardAgent`
- **L1 Base**: AgentBaseGraph
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

Cat 2: outer `AgentBaseGraph` (fixed 5-node backbone) + `GraphNode` in the
`main` slot wrapping an inner `BaseGraph` (2-step linear domain workflow).

### Node Configuration (outer)

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version/session_id/trust_level | - | - | InitializeNode (default) |
| pre_process | `CandidateIngestRequirementLoadNode` — validate input, reject raw candidate PII, parse candidate/requirement payload | `user_input` | `candidate_id`, `requirement_profile` | FunctionNode |
| main | `HRCandidateScorecardGraphNode` — wraps inner workflow | `requirement_profile` | `match_result`, `eligibility_result`, `scorecard`, `output_confidence` | GraphNode |
| post_process | `ReportFinalizeNode` — non-suppressible PII-leak + automated-decision-phrase re-check | `scorecard` | (validated) | FunctionNode |
| finalize | response_metadata, total_time_ms | - | - | FinalizeNode (default) |

### Node Configuration (inner, per the locked node flow)

| Node | Responsibility |
|------|-----------------|
| `VectorMatchEligibilityCheckNode` | Computes candidate-requirement skill match, then calls `eligibility_rules_tool()` — a **deterministic rule-based Tool**, never LLM-generated (immigration eligibility is a legal determination); re-checks `requirement_profile` presence (fields do not cross the GraphNode subgraph boundary) |
| `ScorecardGenerateNode` | Formats the fit-evidence scorecard around the deterministic match/eligibility results via `format_scorecard()` — a deterministic, template-based formatter, not an LLM call; never generates the eligibility verdict itself, never emits a "recommended hire" phrase |

### Data Flow

```
START → initialize → pre_process → main → {route} → post_process → finalize → END
                                            ↓ (retry)
                                          pre_process
```

Inner (wrapped by `main`):
```
START → vector_match_eligibility_check → scorecard_generate → END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `candidate_id` | str | masked/anonymised reference only - never raw PII | Yes |
| `requirement_profile` | str (JSON dict) | parsed candidate/requirement payload | Yes |
| `match_result` | str (JSON dict) | `{skill_match_pct, fit_score, matched_skills, gaps}` | Yes |
| `eligibility_result` | str (JSON dict \| null) | `{eligible, reason, required_docs, conditions}` - deterministic only | No |
| `scorecard` | str (JSON dict) | final fit-evidence summary (decision support only) | Yes |
| `output_confidence` | float | 0.0-1.0 | Yes |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- **No raw candidate PII in State** (name, DOB, mynumber, passport/residence-card number, contact info) — `candidate_id` is the only permitted identifier, and it must already be anonymised before this agent processes it
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [x] SecurityViolationError
- [x] S-2: deterministic PII scan (`detect_candidate_pii()`) directly in
      `CandidateIngestRequirementLoadNode.execute()` — rejects raw
      name/DOB/mynumber/passport/residence-card/contact fields before any
      processing. NOT LLM-based.
- [x] S-3: `_extra_security_gate_output()` — non-suppressible re-check on
      `ReportFinalizeNode` that the scorecard (a) never leaked raw candidate
      PII and (b) never contains an automated "recommended hire: yes/no"
      decision phrase (HITL boundary — decision support only). Own-dict
      field re-check only, per the S-3 hook self-consistency rule.
- [x] S-4: `emit_trace_event()` — domain events (`hr_candidate_ingested`,
      `hr_candidate_input_rejected_pii`,
      `hr_candidate_scorecard_workflow_dispatched`,
      `hr_candidate_scorecard_workflow_completed`,
      `report_finalize_pii_leak_blocked`,
      `report_finalize_automated_decision_blocked`,
      `report_finalize_safety_recheck_blocked`) inside each `execute()`.
      Audit events record scorecard metadata only (candidate_id, scores,
      verdict) — never resume content or immigration identifiers.

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)
> - Custom `BaseNode` subclass → must implement `_security_gate_input()` and
>   `_security_gate_output()` directly (`@abstractmethod` — omission raises `TypeError` at instantiation)

### HITL Boundary — Decision Support Only

This agent never makes an automated hiring decision or automated visa
eligibility determination. `eligibility_rules_tool()` is a deterministic
rule check producing a flag + required-documentation list — the human HR/
legal reviewer decides on application submission. The scorecard is an
evidence summary; the S-3 gate blocks any "recommended hire" phrasing from
ever reaching output. No `interrupt()`/D6 pattern is used here — the
boundary is enforced structurally (no automated-action integration exists in
this template), not via a pause/resume HITL session.

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — `HRCandidateScorecardGraphNode` wraps
  `HRCandidateScorecardWorkflowGraph`.
- **Composition target**: inner `BaseGraph` (2-node linear domain workflow).
- **Error propagation strategy**: `propagate` (fail fast — re-raise inner
  errors as `SubgraphError`, default).

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Cat 2 fixed multi-step workflow, no autonomous loop needed |
| Composition pattern | Standalone nodes | GraphNode (subgraph) | GraphNode | Domain complexity (skill match → deterministic eligibility → scorecard formatting) is encapsulated inside the inner workflow per the locked node flow |
| Eligibility determination | LLM-generated | Deterministic rule table (Tool call) | Deterministic rule table | CRITICAL: immigration eligibility is a legal determination, must never be LLM-generated |
| `required_trust_level` | `VERIFIED_INTERNAL` (spec's literal, invalid) | `INTERNAL` | `INTERNAL` | `VERIFIED_INTERNAL` is not a valid `TrustLevel` enum member (only `ANONYMOUS`/`VERIFIED_EXTERNAL`/`INTERNAL` exist). `INTERNAL` is the correct semantic match: only authenticated internal HR-system callers may submit candidate data. |

## 1. Deployment entry points

The agent is reachable through two entry points, and both resolve their runtime inputs the same way.

| Entry point | File | Used by |
|---|---|---|
| Standalone HTTP | `src/api/server.py` | staging rehearsal, direct invocation |
| Marketplace one-shot Pod | `cli.py` | the platform runner (container `CMD`) |

Both read runtime parameters from `config/config.yaml` — the manifest carries discovery metadata
only — and both scope secrets to the same location (`namespace=ret`, `agent_name=ret-c2-180`), so a
secret provisioned for one path resolves identically on the other.

**No LLM client is constructed at either entry point.** The pipeline is deterministic; a client
may still be injected through `config["llm"]` by a caller that has one.

**Progress events.** Each pipeline stage emits a non-terminal progress event at its start, so a
caller sees the run advancing. Outside the Marketplace runtime the emitter resolves to a no-op, so
the same code is safe on every path. Terminal events belong to the platform runner and are never
emitted by this agent.

**Caller authentication at the standalone entry point.** A caller that no upstream middleware
vouched for stays anonymous unless it presents a deployment-level credential: the external bearer
token grants the verified-external level, and a separate staging-only runner credential is the only
way to reach the internal level. Trust established upstream is never changed.
