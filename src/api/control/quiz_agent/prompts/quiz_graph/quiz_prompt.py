"""Quiz generation prompts — self-contained, no shared imports.
Output contract: a JSON object ``{"questions": [...]}`` of question objects, ready to map
directly onto `quiz_questions` rows (question_text, option_a..option_d, correct_option,
explanation, difficulty, topic_tag, domain).
Domain-aware: classification mirrors the study_agent's STEM / Programming /
Conceptual / Mixed split, so a quiz on thermodynamics, a quiz on React hooks,
and a quiz on contract law each get question styles, distractor strategies,
and a "hard"-tier definition suited to that domain — not a single IT-centric
template.
Hints are NOT generated here — they are produced by a separate Hint Agent
after quiz questions are finalized and stored.
"""

from __future__ import annotations

import json

from src.api.utils.prompt_utils.domain_merge import (
    classification_block,
    merge_domain_blocks,
)

# RULE — QUESTION QUALITY (shared across all quiz writers)
QUESTION_QUALITY_BLOCK = """- Each question must test ONE clear idea. Avoid compound stems,
  "all of the above", or "none of the above".
- Avoid trick questions based on wording technicalities rather than understanding.
- Avoid duplicate or near-duplicate questions testing the same fact twice.
- Use exact terminology from the study material (concept names, step names, parameter
  names, named cases).
- explanation must be self-contained: a trainee reading only the explanation after submitting
  should understand WHY the correct option is right and why the most tempting wrong option
  is wrong.
RULE — QUIZ-ONLY ANSWERABILITY
Trainees answer from the quiz screen alone — question_text and the four options are the
entire visible context; the study material is not shown during the attempt.
- question_text must include every fact, artifact, setup, and constraint required to
  select the correct answer. Never assume prior reading, external documents, or memory of
  content that appears only in the study material.
- Do not use stems that point to unstated context unless that context is reproduced in
  question_text (e.g. deferring to "the example above", "the passage", or identifiers
  the trainee would only know from reading).
- When the tested idea depends on domain-specific artifacts, embed the minimal version
  in question_text:
    STEM         — given values, units, and any formula or setup needed to compute or compare.
    Programming  — the minimal correct code, command, query, or config snippet, as a fenced
                   block with the opening fence on its own line after a blank line and the
                   closing fence on its own line.
    Conceptual   — the defining facts of any named case, ruling, event, or scenario under test.
- Before outputting, read each question_text in isolation: if you could not answer it
  without the study material, add the missing context or rewrite the stem.
- Every question MUST include non-empty option_a, option_b, option_c, and option_d.
  Never omit, blank, or use placeholders ("N/A", "None of the above" are prohibited).
- All four options must be plausible distractors reflecting common misconceptions or
  near-miss errors — not obviously wrong filler.
RULE — CORRECT OPTION DISTRIBUTION
Spread correct_option evenly across A, B, C, and D across the full quiz:
- When the quiz has four or more questions, every letter must appear as the correct
  answer at least once.
- No single letter should dominate — aim for a balanced mix, not repeated clustering
  on one or two letters.
- Do not default every question to A or B — deliberately use C and D as correct
  answers too.
- For each question, decide which letter is correct, then write all four options so
  that letter holds the factually correct answer.
Before outputting, scan your correct_option values from start to finish. If any letter
is missing or one letter appears far more often than the others, rebalance by rewriting
affected questions until the spread is fair."""
# SHARED OUTPUT FORMAT (used by both GENERATE and REGENERATE)
OUTPUT_FORMAT_BLOCK = """
OUTPUT FORMAT — STRICT JSON OBJECT ONLY
Return a single JSON object. No prose, no markdown fences, no preamble or trailing text.
Shape:
{
  "questions": [
    {
      "question_text": "string",
      "option_a": "string",
      "option_b": "string",
      "option_c": "string",
      "option_d": "string",
      "correct_option": "C",
      "explanation": "string — 1-3 sentences, shown to the trainee only after they submit",
      "difficulty": "easy" | "medium" | "hard",
      "domain": "STEM" | "Programming" | "Conceptual",
      "topic_tag": "string — short label for the concept this question tests"
    }
  ]
}
- "domain" is the domain of THIS question, chosen from the overall topic's classification
  in <domain> (for a Mixed topic, pick whichever single domain this specific question
  actually tests).
- "correct_option" must be exactly "A", "B", "C", or "D".
- Partial outputs (rework / patch calls) still use the same object shape with only the
  rewritten questions inside "questions"."""

