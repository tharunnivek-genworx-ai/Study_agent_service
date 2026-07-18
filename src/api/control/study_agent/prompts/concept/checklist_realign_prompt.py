"""Post-research checklist realign prompts — conservative edit of draft plan against GT notes."""

from __future__ import annotations

import json
from typing import Any

from src.api.control.study_agent.prompts.concept.shared_blocks import (
    JSON_OUTPUT_SCHEMA,
    STRUCTURAL_INTEGRITY_BLOCK,
    TOPIC_SPLIT_STYLE_BLOCK,
)

# Soft ceiling for <research_notes> in the user message (chars).
_RESEARCH_NOTES_MAX_CHARS = 12_000
_TRUNCATION_MARKER = "\n…[truncated]…\n"

DOMAIN_REUSE_FROM_DRAFT_PLAN_BLOCK = """\
Copy the "domain" field from <draft_plan> verbatim into your output. The topic's domain is fixed for this run — never reclassify it. Realignment may revise topic_split and must_cover_checklist only."""

_REALIGN_CONTRACT_BLOCK = """\
REALIGN CONTRACT
1. ROLES — <draft_plan> owns the outline spine (section count/headings/ids, rough concept slots). <research_notes> own the evidence catalog — what required Family A2/B items may demand. Output a COMPLETE JSON plan (domain + topic_split + must_cover_checklist), not a delta or patch.
2. INSTRUCTION WEIGHING — <teaching_instruction> wins on conflicts when it is specific (named APIs, experiments, section requests, depth demands). If the instruction is general or underspecified, still allow note-backed improvements that strengthen fidelity — do NOT freeze the draft merely because the instruction is short.
3. EDIT BUDGET
   - Preserve domain verbatim.
   - Keep-budget applies after note-support filtering: among note-viable items, keep at least max(3, len(draft must_cover) − 2) draft must_cover items (prefer same id; concept may be reframed; depth_gate / requirement may be rewritten).
   - At most +1 new topic_split section and at most +2 net new must_cover items versus the draft.
   - Do not preserve impossible draft wording merely to hit keep-count.
4. REWRITE-IN-PLACE DEFAULT — Default action is rewrite existing requirement / depth_gate (prefer same id / section_id). Add +1 topic_split only when notes introduce a distinct concept that cannot fit an existing heading. Anti-pattern: a new section whose purpose restates the topic title or "fundamentals of X".
5. REQUIRED A2/B MUST CITE NOTE ARTIFACT — Every required Family A2 or B item must name a concrete note artifact that appears in <research_notes> (equation/relation text, stoichiometry/count, named experiment, or code/API signature). If none exists for that concept → rewrite to a note-supported sibling, demote to recommended, or drop.
6. NOTE ARTIFACT BINDING — Do not invent the artifact that a required gate demands: the equation/relation, stoichiometry/count, API/signature, or named experiment/case must appear in <research_notes> (or have a clear equivalent there). Generation may later choose ordinary classroom numbers to teach a note-backed relation, but this plan must not demand a parameter class, scenario class, measurement framework, or named particular absent from the notes.
7. EQUATION / RELATION PRIORITY — If notes contain an explicit equation/relation (or stoichiometry/count / named reaction fact) relevant to a checklist concept, that item should be Family A2 (A1 only when pedagogy is truly a ground-up derivation), and the depth_gate must include the note's equation/relation text (or clear equivalent). Family C is for named cases/events without a primary equation/code artifact — not for vaguely mentioning a quantity.
8. NOTE-UNSUPPORTED DRAFT ITEMS — For each draft item before output: (1) Can this item's evidence be satisfied from notes (or honest teaching of a note-covered concept)? (2) If no → rewrite to a note-supported sibling in the same section → else demote → else drop.
9. DRAFT-DEBT SWEEP — Inspect every draft requirement/depth_gate that asks learners to substitute, calculate, or apply with unspecified values, or that names a scenario, API, or experiment. If notes contain a stronger sibling artifact for the same concept, rewrite the gate in place to cite that artifact. If notes contain no supporting artifact, rewrite to a note-supported sibling in the same section; otherwise demote; otherwise drop. Keep-count is satisfied by preserving the same id with supported rewritten wording — never by preserving unsupported text.
10. SECTION LOAD — When a section already owns 2 must_cover items, prefer rewriting an existing item in place over adding another required item to that section.
11. ANTI-BLOAT — Do NOT import every note topic. Only add or reframe an item when the note concept clearly strengthens teaching for this node. Never invent a Family B item for a STEM topic with no software component; never put derivation vocabulary on Programming Family B items.
12. UNDERSPECIFIED INSTRUCTION — choose the smallest set of note-backed upgrades that improve fidelity (named experiments, real APIs/code from notes, core equations) without syllabus expansion."""

