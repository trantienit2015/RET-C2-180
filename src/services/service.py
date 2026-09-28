"""AgentCore Platform v1.0 - RET-C2-180 domain services.

Pure, deterministic helpers - no agenticstar/framework imports here.
Candidate PII detection, semantic-match scoring, 育成就労 visa-eligibility
rule checking, and scorecard formatting for the retail HR candidate-fit
domain.

CRITICAL: eligibility_rules_tool() is a DETERMINISTIC
rule-based check - immigration eligibility is a legal determination and
must never be LLM-generated. The LLM only formats the scorecard around this
deterministic verdict.
"""

import re
from typing import Any

# Field patterns tolerate an optional closing quote (JSON key) between the
# field name and the colon, e.g. `"氏名": "山田太郎"` or `name: John`.
_PII_PATTERNS = {
    "name_field": re.compile(r"(氏名|name)[\"']?\s*[:：]\s*\S+", re.IGNORECASE),
    "dob_field": re.compile(r"(生年月日|date of birth|dob)[\"']?\s*[:：]\s*\S+", re.IGNORECASE),
    "mynumber_like": re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)"),
    "passport_or_residence_card": re.compile(
        r"(passport\s*(no\.?|number)|residence\s*card\s*(no\.?|number))[\"']?\s*[:：]?\s*[A-Z0-9]{6,}", re.IGNORECASE
    ),
    "contact_info": re.compile(r"(電話番号|phone|email)[\"']?\s*[:：]\s*\S+", re.IGNORECASE),
}

REQUIRED_WORK_CATEGORIES = ("retail", "cvs", "supermarket", "convenience store", "小売", "コンビニ")


def detect_candidate_pii(text: str) -> list[str]:
    """S-2 non-suppressible check: reject any raw candidate-identifying field.

    This agent processes only anonymised candidate profiles keyed by
    candidate_id - never raw name/DOB/mynumber/passport/contact fields.
    """
    return [name for name, pattern in _PII_PATTERNS.items() if pattern.search(text or "")]


def normalize_input(user_input: str) -> tuple[str, str | None]:
    normalized = (user_input or "").strip()
    if not normalized:
        return "", "empty input"
    return normalized, None


def compute_skill_match(candidate_skills: list[str], required_skills: list[str]) -> dict[str, Any]:
    if not required_skills:
        return {"skill_match_pct": 0.0, "fit_score": 0.0, "matched_skills": [], "gaps": []}
    matched = [s for s in candidate_skills if s in required_skills]
    gaps = [s for s in required_skills if s not in candidate_skills]
    match_pct = round(100.0 * len(matched) / len(required_skills), 1)
    return {
        "skill_match_pct": match_pct,
        "fit_score": round(match_pct / 100.0, 2),
        "matched_skills": matched,
        "gaps": gaps,
    }


def eligibility_rules_tool(
    work_category: str, weekly_hours: int, employer_registered: bool, has_required_docs: bool
) -> dict[str, Any]:
    """Deterministic 育成就労 visa-eligibility rule table.

    Never LLM-generated - immigration eligibility is a legal determination.
    Returns {eligible, reason, required_docs, conditions}.
    """
    required_docs = ["residence_card", "employment_contract", "employer_registration_certificate"]

    if work_category.lower() not in [c.lower() for c in REQUIRED_WORK_CATEGORIES]:
        return {
            "eligible": False,
            "reason": "work_category not in the 育成就労 retail-eligible category list",
            "required_docs": required_docs,
            "conditions": [],
        }
    if not employer_registered:
        return {
            "eligible": False,
            "reason": "employer is not a registered 育成就労 receiving organization",
            "required_docs": required_docs,
            "conditions": ["employer must complete 育成就労 registration before proceeding"],
        }
    if weekly_hours > 40:
        return {
            "eligible": False,
            "reason": "weekly_hours exceeds the 育成就労 permitted work-hours ceiling",
            "required_docs": required_docs,
            "conditions": ["reduce weekly_hours to <= 40"],
        }
    if not has_required_docs:
        return {
            "eligible": False,
            "reason": "required documentation incomplete",
            "required_docs": required_docs,
            "conditions": ["submit all required_docs before final determination"],
        }
    return {
        "eligible": True,
        "reason": "meets 育成就労 work category, employer registration, and hours criteria",
        "required_docs": required_docs,
        "conditions": [],
    }


def format_scorecard(
    candidate_id: str, match_result: dict[str, Any], eligibility_result: dict[str, Any] | None
) -> dict[str, Any]:
    """Evidence summary only - never a 'recommended hire: yes/no' verdict."""
    scorecard = {
        "candidate_id": candidate_id,
        "fit_evidence": {
            "skill_match_pct": match_result.get("skill_match_pct", 0.0),
            "matched_skills": match_result.get("matched_skills", []),
            "gaps": match_result.get("gaps", []),
        },
        "disclaimer": "本レポートは意思決定支援のための証拠提示であり、採用可否の自動判定ではありません。最終判断は人事責任者が行います。",
    }
    if eligibility_result is not None:
        scorecard["eligibility_flag"] = {
            "eligible": eligibility_result.get("eligible"),
            "reason": eligibility_result.get("reason"),
            "required_docs": eligibility_result.get("required_docs", []),
            "conditions": eligibility_result.get("conditions", []),
        }
    return scorecard


def compute_confidence(match_result: dict[str, Any]) -> float:
    return float(match_result.get("fit_score", 0.0))
