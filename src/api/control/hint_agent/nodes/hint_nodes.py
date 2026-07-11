"""Node functions for the hint generation LangGraph (Graph 2).

Every node is a plain async function that receives the running
``HintGraphState`` and returns a partial state update. DB access goes only
through the existing repository layer; prompt assembly goes only through the
existing prompt builder. The ``AsyncSession`` is threaded in via the graph
invocation config — nodes never create their own session.

Node sequence (wired in ``hint_generation_graph``)
-------------------------------------------------
1. **load_hint_context** — authorize mentor, load quiz/questions, resolve
   domain from study material, seed ``questions_for_hinting``.
2. **build_hint_prompt_payload** — call ``build_hint_prompt`` for batch or
   regeneration mode.
3. **invoke_hint_llm** — Groq call with rotation; sets ``raw_llm_output`` or
   ``terminal_llm_failure``.
4. **parse_hint_output** — validate JSON array shape and question IDs.
5. **validate_hint_quality** — enforce hint rules, per-question LLM retries,
   stage uncommitted hint writes.
6. **persist_hints_to_questions** — commit transaction and merge QC metadata.
7. **persist_hint_failure_diagnostics** — merge LLM failure diagnostics only.

Routing between nodes is defined in ``hint_generation_graph``; resume re-entry
is resolved by ``resume_router.resolve_resume_next_node``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import llm_settings
from src.api.control.hint_agent.prompts.hint_prompt import build_hint_prompt
from src.api.control.hint_agent.states.hint_state import HintGraphState
from src.api.core.exceptions import (
    HintsCannotGenerateOnPublishedQuizException,
    QuizHasNoQuestionsException,
    QuizNotFoundException,
)
from src.api.data.repositories import (  # noqa: E501
    HintRepository,
    StudyMaterialRepository,
)
from src.api.schemas.common import (
    HintGenerationDiagnosticsOut,
    HintQuestionErrorOut,
)
from src.api.utils.artifacts import new_artifact_run_id
from src.api.utils.hint_utils.artifacts.hint_artifacts import log_hint_agent
from src.api.utils.LLM_utils.groq_retry import call_groq_with_rotation
from src.api.utils.LLM_utils.llm_failure_diagnostics import (
    build_hint_invoke_failure_diagnostics,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _get_node_and_assert_space_access,
)

logger = logging.getLogger(__name__)

_BANNED_PHRASES = ("the correct answer is", "the answer is")


def _log_hint_artifact(
    state: HintGraphState,
    agent: str,
    payload: dict[str, Any],
) -> None:
    """Write a structured hint-agent artifact when ``artifact_run_id`` is set."""
    run_id = state.get("artifact_run_id")
    if not run_id:
        return
    log_hint_agent(
        topic_title=state.get("node_title") or str(state.get("node_id")),
        run_id=run_id,
        agent=agent,
        payload=payload,
        node_id=str(state.get("node_id") or ""),
    )


# ── Shared helpers ────────────────────────────────────────────────────────


def _session(config: RunnableConfig) -> AsyncSession:
    """Pull the AsyncSession passed into the graph invocation config."""
    return cast(AsyncSession, config["configurable"]["session"])


def _parse_json_array(raw: str) -> list:
    """Parse an LLM response that should be a JSON array.

    Tolerates accidental ```json fences around the payload.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[len("json") :].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array.")
    return parsed


# ── Nodes ─────────────────────────────────────────────────────────────────


async def load_hint_context(
    state: HintGraphState, config: RunnableConfig
) -> HintGraphState:
    """Load quiz context, questions needing hints, and optional domain metadata.

    Validates mentor ownership, rejects published quizzes, and builds
    ``questions_for_hinting`` (including previous hints when regenerating a
    subset). Skips questions already present in ``hints_written`` from a
    partial checkpoint.
    """
    session = _session(config)

    # Verify the mentor owns the node's space (raises on failure).
    node = await _get_node_and_assert_space_access(
        session, state["node_id"], state["mentor_id"], owner_only=True
    )

    repo = HintRepository(session)
    quiz = await repo.get_quiz_by_id(state["quiz_id"])
    if quiz is None or quiz.node_id != state["node_id"]:
        raise QuizNotFoundException()
    if quiz.is_published:
        raise HintsCannotGenerateOnPublishedQuizException()

    filter_ids = state.get("questions_filter_ids")
    if filter_ids:
        # Regeneration: only the mentor-selected question IDs.
        questions = await repo.get_active_questions_by_ids(state["quiz_id"], filter_ids)
        filter_set = {str(fid) for fid in filter_ids}
        questions = [q for q in questions if str(q.question_id) in filter_set]
    else:
        # Initial generation: all active questions missing hints.
        questions = await repo.get_active_questions_missing_hints(state["quiz_id"])

    if not questions:
        raise QuizHasNoQuestionsException()

    is_regeneration = bool(filter_ids)

    def _question_for_hinting(q: Any) -> dict[str, Any]:
        """Map a DB question row to the LLM-facing hint payload shape."""
        payload: dict[str, Any] = {
            "question_id": str(q.question_id),
            "question_text": q.question_text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_option": q.correct_option,
            "explanation": q.explanation,
        }
        if is_regeneration:
            payload["previous_hints"] = {
                "hint_1": q.hint_1 or "",
                "hint_2": q.hint_2 or "",
                "hint_3": q.hint_3 or "",
            }
        return payload

    questions_for_hinting = [_question_for_hinting(q) for q in questions]

    hints_written = dict(state.get("hints_written") or {})
    if hints_written:
        # Resume: drop questions already written in a prior partial run.
        questions_for_hinting = [
            q for q in questions_for_hinting if q["question_id"] not in hints_written
        ]
        if not questions_for_hinting and not state.get("failed_question_ids"):
            raise QuizHasNoQuestionsException()

    domain: str | None = None
    if quiz.study_material_version_id is not None:
        # Optional domain label from the study material concept plan.
        study_repo = StudyMaterialRepository(session)
        version = await study_repo.get_version_by_id(
            cast(UUID, quiz.study_material_version_id)
        )
        if version is not None:
            concept_plan = version.concept_plan
            if isinstance(concept_plan, dict) and concept_plan.get("domain"):
                domain = str(concept_plan["domain"])

    return {
        **state,
        "space_id": cast(UUID, node.space_id),
        "node_title": cast(str, node.title),
        "domain": domain,
        "artifact_run_id": state.get("artifact_run_id") or new_artifact_run_id(),
        "questions_for_hinting": questions_for_hinting,
        "hints_written": hints_written or None,
    }


async def build_hint_prompt_payload(state: HintGraphState) -> HintGraphState:
    """Assemble system/user messages for the batch hint LLM call.

    Uses regeneration mode when ``questions_filter_ids`` is set (includes prior
    hints and optional ``mentor_feedback`` in the prompt).
    """
    is_regeneration = bool(state.get("questions_filter_ids"))
    prompt_input = build_hint_prompt(
        questions_for_hinting=state.get("questions_for_hinting") or [],
        topic_title=state.get("node_title"),
        domain=state.get("domain"),
        is_regeneration=is_regeneration,
        mentor_feedback=state.get("mentor_feedback"),
    )
    return {**state, "prompt_input": prompt_input}


async def invoke_hint_llm(state: HintGraphState) -> HintGraphState:
    """Call Groq to generate hints for all questions in ``prompt_input``.

    On success, stores ``raw_llm_output`` and token usage. On terminal failure
    (retries exhausted), sets ``terminal_llm_failure`` and diagnostics for the
    failure-persist node — does not raise.
    """
    prompt_input = state.get("prompt_input")
    if not prompt_input:
        return {**state, "error": "Missing prompt input for hint generation."}

    result = await call_groq_with_rotation(
        messages=[
            SystemMessage(content=prompt_input["system_prompt"]),
            HumanMessage(content=prompt_input["user_message"]),
        ],
        model=llm_settings.llm_model,
        temperature=llm_settings.hint_generation_temperature,
        timeout=120,
        graph_node="hint_generator",
    )
    if not result.ok:
        logger.error(
            "Groq hint generation failed: %s",
            result.error_type,
        )
        # Terminal path — graph routes to persist_hint_failure_diagnostics.
        failure = {
            **state,
            "terminal_llm_failure": True,
            "hint_generation_diagnostics": build_hint_invoke_failure_diagnostics(
                result
            ),
            "next_llm_retry_at": result.next_llm_retry_at,
        }
        _log_hint_artifact(
            state,
            "hint_generator",
            {
                "prompt_input": prompt_input,
                "raw_llm_output": result.content,
                "llm_model_used": result.model or llm_settings.llm_model,
                "token_usage": result.token_usage,
                "terminal_llm_failure": True,
            },
        )
        return cast(HintGraphState, failure)

    success = {
        **state,
        "raw_llm_output": result.content or "",
        "llm_model_used": result.model or llm_settings.llm_model,
        "token_usage": result.token_usage,
    }
    _log_hint_artifact(
        state,
        "hint_generator",
        {
            "prompt_input": prompt_input,
            "raw_llm_output": success["raw_llm_output"],
            "llm_model_used": success["llm_model_used"],
            "token_usage": result.token_usage,
        },
    )
    return cast(HintGraphState, success)


async def parse_hint_output(state: HintGraphState) -> HintGraphState:
    """Parse and validate the LLM JSON array into ``parsed_hints``.

    Each element must reference a known ``question_id`` and include
    ``hint_1``, ``hint_2``, and ``hint_3``. Sets ``error`` on any schema or
    ID mismatch (graph ends; runner raises).
    """
    raw = state.get("raw_llm_output")
    if not raw:
        return {**state, "error": "No LLM output to parse."}

    try:
        items = _parse_json_array(raw)
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Malformed hint output: {exc}"}

    questions = state.get("questions_for_hinting") or []
    valid_ids = {q["question_id"] for q in questions}

    parsed: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            return {**state, "error": "Hint output element is not an object."}

        question_id = item.get("question_id")
        if question_id is None:
            return {**state, "error": "Hint output element missing question_id."}
        question_id = str(question_id)
        if question_id not in valid_ids:
            # LLM hallucinated or duplicated an ID not in the batch.
            return {
                **state,
                "error": f"Hint references unknown question_id: {question_id}.",
            }

        for field in ("hint_1", "hint_2", "hint_3"):
            if field not in item:
                return {**state, "error": f"Hint output missing field: {field}."}

        parsed.append(
            {
                "question_id": question_id,
                "hint_1": item.get("hint_1"),
                "hint_2": item.get("hint_2"),
                "hint_3": item.get("hint_3"),
            }
        )

    return {**state, "parsed_hints": parsed}


def _hint_quality_issue(hint_1: Any, hint_2: Any, hint_3: Any) -> str | None:
    """Return an error type when hints fail validation, else None."""
    for value in (hint_1, hint_2, hint_3):
        if not isinstance(value, str) or not value.strip():
            return "hint_quality_error"
        lowered = value.lower()
        if any(phrase in lowered for phrase in _BANNED_PHRASES):
            return "hint_quality_error"
    h1 = str(hint_1).strip()
    h3 = str(hint_3).strip()
    if len(h1) > len(h3):
        return "hint_quality_error"
    return None


async def _regenerate_hints_for_question(
    question: dict[str, Any],
    state: HintGraphState,
) -> dict[str, Any] | None:
    """Call the LLM for a single question and return parsed hints or None."""
    is_regeneration = bool(state.get("questions_filter_ids"))
    prompt_input = build_hint_prompt(
        questions_for_hinting=[question],
        topic_title=state.get("node_title"),
        domain=state.get("domain"),
        is_regeneration=is_regeneration,
        mentor_feedback=state.get("mentor_feedback"),
    )
    result = await call_groq_with_rotation(
        messages=[
            SystemMessage(content=prompt_input["system_prompt"]),
            HumanMessage(content=prompt_input["user_message"]),
        ],
        model=llm_settings.llm_model,
        temperature=llm_settings.hint_generation_temperature,
        timeout=120,
        graph_node="hint_generator",
    )
    if not result.ok:
        return None

    try:
        items = _parse_json_array(result.content or "")
    except Exception:  # noqa: BLE001
        return None

    question_id = question["question_id"]
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("question_id")) != question_id:
            continue
        for field in ("hint_1", "hint_2", "hint_3"):
            if field not in item:
                return None
        return {
            "question_id": question_id,
            "hint_1": item.get("hint_1"),
            "hint_2": item.get("hint_2"),
            "hint_3": item.get("hint_3"),
        }
    return None


async def validate_hint_quality(
    state: HintGraphState, config: RunnableConfig
) -> HintGraphState:
    """Validate hints, retry low-quality items, and stage DB writes.

    For each pending question, checks non-empty hints, banned answer-leak
    phrases, and progressive specificity (hint_1 must not be longer than
    hint_3). Failed questions after max retries are recorded in
    ``hint_generation_diagnostics``; successful hints are written with
    ``commit=False`` for the persist node to finalize.
    """
    session = _session(config)
    repo = HintRepository(session)
    questions = state.get("questions_for_hinting") or []
    parsed = state.get("parsed_hints") or []
    hints_written = dict(state.get("hints_written") or {})

    failed_ids = state.get("failed_question_ids")
    if failed_ids:
        # Resume/retry path: only re-validate previously failed questions.
        failed_set = {str(fid) for fid in failed_ids}
        questions = [q for q in questions if q["question_id"] in failed_set]
    else:
        questions = [q for q in questions if q["question_id"] not in hints_written]

    by_question_id: dict[str, dict] = {}
    for hint in parsed:
        question_id = hint["question_id"]
        if question_id in by_question_id:
            return {
                **state,
                "error": "Hint validation failed: duplicate question_id in LLM output.",
            }
        by_question_id[question_id] = hint

    validated: list[dict] = []
    question_errors: list[dict[str, Any]] = []

    for q in questions:
        qid = q["question_id"]
        if qid in hints_written:
            continue

        hint = by_question_id.get(qid)
        attempts = 0
        max_retries = llm_settings.hint_quality_max_retries

        while attempts <= max_retries:
            if hint is not None:
                issue = _hint_quality_issue(
                    hint.get("hint_1"), hint.get("hint_2"), hint.get("hint_3")
                )
                if issue is None:
                    hint_payload = {
                        "question_id": qid,
                        "hint_1": hint["hint_1"],
                        "hint_2": hint["hint_2"],
                        "hint_3": hint["hint_3"],
                    }
                    validated.append(hint_payload)
                    await repo.update_question_hints(
                        UUID(qid),
                        hint["hint_1"],
                        hint["hint_2"],
                        hint["hint_3"],
                        commit=False,
                    )
                    hints_written[qid] = hint_payload
                    break

            if attempts >= max_retries:
                # Exhausted per-question quality retries — record diagnostic.
                question_errors.append(
                    HintQuestionErrorOut(
                        question_id=UUID(qid),
                        error_type="hint_quality_error",
                        attempts=attempts + 1,
                    ).model_dump(by_alias=True)
                )
                break

            attempts += 1
            # Single-question LLM retry when batch hints fail quality checks.
            hint = await _regenerate_hints_for_question(q, state)

    diagnostics: dict[str, Any] | None = None
    failed_question_ids: list[str] | None = None
    if question_errors:
        diagnostics = HintGenerationDiagnosticsOut.model_validate(
            {"questionErrors": question_errors}
        ).model_dump(by_alias=True, exclude_none=True)
        failed_question_ids = [
            str(err.get("questionId") or err.get("question_id"))
            for err in question_errors
        ]

    validation_return = {
        **state,
        "validated_hints": validated,
        "hints_written": hints_written,
        "failed_question_ids": failed_question_ids,
        "hint_generation_diagnostics": diagnostics,
    }
    _log_hint_artifact(
        state,
        "hint_validation",
        {
            "validated_hints": validated,
            "hint_generation_diagnostics": diagnostics,
            "parsed_hints": parsed,
        },
    )
    return cast(HintGraphState, validation_return)


async def persist_hints_to_questions(
    state: HintGraphState, config: RunnableConfig
) -> HintGraphState:
    """Commit staged hint writes and merge generation diagnostics onto the quiz.

    Flushes any validated hints not yet in ``hints_written``, merges QC
    diagnostics (including per-question failures), touches quiz updated_at when
    only hints changed, and commits the session when writes occurred.
    """
    session = _session(config)
    repo = HintRepository(session)
    hints_written = state.get("hints_written") or {}
    validated = state.get("validated_hints") or []

    for hint in validated:
        qid = hint["question_id"]
        if qid in hints_written:
            continue
        await repo.update_question_hints(
            UUID(qid),
            hint["hint_1"],
            hint["hint_2"],
            hint["hint_3"],
            commit=False,
        )

    diagnostics = state.get("hint_generation_diagnostics")
    next_llm_retry_at = state.get("next_llm_retry_at")
    hint_writes_pending = bool(validated or hints_written)
    if diagnostics:
        # Merge partial failures or LLM metadata into quiz QC JSON.
        await repo.merge_quiz_qc_result(
            state["quiz_id"],
            {"hintGeneration": diagnostics},
            next_llm_retry_at=next_llm_retry_at,
        )
    elif hint_writes_pending:
        await repo.touch_quiz_updated_at(state["quiz_id"])
    if hint_writes_pending:
        await session.commit()

    _log_hint_artifact(
        state,
        "hint_result",
        {
            "quiz_id": str(state["quiz_id"]),
            "validated_hints": validated,
            "hint_generation_diagnostics": diagnostics,
        },
    )

    return state


async def persist_hint_failure_diagnostics(
    state: HintGraphState, config: RunnableConfig
) -> HintGraphState:
    """Persist hint LLM failure diagnostics without modifying existing hints."""
    session = _session(config)
    repo = HintRepository(session)
    diagnostics = state.get("hint_generation_diagnostics")
    if diagnostics:
        await repo.merge_quiz_qc_result(
            state["quiz_id"],
            {"hintGeneration": diagnostics},
            next_llm_retry_at=state.get("next_llm_retry_at"),
        )
    return state