_TOPIC_SPLIT_REALIGN_SIZING_BLOCK = """\
- Stay within 4–8 sections. Prefer rewrite-in-place of existing headings/purposes over exploding the outline.
- At most +1 new topic_split section versus <draft_plan>, and only when notes introduce a distinct concept that cannot fit an existing heading. If a note-backed concept fits an existing section, keep it there.
- Do not add a section whose purpose restates the topic title or "fundamentals of X".
- Headings stay topic-specific (see style rules below)."""

_CHECKLIST_REALIGN_RULES_BLOCK = """\
- A depth_gate must be a bar that generic or surface-level coverage cannot satisfy.
- priority: "required" — absence is a critical failure. "recommended" — absence is a significant gap.
- section_id must name the single topic_split section where a reviewer will find all depth_gate evidence. Never assign a checklist item to an introductory section (typically ts_1) unless that section is where the concept's complete treatment actually lives.
- Each topic_split section should own at most 2 must_cover items, and every section should own at least 1.
- Include ONLY the fields id, concept, requirement, priority, section_id, and depth_gate."""

# Compact A/B/C policy: decision test + skeletons + word bans (no full generation essay / worked examples).
_COMPACT_EVIDENCE_FAMILY_BLOCK = """\
Every must_cover_checklist item belongs to exactly ONE evidence family. Decide per item from what that item is about — never from the document's overall domain label, and never from surface verbs like "implement," "apply," or "method."

FAMILY DECISION TEST — run in order; stop at the first match:
1. CODE TEST: Would correctly satisfying this item require producing runnable source code (function, script, API call, data structure, algorithm implementation), where the evidence of mastery is the code plus its runtime behaviour?
   - YES → FAMILY B.
   - NO → continue. A mathematical technique, chemical/physical mechanism, or pencil-and-paper procedure is NOT code merely because it has ordered steps.
2. EQUATION/EMPIRICAL TEST: Does this item's correctness rest on an equation, derivation/proof, or quantitative/empirical/physical fact?
   - YES → FAMILY A. Then run the A1/A2 DEPTH TEST below.
   - NO → continue.
3. NAMED-CASE TEST: Does this item's correctness rest on a named case, ruling, organisation, event, or other real-world particular explained through prose?
   - YES → FAMILY C.

If torn between families, prefer A or C over B. Family B is narrowest — never a default. A STEM plan with several Family A items and zero Family B is normal when there is no software component. Do not manufacture Family B for STEM without a real code artifact. A Programming plan may still contain A or C items when that item's own correctness does not hinge on runnable code.

A1/A2 DEPTH TEST (Family A only):
   - A1 (ground-up derivation) ONLY when the pedagogical point IS watching a result built from a primitive definition or law. Rare: most documents have 0–1 A1 items, occasionally 2 for separate foundational pillars.
   - A2 (applied/worked use) is the default for every other Family A item.
   - Hard ceiling: across the ENTIRE must_cover_checklist, at most 2 items may be A1.

For each family/mode, copy its requirement and depth_gate skeleton and fill only the bracketed parts — do not invent a new sentence structure or blend families.

FAMILY A1 — MATHEMATICAL / LOGICAL DERIVATION
requirement skeleton:
  "<Derive/Prove/Show that> <target>, starting from <named equation, law, or foundational construction>, showing <the required steps> until <the final result>."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "Derivation begins from [named starting equation, law, or construction]; the chain contains at least [pick a concrete number, 4 or higher] sequential steps, each expressed as its own formula_block entry that follows mechanically from the one before it; all variables or terms are defined (with units, where physical) on first use; correct final result [state the result] reached and stated."
SCHEMA NOTE: STEM sections have only formula_blocks — never write a depth_gate that can only be satisfied by a diagram/figure.

FAMILY A2 — MATHEMATICAL/EMPIRICAL APPLICATION
requirement skeleton:
  "<Calculate/Apply/Determine/Solve for> <target> using <the named equation, rule, or law>, substituting <the specific values or variables involved>, and explain what the result means."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "States the applicable [named equation, rule, or law]; substitutes the specific [values or variables] used; arrives at the correct result [state the result]; explains what the result means in context."
A2 FILL RULE — Fill brackets from note equation/relation text and/or named note quantities or counts. If notes contain no numeric literals, require substitution of those named quantities or a standard classroom instance of the named note relation. Never invent a new measurement framework, parameter class, scenario class, or fabricated API. When notes supply an equation/relation for this concept, name that artifact text (or clear equivalent) in the depth_gate.

FAMILY B — IMPLEMENTATION
requirement skeleton:
  "<Implement/Build/Write/Debug> <artifact> that <behaviour>, and explain what the code does/outputs and why, including <a named scenario or edge case>."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "At least one self-contained, runnable code block demonstrating [the behaviour or concept]; explanation explicitly states what the code outputs or returns and why; behaviour is shown for [a normal-case scenario] and for [an edge-case scenario]."
Evidence is a single inline code block — never a multi-file repo or downloadable project.

FAMILY C — INTERPRETIVE
requirement skeleton:
  "Explain how <a named case, ruling, organisation, or event> demonstrates <the concept>, including <the causal or interpretive reasoning>."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "[The concept] is defined in prose; the specific named case, ruling, organisation, or event — [name it] — is presented; the causal or interpretive reasoning connecting it to [the concept] is explained."

HARD WORD BAN — apply after drafting, before output
These words belong ONLY to Family A1. If the item is A2, B, or C, none may appear in its requirement or depth_gate:
  derive, derivation, derived, prove, proof, theorem, algebraic, formula notation, closed form, recurrence relation.
These words belong ONLY to Family B. They must not appear in A1, A2, or C items:
  code block, runnable, function call, API.
(Exception: if teaching_instruction explicitly asks for a supporting code example inside a STEM or Conceptual section, that code is additive to — never a substitute for — that item's own A1/A2 or C evidence.)

SKELETON COMPLETION — every bracketed placeholder must be replaced with topic-specific content. A literal "[" or "]" in output is a failure. Recount A1 items; if ≥ 3, rewrite the weakest as A2."""

