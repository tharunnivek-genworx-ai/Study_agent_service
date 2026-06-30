"""Shared QC check-category definitions for quiz verification prompts."""

from __future__ import annotations

import json

PER_QUESTION_CHECK_CATEGORIES_BLOCK = """For EACH question, produce one question_result object containing both dimensions inline:
① answer_correctness  →  fields: answer_correctness_passed (bool), answer_evidence (str)
   Derive the correct answer yourself from the study material BEFORE looking at
   correct_option. State your independent answer in answer_evidence first, then
   confirm or deny the match.
   STEM: re-derive or recompute the calculation.
   Programming: trace the code or API behaviour step by step.
   Conceptual: verify named facts, dates, and attributions against the study material.
   Pass: your independent answer matches correct_option AND the explanation is
   consistent with it.
   Fail: wrong correct_option; explanation contradicts the marked option;
   two or more options are equally correct.
   answer_evidence format: "Independent answer: <X>. Marked option <Y> — <matches/does not match>."
② question_quality  →  fields: quality_passed (bool), quality_evidence (str)
   Combined quality review: topic relevance, stem clarity, explanation substance,
   and distractor plausibility.
   Do NOT re-check structural fields (option count, blank fields) — those are
   verified in code before QC runs.
   Pass: on-topic, unambiguous stem, explanation teaches why the correct option is
   right (not just restates it), all four options are plausible distractors.
   Fail: off-topic; vague or double-barreled stem; explanation empty or only
   restates the answer; absurd or obviously wrong distractors; hallucinated claim.
   Quiz-only answerability: evaluate question_text as a trainee would see it — without
   the study material. Fail quality_passed if the stem depends on unstated context
   (artifacts, setups, cases, or identifiers that appear only in the material and are
   not reproduced in question_text).
   Embedded artifact format: when question_text includes a fenced block, fail
   quality_passed if the opening fence is not on its own line after a blank line, or if
   the closing fence is not on its own line.
   quality_evidence format: one sentence — reason for pass or the specific failure.
When either dimension fails, populate corrective_hint with one actionable sentence
describing the root-cause fix. Leave corrective_hint as "" when both dimensions pass."""
QUIZ_SUMMARY_BLOCK = """QUIZ SUMMARY — one compact object covering the whole quiz
   Structural coherence (option count, field presence) is verified in code — do NOT
   include those here.
   Evaluate only:
   - difficulty_ok: does easy/medium/hard mix match the requested profile?
     Derive difficulty_counts from the per-question difficulty labels in the input.
   - duplicate_concepts: list topic_tag values or concept labels tested more than once
   - coverage_issues: list important study-material concepts that have no question"""
ANTI_INFLATION_RULES_BLOCK = """ANTI-INFLATION — no exceptions
- answer_correctness: state your independent answer first — never treat the marked
  option as evidence ("B is indeed correct" is not independent verification).
- answer_evidence and quality_evidence: one short sentence each, no padding.
- corrective_hint: populate only when at least one dimension failed; one sentence only.
- retry_recommendation.mode must never be "none" while any question_result has a failure."""
WRONG_ANSWER_RISK_BLOCK = """WRONG ANSWER RISK — set at top level based on answer_correctness results
  none   — every answer_correctness_passed is true via independent verification.
  low    — minor explanation imprecision; all correct_option values are right.
  medium — exactly one wrong correct_option or one contradicting explanation.
  high   — two or more wrong correct_options, or badly contradicting explanations
           on multiple questions."""
RETRY_RECOMMENDATION_BLOCK = """RETRY RECOMMENDATION
  none                     — all question_results show both dimensions passing.
  question_patch           — isolated question failures; no concept is entirely
                             unrepresented.
  question_insert          — a key concept has no question at all (coverage gap
                             in quiz_summary.coverage_issues).
  question_patch_then_insert — both of the above apply.
  full_regeneration        — answer_correctness_passed is false on more than ⅓ of
                             questions, or wrong_answer_risk is "high" with multiple
                             quality failures."""