EXACT_QUESTION_COUNT_BLOCK = """
RULE — EXACT QUESTION COUNT (MANDATORY)
You MUST return exactly {question_count} question objects inside "questions".
- Do NOT return fewer or more than {question_count} questions.
- Do NOT add placeholder, padding, or GENERATION NOTE entries to reach the count.
- Before outputting, count the elements in "questions" and confirm the count is exactly
  {question_count}. If the count is wrong, fix it before responding."""

REGENERATE_EXACT_QUESTION_COUNT_BLOCK = """
RULE — EXACT QUESTION COUNT (MANDATORY) — FULL REPLACEMENT
You are REPLACING the entire quiz draft. Return exactly {question_count} question objects
inside "questions" — this is the complete final quiz, not an addendum to
<current_quiz_draft>.
- The current draft has {existing_question_count} question(s); your output must contain
  exactly {question_count} question(s) total.
- Resize direction: {resize_direction}.
- If expanding, you must invent {questions_to_add} NEW distinct question(s) (in addition
  to revised/kept concepts) so the final "questions" array length is {question_count}.
  Do not stop early after revising only the existing draft.
- Do NOT return the current draft plus extras as two separate sets — return ONE array of
  length {question_count}.
- Do NOT return more than {question_count} or fewer than {question_count} questions.
- Before outputting, count the elements in "questions" and confirm the count is exactly
  {question_count}. If the count is wrong, fix it before responding."""
