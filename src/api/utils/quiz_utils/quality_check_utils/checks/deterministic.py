"""Deterministic structural checks for quiz questions before LLM QC."""

from __future__ import annotations

from typing import Any

_VALID_CORRECT_OPTIONS = frozenset({"A", "B", "C", "D"})

_REQUIRED_FIELDS = (
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "correct_option",
    "explanation",
)


def _blank_str(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


def det_question_count(
    questions: list[dict[str, Any]],
    *,
    expected_count: int,
) -> dict[str, Any]:
    actual = len(questions)
    passed = actual == expected_count
    return {
        "id": "det_question_count",
        "category": "quiz_coherence",
        "question": (
            f"Does the quiz contain exactly {expected_count} questions as requested?"
        ),
        "passed": passed,
        "severity": "critical",
        "evidence": (
            f"Found {actual} questions; expected {expected_count}."
            if not passed
            else f"Question count matches requested {expected_count}."
        ),
        "corrective_hint": (
            ""
            if passed
            else f"Return exactly {expected_count} questions in the JSON array."
        ),
    }


def det_quiz_coherence(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Structural checks: fields, correct_option, blank options, duplicate stems."""
    checks: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    for index, question in enumerate(questions):
        qnum = index + 1
        question_id = str(question.get("question_id", "")).strip()
        question_text = question.get("question_text")
        option_a = question.get("option_a")
        option_b = question.get("option_b")
        option_c = question.get("option_c")
        option_d = question.get("option_d")
        correct_option = question.get("correct_option")
        explanation = question.get("explanation")

        base = {
            "question_number": qnum,
            "question_id": question_id,
        }

        for field in _REQUIRED_FIELDS:
            if question.get(field) in (None, "") or _blank_str(question.get(field)):
                checks.append(
                    {
                        **base,
                        "id": f"det_missing_{field}_{qnum}",
                        "category": "quiz_coherence",
                        "question": f"Is {field} present and non-empty for question {qnum}?",
                        "passed": False,
                        "severity": "critical",
                        "evidence": f"Question {qnum} is missing or blank: {field}.",
                        "corrective_hint": (
                            "All four options (A–D) are required."
                            if field in ("option_c", "option_d")
                            else f"Provide a non-empty {field}."
                        ),
                    }
                )

        if _blank_str(option_a) or _blank_str(option_b):
            checks.append(
                {
                    **base,
                    "id": f"det_blank_required_option_{qnum}",
                    "category": "quiz_coherence",
                    "question": f"Are option_a and option_b non-empty for question {qnum}?",
                    "passed": False,
                    "severity": "critical",
                    "evidence": f"Question {qnum} has blank required options.",
                    "corrective_hint": "Fill option_a and option_b with plausible distractors.",
                }
            )

        if (
            option_c is None
            or _blank_str(option_c)
            or option_d is None
            or _blank_str(option_d)
        ):
            checks.append(
                {
                    **base,
                    "id": f"det_missing_option_c_d_{qnum}",
                    "category": "quiz_coherence",
                    "question": f"Are option_c and option_d present for question {qnum}?",
                    "passed": False,
                    "severity": "critical",
                    "evidence": f"Question {qnum} is missing option_c or option_d.",
                    "corrective_hint": "All four options (A–D) are required.",
                }
            )

        if correct_option not in _VALID_CORRECT_OPTIONS:
            checks.append(
                {
                    **base,
                    "id": f"det_invalid_correct_option_{qnum}",
                    "category": "quiz_coherence",
                    "question": f"Is correct_option valid for question {qnum}?",
                    "passed": False,
                    "severity": "critical",
                    "evidence": f"Invalid correct_option {correct_option!r}.",
                    "corrective_hint": "Set correct_option to A, B, C, or D.",
                }
            )
        else:
            option_map = {
                "A": option_a,
                "B": option_b,
                "C": option_c,
                "D": option_d,
            }
            if option_map[correct_option] is None or _blank_str(
                option_map[correct_option]
            ):
                checks.append(
                    {
                        **base,
                        "id": f"det_correct_option_missing_target_{qnum}",
                        "category": "quiz_coherence",
                        "question": (
                            f"Does correct_option reference a real option for question {qnum}?"
                        ),
                        "passed": False,
                        "severity": "critical",
                        "evidence": (
                            f"correct_option {correct_option} points to a missing or blank option."
                        ),
                        "corrective_hint": (
                            "Ensure correct_option references a filled option letter."
                        ),
                    }
                )

        if _blank_str(explanation):
            checks.append(
                {
                    **base,
                    "id": f"det_blank_explanation_{qnum}",
                    "category": "quiz_coherence",
                    "question": f"Is explanation non-empty for question {qnum}?",
                    "passed": False,
                    "severity": "critical",
                    "evidence": f"Question {qnum} has a missing or empty explanation.",
                    "corrective_hint": "Provide a teaching explanation for the correct answer.",
                }
            )

        text_key = str(question_text or "").strip()
        if text_key:
            if text_key in seen_texts:
                checks.append(
                    {
                        **base,
                        "id": f"det_duplicate_stem_{qnum}",
                        "category": "duplicate_overlap",
                        "question": f"Is question {qnum} stem unique within the quiz?",
                        "passed": False,
                        "severity": "major",
                        "evidence": f"Duplicate question_text for question {qnum}.",
                        "corrective_hint": "Rewrite or remove the duplicate stem.",
                    }
                )
            seen_texts.add(text_key)

    return checks


def run_deterministic_quiz_checks(
    questions: list[dict[str, Any]],
    *,
    expected_count: int,
) -> list[dict[str, Any]]:
    """Run all deterministic quiz checks."""
    checks = [det_question_count(questions, expected_count=expected_count)]
    checks.extend(det_quiz_coherence(questions))
    return checks