_EXAMPLE_QUESTION_RESULT = {
    "question_id": "<exact question_id from quiz_questions input>",
    "question_number": 1,
    "answer_correctness_passed": True,
    "answer_evidence": "Independent answer: B. Marked option B matches and explanation is consistent.",
    "quality_passed": True,
    "quality_evidence": "Clear unambiguous stem, all four options are plausible, explanation teaches the why.",
    "corrective_hint": "",
}
_EXAMPLE_QUIZ_SUMMARY = {
    "difficulty_ok": True,
    "difficulty_counts": {"easy": 3, "medium": 4, "hard": 3},
    "duplicate_concepts": [],
    "coverage_issues": [],
}
QC_OUTPUT_FORMAT_BLOCK = f"""OUTPUT CONTRACT
Return ONLY valid JSON. Start with {{ end with }}. No preamble, no markdown, no commentary.
Every schema field below must be present. Use [] for empty arrays, "" for empty strings.
FIELD NAMES ARE FIXED — never rename them:
  question_results (NOT checks), answer_correctness_passed (NOT passed),
  answer_evidence (NOT evidence), quality_passed, quality_evidence, corrective_hint.
RESULT COUNT: question_results must contain exactly one object per question evaluated.
For N questions emit exactly N objects — no more, no fewer.
Do NOT emit separate quiz-wide objects inside question_results — quiz-level findings
go exclusively in quiz_summary, wrong_answer_risk, corrective_instructions, and
retry_recommendation.
Example question_result object:
{json.dumps(_EXAMPLE_QUESTION_RESULT, indent=2)}
Example quiz_summary:
{json.dumps(_EXAMPLE_QUIZ_SUMMARY, indent=2)}
Full top-level JSON shape:
{{
  "question_results": [
    {{
      "question_id": "<exact id from input>",
      "question_number": 1,
      "answer_correctness_passed": true,
      "answer_evidence": "one sentence",
      "quality_passed": true,
      "quality_evidence": "one sentence",
      "corrective_hint": ""
    }}
  ],
  "quiz_summary": {{
    "difficulty_ok": true,
    "difficulty_counts": {{ "easy": 0, "medium": 0, "hard": 0 }},
    "duplicate_concepts": [],
    "coverage_issues": []
  }},
  "wrong_answer_risk": "none|low|medium|high",
  "corrective_instructions": "<actionable paragraph for the quiz writer, or empty string>",
  "retry_recommendation": {{
    "mode": "none|question_patch|question_insert|question_patch_then_insert|full_regeneration",
    "failed_question_ids": [],
    "missing_concepts": [],
    "rationale": "<why this mode>"
  }}
}}"""
PER_QUESTION_CATEGORIES = frozenset(
    {
        "answer_correctness",
        "question_quality",
    }
)
# Synthetic checks expanded from quiz_summary during parse (not emitted by LLM).
LLM_QUIZ_WIDE_CATEGORIES = frozenset(
    {
        "difficulty_alignment",
        "duplicate_overlap",
    }
)
# Includes deterministic quiz_coherence checks merged in result_builder.
QUIZ_WIDE_CATEGORIES = LLM_QUIZ_WIDE_CATEGORIES | frozenset({"quiz_coherence"})
JSON_OUTPUT_RULES_BLOCK = """JSON OUTPUT
- One complete JSON object — Groq JSON mode is enabled.
- question_results: exactly one entry per question (answer_correctness_passed +
  quality_passed inline per entry, not as separate objects).
- quiz_summary: required compact rollup — difficulty_alignment and duplicate_overlap
  are NOT separate entries in question_results.
- question_id on every result must exactly match the quiz_questions input.
- NEVER use alternate field names (checks, check_type, passed, result, evidence,
  explanation)."""