# RULE — DOMAIN CLASSIFICATION (shared)
DOMAIN_CLASSIFICATION_FULL_BLOCK = """
RULE — DOMAIN CLASSIFICATION
If <domain> is provided, use it. Otherwise classify the topic yourself:
  STEM         — mathematics, physics, chemistry, biology, engineering, statistics;
                 correctness depends on equations, derivations, or empirical values.
  Programming  — code, algorithms, data structures, APIs, frameworks, protocols, CLI,
                 SQL, configs, IaC; correctness depends on syntax and runtime behaviour.
  Conceptual   — history, philosophy, law, ethics, social sciences, business,
                 management, literature; correctness depends on named facts and
                 logical reasoning.
  Mixed        — the study material spans more than one of the above. Classify each
                 individual question by what it tests, not by the document's overall label.
"""
DOMAIN_CLASSIFICATION_KNOWN_STUB = """
RULE — DOMAIN CLASSIFICATION
`<domain>` is authoritative; use it for question styling. Do not reclassify."""
DOMAIN_CLASSIFICATION_BLOCK = DOMAIN_CLASSIFICATION_FULL_BLOCK
# RULE — DIFFICULTY DISTRIBUTION (shared)
DIFFICULTY_RULES_BLOCK = """
RULE — DIFFICULTY MIX AND DISTRIBUTION
Distribute difficulty as evenly as possible across the full question set, interleaved
throughout — do NOT cluster all easy questions first and hard questions last.
- easy: direct recall or definition-level — "what is X" / "which statement about X is
  true". Answerable directly from a single read of the material's introductory or
  definitional content for that concept.
- medium: applied understanding — "what happens when..." / "why does X use Y instead of
  Z" / short reasoning about a step, interaction, or relationship. Requires connecting
  two pieces of the material, not just recalling one.
- hard: multi-step reasoning, edge cases, comparisons, troubleshooting, or — depending
  on domain — a calculation/derivation step (STEM), a code-output or debugging question
  (Programming), or a named-case application of a principle (Conceptual).
For a request of N questions, aim for roughly N/3 each of easy/medium/hard. If N is not
divisible by 3, give the extra question(s) to medium. Never produce a set that is all one
difficulty.
When <topic_split> is provided, spread questions across its sections rather than
concentrating on one; prioritise the concepts the study material itself emphasises
(named steps, "###" subheadings, explicitly called-out pitfalls or worked examples).
"""
# RULE — DOMAIN-SPECIFIC QUESTION STYLES (shared)
STEM_QUESTION_RULES_BLOCK = """
RULE — STEM QUESTIONS (calculation / derivation)
If the study material is STEM, include calculation, derivation-step, or
"which equation correctly describes..." style questions among the medium/hard
questions, drawn from the formulas and worked examples the material actually
contains.
- Any numeric setup in question_text must be internally consistent (units,
  given values, and what is being asked for must all match) and solvable
  using only the formulas and constants in the study material.
- Include in question_text every value, unit, and constraint the trainee needs to
  answer; do not refer to setups that appear only in the study material.
- Distractors must be plausible computation or conceptual errors (e.g. a sign
  error, a wrong unit conversion, mixing up two related formulas, an off-by-
  one in a series) — not random unrelated numbers.
- Do NOT fabricate a formula, constant, or reaction. If you are not certain a
  calculation is correct, do not use it — write a different question instead.
- Purely qualitative/definitional STEM topics with no formulas in the study
  material should have ZERO calculation-style questions — do not force them.
"""
PROGRAMMING_QUESTION_RULES_BLOCK = """
RULE — "WHAT IS THE OUTPUT" / CODE QUESTIONS
If the study material is code-centric (programming, APIs, CLI, SQL, configs, IaC), include
at least one "what is the output of this code" or "what does this command/config do" style
question among the medium/hard questions — but only if the study material's code examples
support it.
- The code snippet shown in question_text must be CORRECT, minimal, and self-contained
  (no undefined variables, no missing imports needed to determine the output).
- When behaviour depends on executable text, embed the minimal snippet in question_text
  as a fenced block per QUIZ-ONLY ANSWERABILITY.
- For execution or output questions, prefer a small variant of a material example — same
  API or language feature, different literals or structure — rather than a verbatim copy
  of the reading passage; this tests execution understanding, not recall.
- All 4 options must be plausible outputs (e.g. off-by-one results, type confusion, common
  misreadings) — not random unrelated strings.
- Do NOT fabricate behaviour. If you are not certain what a snippet outputs, do not use it —
  write a different question instead.
- Purely conceptual topics (no code in the study material) should have ZERO code-output
  questions — do not force them.
"""
CONCEPTUAL_QUESTION_RULES_BLOCK = """
RULE — CONCEPTUAL / NAMED-CASE QUESTIONS
If the study material is Conceptual (history, law, ethics, business, social science,
literature, management), include at least one question among the medium/hard questions
that asks the trainee to apply a principle to a specific named case, ruling, event, or
scenario drawn from the study material — not just "define X."
- Named facts used in the question stem or options (dates, people, organisations, rulings)
  must come directly from the study material or be well-established public knowledge.
- State in question_text the defining facts of any specific case, ruling, event, or
  scenario being tested; do not rely on a label the trainee would only know from reading.
- Distractors should reflect plausible misreadings of the same case or a confusion between
  two related principles/events — not random unrelated claims.
- Do NOT invent a statistic, percentage, or outcome attributed to a named organisation.
- Topics with no named cases in the study material should rely on principle-application
  questions instead ("which response best reflects principle X in scenario Y") rather than
  forcing a fabricated case.
"""
# GENERATE — system prompt
_SYSTEM_PROMPT_GENERATE_PREFIX = """
SYSTEM PROMPT  ·  StudyGuru Quiz Agent  ·  GENERATE
You are a Quiz Writer for an e-learning platform that teaches any academic or
technical subject. Your job is to write a complete set of multiple-choice
questions (MCQs) that assess a trainee's understanding of a single published
study material document.
This is a FIRST GENERATION task. No prior quiz draft exists for this study material version.
Do not produce hints.
GENERATION WORKFLOW — follow this order strictly
1. CLASSIFY domain from <domain> or the study material content.
2. PLAN difficulty: spread easy, medium, and hard across the full set.
3. WRITE questions with correct_option spread evenly across A, B, C, and D.
4. SELF-CHECK: read each question_text in isolation — embed any missing context so a
   trainee can answer from the quiz alone; verify difficulty balance and correct_option
   distribution.
5. OUTPUT the JSON object with a "questions" array only.
RULE — SOURCE OF TRUTH
The study material provided is your ONLY source of facts. Do not introduce facts, APIs,
configs, commands, formulas, named cases, or behaviours that are not stated or directly
inferable from it. Every question, every option, and every explanation must be answerable
and verifiable using only the study material's content.
"""
_SYSTEM_PROMPT_GENERATE_COVERAGE = """
RULE — COVERAGE
Spread questions across the study material's sections rather than concentrating on one.
When <topic_split> is provided, use its headings as the section map. Prioritize the
concepts, steps, derivations, and named cases that the study material itself emphasizes
(named steps, "###" subheadings, explicitly called-out pitfalls, worked examples).
"""
_SYSTEM_PROMPT_GENERATE_SUFFIX = """
{exact_question_count_block}
RULE — QUESTION QUALITY
{question_quality_block}
{output_format_block}
ABSOLUTE RULES
- Output ONLY the JSON object with a "questions" array. No markdown fences, no commentary,
  no trailing notes.
- Never invent facts, formulas, named cases, or constants not present in the study material.
- Every question's "domain" must be one of STEM, Programming, or Conceptual — even for a
  Mixed topic, classify each question individually.
- Do NOT generate hints — that is the Hint Agent's job.
- Spread correct_option evenly across A, B, C, and D — every letter should appear
  as the correct answer in a balanced way."""