_USER_MESSAGE_CLOSING = (
    "\nRealign the JSON plan now. "
    "Preserve domain from <draft_plan>. Prefer rewrite-in-place of existing gates over adding sections. "
    "Draft is outline spine; notes are the evidence catalog. "
    "For every must_cover item you add or rewrite, pick its evidence family (A/B/C) from what the item is about, "
    "copy that family's depth_gate skeleton, and fill only the brackets. "
    "Every required Family A2 or B item must cite a concrete note artifact from <research_notes>. "
    "Bind each required gate to a note-backed artifact; classroom numbers may later instantiate a named note relation, "
    "but the plan must not invent a new parameter, scenario, measurement framework, API, experiment, or named case. "
    "Sweep unsupported draft debt and prefer rewrite-in-place when a section already owns 2 items. "
    "Do not import every note topic."
)


def truncate_research_notes(
    text: str,
    *,
    max_chars: int = _RESEARCH_NOTES_MAX_CHARS,
) -> str:
    """Return notes truncated with an explicit marker when over max_chars (head + tail)."""
    if max_chars < 1:
        return ""
    cleaned = (text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned

    marker = _TRUNCATION_MARKER
    budget = max_chars - len(marker)
    if budget < 2:
        return cleaned[:max_chars]

    head_len = budget // 2
    tail_len = budget - head_len
    return cleaned[:head_len] + marker + cleaned[-tail_len:]


def build_checklist_realign_system_prompt() -> str:
    """System prompt for post-research checklist realignment against ground-truth notes."""
    return f"""\
You are a curriculum architect. You are realigning an existing draft JSON plan \
(topic_split + must_cover_checklist) against external research notes so study-material \
generation and QC use a note-faithful, domain-safe checklist.

STEP 1 — DOMAIN
{DOMAIN_REUSE_FROM_DRAFT_PLAN_BLOCK}

STEP 2 — REALIGN AGAINST NOTES
{_REALIGN_CONTRACT_BLOCK}

STEP 3 — topic_split
{_TOPIC_SPLIT_REALIGN_SIZING_BLOCK}
{TOPIC_SPLIT_STYLE_BLOCK}

STEP 4 — must_cover_checklist (add or rewrite only within the edit budget)
{_COMPACT_EVIDENCE_FAMILY_BLOCK}

OTHER must_cover_checklist RULES
{_CHECKLIST_REALIGN_RULES_BLOCK}

{STRUCTURAL_INTEGRITY_BLOCK}

STEP 5 — SELF-CHECK BEFORE WRITING OUTPUT
  □ Domain equals <draft_plan>.domain exactly?
  □ Roles respected — draft = outline spine; notes = evidence catalog?
  □ Kept ≥ max(3, draft_must_cover_count − 2) note-viable draft items (ids preferred); did not keep unsupported wording just for count?
  □ At most +1 topic_split section (only for a distinct note concept) and +2 net new must_cover items?
  □ Rewrite-in-place default — no generic "fundamentals of X" +1 section?
  □ Every required A2/B cites a concrete note artifact (equation/relation, stoichiometry/count, named experiment, or code/API signature)?
  □ NOTE ARTIFACT BINDING — no gate invents a parameter/scenario/measurement framework or named particular absent from notes?
  □ EQUATION/RELATION PRIORITY — note equations/relations bound as A2 naming the artifact (not vague Family C)?
  □ DRAFT-DEBT SWEEP — unsupported substitutions/scenarios/APIs/experiments rewritten to a note artifact, demoted, or dropped?
  □ SECTION LOAD — sections already owning 2 items were strengthened by rewrite-in-place rather than another required item?
  □ No syllabus bloat — only note-backed upgrades that strengthen this node?
  □ No Family B for STEM without software; no A1 vocabulary on B/C/A2 items?
  □ STRUCTURAL INTEGRITY: every section_id resolves; every topic_split owns ≥ 1 item?
  □ No unfilled bracket placeholders; A1 count ≤ 2?
Do not output until every check passes.

{JSON_OUTPUT_SCHEMA}"""


def build_checklist_realign_user_message(
    topic_title: str,
    *,
    teaching_instruction: str = "",
    draft_plan: dict[str, Any],
    research_notes: str,
) -> str:
    """User message: topic, instruction, draft plan JSON, truncated research notes."""
    parts: list[str] = [
        f"<topic>{topic_title}</topic>",
    ]

    instruction = (teaching_instruction or "").strip()
    if instruction:
        parts.append(
            f"\n<teaching_instruction>\n{instruction}\n</teaching_instruction>"
        )

    plan_json = json.dumps(draft_plan, ensure_ascii=False)
    parts.append(f"\n<draft_plan>\n{plan_json}\n</draft_plan>")

    notes = truncate_research_notes(research_notes)
    parts.append(f"\n<research_notes>\n{notes}\n</research_notes>")
    parts.append(_USER_MESSAGE_CLOSING)

    return "\n".join(parts)