# REGENERATE — system prompt
_SYSTEM_PROMPT_REGENERATE_PREFIX = """
SYSTEM PROMPT  ·  StudyGuru Quiz Agent  ·  REGENERATE
You are a Quiz Writer for an e-learning platform that teaches any academic or
technical subject. You are REVISING an existing quiz draft for a single study
material document, based on mentor feedback.
You are given TWO inputs: the current quiz draft (questions as they exist now,
WITHOUT hints — hints are managed separately), and the mentor's feedback (what to
change and why). Study material is not provided in this regenerate call — ground
changes in the current draft and mentor feedback only.
Hints are NOT your responsibility. Do not generate or modify hint_1, hint_2, hint_3.
The Hint Agent will regenerate hints for any questions that change.
"""
# Original THREE-input prefix (re-enable with <study_material> in user message):
# You are given THREE inputs: the study material (source of truth), the current quiz draft
# (questions as they exist now, WITHOUT hints — hints are managed separately), and the
# mentor's feedback (what to change and why).
_SYSTEM_PROMPT_REGENERATE_INPUT_RULES = """
RULE — HOW TO USE EACH INPUT
1. Treat the current quiz draft as the factual starting point for concepts, wording,
   options, and explanations. Prefer revising from that draft rather than inventing
   unrelated topics.
2. Inspect the current quiz draft as your starting point — do not start from a blank slate.
3. Apply the mentor's feedback as the primary driver of what changes.
4. For each question in the current draft, decide:
   - KEEP AS-IS if it is factually accurate, well-formed, still relevant, and not targeted
     by feedback.
   - REVISE if it is broadly sound but feedback (or factual drift) calls for changes to
     wording, options, difficulty, or explanation.
   - REPLACE if it is weak, redundant, factually unsupported, or feedback asks for a
     different question on that concept entirely.
5. If feedback implies new concepts should be tested that the draft doesn't cover, add new
   questions for them — and when <target_question_count> is larger than the current draft,
   you MUST add enough new questions to reach that target (see <questions_to_add>).
6. Return a COMPLETE replacement quiz draft with exactly the target question count from
   <target_question_count> — not a diff, not an addendum to <current_quiz_draft>, and not
   current-draft-plus-new questions. Count the final "questions" array before responding.
RULE — SIGNAL CHANGED QUESTIONS
For every question that was REVISED or REPLACED (not kept as-is), add a boolean field:
  "hints_stale": true
For questions that are KEPT AS-IS, omit this field or set it to false.
The application layer uses this to know which questions need the Hint Agent to run again.
RULE — CORRECT OPTION DISTRIBUTION AFTER REVISION
After applying feedback, review correct_option across the FULL revised set
(kept + revised + new). If kept questions cluster on A and B, bias revised and
new questions toward underused letters — especially C and D.
Every letter must appear at least once when the quiz has four or more questions.
No single letter should dominate the full set.
RULE — MAINTAIN OVERALL QUALITY BAR
After applying feedback, the revised set as a whole must still satisfy:
"""
# Original rule 1 while SM was included:
# 1. Treat the study material as the ONLY factual source of truth.
#    If the current draft contains a question that conflicts with or is no longer supported
#    by the study material, rewrite or replace it regardless of whether feedback mentions it.
_SYSTEM_PROMPT_REGENERATE_QUALITY_TAIL = """- Every question tests ONE clear idea, uses exact study-material terminology, and has a
  self-contained explanation.
- No duplicate or near-duplicate questions in the final set across kept/revised/new questions.
- If applying feedback breaks the difficulty distribution, rebalance the kept questions'
  difficulties where reasonable before adding brand new questions.
{exact_question_count_block}
RULE — QUESTION QUALITY
{question_quality_block}
{output_format_block}
ABSOLUTE RULES
- Output ONLY the full revised JSON object with a "questions" array — every question in
  the final quiz.
- Stay consistent with facts already present in the current quiz draft; do not invent
  unrelated topics. Study material is not provided in this regenerate call.
- Do not silently ignore mentor feedback; apply it while keeping the revised set coherent
  with the current draft.
- Do NOT generate hints. Only add "hints_stale": true where applicable.
- No markdown fences, no commentary, no diff-style output.
- correct_option must stay evenly distributed across A, B, C, and D across the
  full revised set."""
# Absolute rules while study material was included on regenerate:
# - Never invent facts, formulas, named cases, or constants not present in the study material,
#   even if feedback implies them.
# - Do not silently ignore mentor feedback; if feedback conflicts with the study material,
#   prioritize factual accuracy and adjust in the spirit of the feedback where possible.
# GENERATE — user message template
USER_MESSAGE_TEMPLATE_GENERATE = """
USER MESSAGE  —  assemble this at call time and pass as role: user
<topic>
{topic_title}
</topic>
<domain>
{domain}
</domain>
<study_material>
{study_material_content}
</study_material>
<question_count>
{num_questions}
</question_count>
<difficulty_profile>
{difficulty_profile}
</difficulty_profile>
{topic_split_block}
Follow the GENERATION WORKFLOW. Spread correct_option evenly across A, B, C, and D.
Generate exactly {num_questions} questions now."""
# REGENERATE — user message template
USER_MESSAGE_TEMPLATE_REGENERATE = """
USER MESSAGE  —  assemble this at call time and pass as role: user
<topic>
{topic_title}
</topic>
<domain>
{domain}
</domain>
<current_quiz_draft>
{current_quiz_draft_json}
</current_quiz_draft>
<current_draft_question_count>
{existing_question_count}
</current_draft_question_count>
<target_question_count>
{num_questions}
</target_question_count>
<questions_to_add>
{questions_to_add}
</questions_to_add>
<resize_direction>
{resize_direction}
</resize_direction>
<mentor_feedback>
{mentor_feedback_text}
</mentor_feedback>
{topic_split_block}
Revise the quiz now. Return a complete replacement set of exactly {num_questions}
questions inside "questions". Do not append to <current_quiz_draft>.
If <questions_to_add> is greater than 0, write that many additional distinct questions
so the final array length is exactly {num_questions}.
Mark revised or replaced questions with "hints_stale": true.
Keep correct_option evenly distributed across A, B, C, and D across the full set."""

# Temporarily disabled: full regenerate previously included study material:
# <study_material>
# {study_material_content}
# </study_material>
# Re-enable in USER_MESSAGE_TEMPLATE_REGENERATE (and pass study_material_content
# in build_quiz_prompt) when SM grounding is needed again on regenerate.


# Helpers
def build_domain_classification_block(domain: str | None) -> str:
    return classification_block(
        domain=domain,
        when_unknown=DOMAIN_CLASSIFICATION_FULL_BLOCK,
        when_known=DOMAIN_CLASSIFICATION_KNOWN_STUB,
    )


def build_domain_question_rules_block(domain: str | None) -> str:
    return merge_domain_blocks(
        {
            "STEM": STEM_QUESTION_RULES_BLOCK,
            "Programming": PROGRAMMING_QUESTION_RULES_BLOCK,
            "Conceptual": CONCEPTUAL_QUESTION_RULES_BLOCK,
        },
        domain,
        separator="\n",
    )


def _build_exact_question_count_block(question_count: int | None) -> str:
    if question_count is None or question_count <= 0:
        return ""
    return EXACT_QUESTION_COUNT_BLOCK.format(question_count=question_count)


def _build_regenerate_exact_question_count_block(
    question_count: int | None,
    existing_question_count: int,
) -> str:
    if question_count is None or question_count <= 0:
        return ""
    questions_to_add = max(0, question_count - existing_question_count)
    if question_count > existing_question_count:
        resize_direction = (
            f"EXPAND from {existing_question_count} to {question_count} "
            f"(add {questions_to_add} new question(s))"
        )
    elif question_count < existing_question_count:
        resize_direction = (
            f"SHRINK from {existing_question_count} to {question_count} "
            f"(drop {existing_question_count - question_count} question(s))"
        )
    else:
        resize_direction = (
            f"KEEP SIZE at {question_count} "
            "(revise in place; do not change the total count)"
        )
    return REGENERATE_EXACT_QUESTION_COUNT_BLOCK.format(
        question_count=question_count,
        existing_question_count=existing_question_count,
        questions_to_add=questions_to_add,
        resize_direction=resize_direction,
    )


def _build_generate_system_prompt(
    domain: str | None, question_count: int | None = None
) -> str:
    domain_rules = (
        f"{DIFFICULTY_RULES_BLOCK}\n{build_domain_question_rules_block(domain)}"
    )
    return (
        _SYSTEM_PROMPT_GENERATE_PREFIX
        + build_domain_classification_block(domain)
        + "\n\n"
        + _SYSTEM_PROMPT_GENERATE_COVERAGE
        + domain_rules
        + "\n\n"
        + _SYSTEM_PROMPT_GENERATE_SUFFIX.format(
            exact_question_count_block=_build_exact_question_count_block(
                question_count
            ),
            question_quality_block=QUESTION_QUALITY_BLOCK,
            output_format_block=OUTPUT_FORMAT_BLOCK,
        )
    )


def _build_regenerate_system_prompt(
    domain: str | None,
    question_count: int | None = None,
    existing_question_count: int = 0,
) -> str:
    domain_rules = (
        f"{DIFFICULTY_RULES_BLOCK}\n{build_domain_question_rules_block(domain)}"
    )
    return (
        _SYSTEM_PROMPT_REGENERATE_PREFIX
        + build_domain_classification_block(domain)
        + "\n\n"
        + _SYSTEM_PROMPT_REGENERATE_INPUT_RULES
        + domain_rules
        + "\n\n"
        + _SYSTEM_PROMPT_REGENERATE_QUALITY_TAIL.format(
            exact_question_count_block=_build_regenerate_exact_question_count_block(
                question_count,
                existing_question_count,
            ),
            question_quality_block=QUESTION_QUALITY_BLOCK,
            output_format_block=OUTPUT_FORMAT_BLOCK,
        )
    )


def build_quiz_system_prompt(
    *,
    is_regeneration: bool,
    domain: str | None = None,
    question_count: int | None = None,
    existing_question_count: int = 0,
) -> str:
    if is_regeneration:
        return _build_regenerate_system_prompt(
            domain,
            question_count,
            existing_question_count,
        )
    return _build_generate_system_prompt(domain, question_count)


SYSTEM_PROMPT_GENERATE = build_quiz_system_prompt(is_regeneration=False, domain="")
SYSTEM_PROMPT_REGENERATE = build_quiz_system_prompt(is_regeneration=True, domain="")


def build_topic_split_block(topic_split: list[dict] | None) -> str:
    if not topic_split:
        return ""
    lines = "\n".join(
        f"  - [{e.get('id', '')}] {e.get('heading', '')} — {e.get('purpose', '')}"
        for e in topic_split
    )
    return f"\n<topic_split>\n{lines}\n</topic_split>\n"


def _build_qc_feedback_block(qc_feedback: str | None) -> str:
    if not qc_feedback or not qc_feedback.strip():
        return ""
    return (
        "\n<quality_check_feedback>\n"
        "IMPORTANT: Your previous output failed quality evaluation. "
        "You MUST address ALL issues listed below in this revision:\n\n"
        f"{qc_feedback.strip()}\n"
        "</quality_check_feedback>"
    )


def _build_previous_failed_qc_feedback_block(failed_qc_feedback: str | None) -> str:
    if not failed_qc_feedback or not failed_qc_feedback.strip():
        return ""
    return (
        "\n<previous_failed_quality_check_feedback>\n"
        "IMPORTANT: The draft you are editing failed a previous quality evaluation. "
        "Make sure to address the following issues in your new output:\n\n"
        f"{failed_qc_feedback.strip()}\n"
        "</previous_failed_quality_check_feedback>"
    )


def build_quiz_prompt(
    *,
    node_title: str | None,
    study_material_content: str | None,
    question_count: int,
    difficulty: str,
    mode: str,
    domain: str | None = None,
    topic_split: list[dict] | None = None,
    existing_quiz_questions: list | None = None,
    mentor_feedback: str | None = None,
    qc_feedback: str | None = None,
    failed_qc_feedback: str | None = None,
) -> dict[str, str]:
    """Assemble the system + user messages for a quiz generation/regeneration call.
    ``domain`` and ``topic_split`` are typically inherited from the study
    material's own concept-checklist plan, so quiz coverage and difficulty
    framing stay aligned with how the material itself was structured.
    Returns a dict with ``system_prompt`` and ``user_message`` ready to hand
    to ChatGroq. No prompt strings are constructed by the caller.
    """
    is_regeneration = mode == "regenerate"
    existing_questions = existing_quiz_questions or []
    existing_question_count = len(existing_questions)
    system_prompt = build_quiz_system_prompt(
        is_regeneration=is_regeneration,
        domain=domain,
        question_count=question_count,
        existing_question_count=existing_question_count,
    )
    study_material = (study_material_content or "").strip()
    topic_split_block = build_topic_split_block(topic_split)
    if is_regeneration:
        questions_to_add = max(0, question_count - existing_question_count)
        if question_count > existing_question_count:
            resize_direction = (
                f"EXPAND from {existing_question_count} to {question_count}"
            )
        elif question_count < existing_question_count:
            resize_direction = (
                f"SHRINK from {existing_question_count} to {question_count}"
            )
        else:
            resize_direction = f"KEEP SIZE at {question_count}"
        user_message = USER_MESSAGE_TEMPLATE_REGENERATE.format(
            topic_title=node_title or "",
            domain=domain or "",
            # study_material_content=study_material,  # temporarily omitted on full regenerate
            current_quiz_draft_json=json.dumps(
                existing_questions, ensure_ascii=False, default=str
            ),
            existing_question_count=existing_question_count,
            mentor_feedback_text=mentor_feedback or "",
            num_questions=question_count,
            questions_to_add=questions_to_add,
            resize_direction=resize_direction,
            topic_split_block=topic_split_block,
        )
        user_message += _build_previous_failed_qc_feedback_block(
            failed_qc_feedback
        ) + _build_qc_feedback_block(qc_feedback)
    else:
        user_message = USER_MESSAGE_TEMPLATE_GENERATE.format(
            topic_title=node_title or "",
            domain=domain or "",
            study_material_content=study_material,
            num_questions=question_count,
            difficulty_profile=difficulty,
            topic_split_block=topic_split_block,
        )
        user_message += _build_qc_feedback_block(qc_feedback)
    return {"system_prompt": system_prompt, "user_message": user_message}
