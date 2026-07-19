"""Post-research checklist realign prompts — domain-routed note-faithful plan edit.

Domain comes from graph state / draft_plan (already fixed). Only the matching
domain policy is injected into the system prompt — never all four.
"""

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

_VALID_DOMAINS = frozenset({"STEM", "Programming", "Conceptual", "Mixed"})

DOMAIN_REUSE_FROM_DRAFT_PLAN_BLOCK = """\
Copy the "domain" field from <draft_plan> verbatim into your output. The topic's \
domain is fixed for this run — never reclassify it. Realignment may revise \
topic_split and must_cover_checklist only."""

_REALIGN_ROLE_BLOCK = """\
You are a syllabus alignment compiler. Transform the draft JSON plan into a \
complete, note-faithful syllabus plan that a downstream study-material writer \
and reviewer will execute.

Authority order:
1. Specific <teaching_instruction> wins on requested scope/emphasis.
2. <research_notes> own the concrete artifacts required gates may demand.
3. <draft_plan> supplies reusable section/id scaffold and concept candidates.
4. General knowledge may clarify terminology but must not invent a required \
equation, API, experiment, case, parameter class, measurement framework, or \
scenario absent from both the instruction and the notes.

A specific instruction may require a concept not present in notes — keep that \
concept, but do not pretend notes supplied an artifact they did not. A vague \
instruction ("explain thoroughly") does not freeze unsupported draft wording \
and does not authorize unrelated syllabus expansion."""

_TOPIC_SPLIT_REALIGN_SIZING_BLOCK = """\
- Stay within 4–8 sections. Prefer rewrite-in-place of existing headings/purposes \
over exploding the outline.
- At most +1 new topic_split section versus <draft_plan>, and only when notes \
introduce a distinct concept that cannot fit an existing heading.
- Do not add a section whose purpose restates the topic title or "fundamentals of X".
- Headings stay topic-specific (see style rules below)."""

_CHECKLIST_ITEM_FIELDS_BLOCK = """\
- Include ONLY the fields id, concept, requirement, priority, section_id, and \
depth_gate.
- priority: "required" — absence is a critical failure. "recommended" — absence \
is a significant gap.
- section_id must name the single topic_split section where a reviewer will find \
all depth_gate evidence. Never assign a checklist item to an introductory \
section (typically ts_1) unless that section is where the concept's complete \
treatment actually lives.
- Each topic_split section should own at most 2 must_cover items, and every \
section should own at least 1.
- A depth_gate must be a bar that generic or surface-level coverage cannot \
satisfy."""

_PRESERVATION_BUDGET_BLOCK = """\
EDIT / PRESERVATION BUDGET (apply after support filtering):
- Among note-viable items, keep at least max(3, len(draft must_cover) − 2) draft \
must_cover items (prefer same id; concept may be reframed; requirement / \
depth_gate may be fully rewritten).
- Keep-count is satisfied by preserving the same id with supported rewritten \
wording — never by preserving unsupported text.
- At most +2 net new must_cover items versus the draft.
- Do not import every note topic — only note-backed upgrades that strengthen \
this node."""

# ---------------------------------------------------------------------------
# Domain-specific policies (only one is injected per call)
# ---------------------------------------------------------------------------

_STEM_POLICY_BLOCK = """\
DOMAIN POLICY — STEM (this run is STEM; do not invent Programming/Conceptual \
defaults)

SAFE DEFAULTS
- Default quantitative item is STEM APPLICATION, not derivation.
- Zero derivations and zero code items are normal and expected — and for this STEM domain run, zero code items are mandatory.
- Do not create code because notes say process, procedure, algorithm, model, \
simulation, implementation, method, steps, system, calculation, or computing.
- Do not force an equation exercise into every section — mechanisms, \
experiments, and scientific comparisons may use STEM EXPLANATION.
- HARD BAN: runnable code / scripts / library demos are never valid STEM \
depth_gates on this run. Downstream STEM sections have no code_blocks field.
- After the code ban: prefer STEM EXPLANATION (named algorithm / protocol / \
experiment / thought experiment + causal reasoning) over inventing a numeric \
APPLICATION gate. Use STEM APPLICATION only when notes supply a named equation \
and named quantities/values to substitute. Never invent A1/A2 merely because \
code is forbidden.
- DERIVATION VIABILITY: keep a derivation only when requirement and depth_gate \
share the same concrete note-backed start and the same final result, and notes \
support a real multi-step formula_block chain. Vague starts ("principles of…", \
"wave-particle duality" as a theme) or start≠end mismatches → rewrite to \
APPLICATION or EXPLANATION.

MODE DECISION (per item; stop at first match)
1. Pedagogical point IS building a result from a note-backed primitive law / \
definition / axiom, with enough support for a real multi-step chain → STEM \
DERIVATION (exceptional; ≤ 2 in the whole plan).
2. Correctness rests on applying a note-backed equation, law, stoichiometry, \
count, or empirical relation → STEM APPLICATION (default).
3. Correctness rests on a named mechanism, stage sequence, experiment, \
algorithm-as-concept, protocol, thought experiment, or scientific comparison \
without a numerical result → STEM EXPLANATION.
4. NEVER choose Programming implementation on a STEM-domain plan — even if \
notes show source code, an algorithm name, a simulator, or the instruction \
mentions "implement." Prefer STEM EXPLANATION for algorithms/protocols/\
experiments; use STEM APPLICATION only with a note-backed equation + quantities. \
If the mentor truly needed code as mastery evidence, the domain would be \
Programming or Mixed; it is STEM here.

STEM DERIVATION (exceptional)
Slot labels are planning cues only — never copy brackets or angle-slot names \
into JSON. Fill every kept slot with exact note literals.
requirement: Derive/Prove/Show <NOTE_TARGET> starting from <NOTE_PRIMITIVE>, \
showing the genuine transformations through <NOTE_FINAL_RESULT>.
depth_gate: Begins from <EXACT_STARTING_ARTIFACT>; shows at least \
<HONEST_STEP_COUNT> sequential formula_block transformations (≥ 4 only when \
genuine); defines all symbols/units on first use; reaches and states \
<EXACT_FINAL_RESULT>.
Never require a diagram/figure as the only evidence. Never invent fake steps. \
Never put a derivation in every section.

STEM APPLICATION (default)
Slot labels are planning cues only — never leave them (or their English \
paraphrases) in output.
requirement: Calculate/Apply/Determine/Solve for <TARGET> using \
<EXACT_NOTE_EQUATION_OR_RELATION>, substituting <NAMED_QUANTITIES_OR_NOTE_VALUES>, \
and explain what the result means.
depth_gate: States <EXACT_NOTE_EQUATION_OR_RELATION>; substitutes \
<NAMED_QUANTITIES_OR_NOTE_VALUES>; reaches <NOTE_SUPPORTED_OR_COMPUTABLE_RESULT>; \
explains the result in <SPECIFIC_SCIENTIFIC_CONTEXT>.
Fill from notes. If notes have symbols but no literals, use symbolic \
substitution or a standard classroom instance of THAT named relation. Never \
invent a measurement framework, parameter class, kinetics model, or claimed \
answer.
FORBIDDEN OUTPUT PHRASES (instant rewrite): "specific values", "given values", \
"relevant formula", "appropriate equation", "the sine formula", "the applicable \
formula" without writing the actual formula text from notes.

STEM EXPLANATION
requirement: Explain how <NOTE_MECHANISM_OR_EXPERIMENT> demonstrates/produces \
<CONCEPT>, including <CONCRETE_CAUSAL_SEQUENCE>.
depth_gate: Defines <CONCEPT>; presents <NAMED_NOTE_ARTIFACT>; traces \
<CONCRETE_STAGES_OR_EVIDENCE>; explains why that evidence supports \
<SPECIFIC_CONCLUSION_OR_LIMITATION>.

CONCEPT-SCOPED NOTE BINDING (STEM)
- Internally index equations, reactions, counts, variables, units, mechanisms, \
and experiments from notes by concept — do not output the index.
- Bind only an artifact that teaches THIS item's concept/heading. A prominent \
global equation elsewhere in the notes is not valid evidence for a local \
mechanism (e.g. overall photosynthesis ≠ Calvin-stage stoichiometry).
- Prefer: same-concept note artifact → clear equivalent → same-section sibling \
→ instruction-backed → else demote/drop.
- Requirement and depth_gate must demand the same artifact.

ITEM PASS (STEM)
For each draft must_cover item: KEEP only if every named particular is \
supported and the mode is valid; else REWRITE (same id/section when viable) to \
the strongest same-concept note artifact; else DEMOTE; else DROP.
REWRITE is mandatory for unsupported equations/scenarios, wrong mode \
(especially accidental code or unnecessary derivation), vague brackets, or \
unsupported claimed results.

TOPIC_SPLIT (STEM)
Rewrite headings/purposes when generic or note-conflicting. Do not force one \
derivation or one equation per section. Order foundations → mechanism → \
application/evidence → limitations when the draft order is unusable.

PROHIBITIONS
- No API / runnable code / function-call / script / notebook gates — ever, on \
a STEM-domain plan (mode 4 never authorizes code here).
- No derivation language unless mode 1 passed.
- No invented values, units, rates, or frameworks.
- No square-bracket placeholders left in output."""

_PROGRAMMING_POLICY_BLOCK = """\
DOMAIN POLICY — PROGRAMMING (this run is Programming; do not invent STEM \
derivation defaults)

SAFE DEFAULTS
- Default for code-mastery concepts is PROGRAMMING IMPLEMENTATION.
- Rigor = correct executable behaviour + explanation, not algebraic derivation.
- Never require formula_blocks for ordinary code execution, state tracing, \
control flow, API usage, lifecycle, or debugging.
- Words like calculate, trace, step-by-step, state, rule, proof do NOT convert \
Programming into STEM.
- Do not import every API from the notes — smallest set that covers the topic.

MODE DECISION (per item; stop at first match)
1. Mastery requires source code whose runtime behaviour / output / state / \
side effect / error can be examined → PROGRAMMING IMPLEMENTATION (default).
2. Concept is architectural/behavioural with a checkable runtime causal \
sequence, and new code is not the primary evidence → PROGRAMMING BEHAVIOURAL \
EXPLANATION.
3. Exact item rests on a note-backed formal math artifact (e.g. deriving a \
complexity bound from a recurrence) → STEM derivation/application allowed for \
THAT sub-concept only.
4. Exact item is a named historical/standards case from notes → Conceptual case \
allowed for THAT item only.

PROGRAMMING IMPLEMENTATION (default)
Slot labels below are planning cues only — NEVER copy them into JSON.
Finished requirement/depth_gate must contain concrete note-backed literals \
(API names, function/component names, exact behaviours, concrete cases).

Shape (fill every slot from notes; omit a slot only by DEMOTE/DROP):
requirement: Implement/Build/Write/Debug <NOTE_CODE_ARTIFACT> that \
<CONCRETE_BEHAVIOUR>, and explain what the code outputs/returns/changes and \
why, including <CONCRETE_NORMAL_CASE> and <CONCRETE_EDGE_OR_CLEANUP_CASE>.
depth_gate: Contains at least one self-contained, runnable <LANGUAGE> code \
block using <EXACT_NOTE_API_OR_SIGNATURE> to demonstrate <CONCRETE_BEHAVIOUR>; \
explanation states <CONCRETE_OUTPUT_OR_STATE> and why; execution is shown for \
<CONCRETE_NORMAL_CASE> and <CONCRETE_EDGE_OR_CLEANUP_CASE>.
Evidence is one inline code block — never a multi-file repo.

FORBIDDEN OUTPUT PHRASES (instant rewrite/drop if they appear):
"normal-case scenario", "edge-case scenario", "named scenario or edge case", \
"a normal-case scenario", "an edge-case scenario", "an edge case", \
"a normal case", "an API", "a code example", "demonstrating the concept".
Do not use "edge case" / "normal case" as the entire case description — replace \
with the concrete input/output from notes.
Cases must be specific (e.g. "count starts at 0 then Increment raises it to 1"; \
"effect cleanup restores document.title to React App"; "ThemeContext value is \
light").

GOOD (literals filled): "Implement a counter with useState(0) and Increment/ \
Decrement buttons from the notes; explain count updates; show increment from 0 \
to 1 and rapid double-click still yielding a single coherent count."
BAD (placeholder leak — never emit): "...including a normal-case scenario and \
an edge-case scenario." / "...demonstrating the useState Hook..."

ARTIFACT CONFLICT RULE (critical — apply to EVERY draft item)
If draft names an API, signature, demo, or scenario absent from notes:
1. Same-concept note sibling exists → KEEP id/section when viable; REWRITE \
requirement AND depth_gate to that sibling (both fields must agree).
2. No same-concept sibling → DEMOTE to recommended behavioural explanation only \
if notes support a causal story; else DROP. Never invent a substitute demo.
3. Teaching instruction may keep a concept label (e.g. TypeScript) without a \
note demo — then the gate must stay no more specific than the instruction; do \
not fabricate APIs, memoization, lazy loading, database fetch, or form \
validation the notes do not show.

Widen the rewrite beyond one hook family — same rule for:
- effects / data loading (draft fetch/API → notes document.title / cleanup)
- custom hooks (draft "form validation" / generic custom hook → notes' named \
custom hook such as useDouble)
- context (draft generic context → notes' ThemeContext / MyContext demo)
- state demos (draft abstract state app → notes' counter / named component)
- optimization (draft memoization / lazy loading / React.memo with no note \
demo → DROP or rewrite only to a note-backed performance artifact; do not keep \
unsupported optimization gates)
- server/async UI (draft "fetch from database" → only what notes actually show \
for server/async components; else demote/drop)

Examples:
- draft useEffect + fetch API, notes teach document.title / cleanup → bind \
title/cleanup, drop fetch.
- draft custom Hook "form validation", notes teach useDouble(count) → bind \
useDouble, drop form validation.
- draft memoization + lazy loading, notes lack both → drop or demote; do not \
preserve the unsupported optimization requirement.

PROGRAMMING BEHAVIOURAL EXPLANATION
Fill with concrete note names — no slot-label prose in output.
requirement: Explain how <NOTE_MECHANISM> produces/enforces <BEHAVIOUR>, \
tracing <CONCRETE_RUNTIME_SEQUENCE> and including <NAMED_FAILURE_OR_INVARIANT>.
depth_gate: Defines <NOTE_MECHANISM>; traces <CONCRETE_RUNTIME_SEQUENCE>; \
identifies <NAMED_FAILURE_OR_INVARIANT>; explains why <BEHAVIOUR> follows.

CONCEPT-SCOPED NOTE BINDING (PROGRAMMING)
- Internally index languages, APIs, signatures, hooks, components, code \
examples, runtime outcomes, and edge/cleanup behaviour by concept.
- Bind only same-concept note artifacts. Do not attach one API's scenario to a \
different API merely because both are in the same framework.
- Prefer note-backed sibling over unsupported draft wording (Artifact Conflict \
Rule).
- Requirement and depth_gate must name the same artifact and the same two \
concrete cases.

ITEM PASS (PROGRAMMING)
KEEP only if named APIs/scenarios are note- or instruction-supported and mode \
is valid; else REWRITE to strongest same-concept note artifact; else DEMOTE; \
else DROP. Apply Artifact Conflict Rule before KEEP. Any forbidden output \
phrase, square-bracket slot label, or unnamed case → mandatory REWRITE or DROP.

TOPIC_SPLIT (PROGRAMMING)
Prefer concrete headings (e.g. "useState Hook" not "Core Concepts"). Do not \
force code into a purely historical/architectural section unless code is the \
evidence. Do not force a derivation section. Do not keep an optimization or \
advanced-API section whose only checklist item would be unsupported by notes.

PROHIBITIONS
- No algebraic derivation / formula_block gates for hooks, lifecycle, state, \
API usage, or execution tracing.
- No fabricated API, language, signature, scenario, memoization, lazy loading, \
database fetch, or form-validation demo absent from notes (and not explicitly \
specified by teaching_instruction).
- No generic "runnable code block demonstrating the concept".
- No square-bracket placeholders or forbidden output phrases left in output."""

_CONCEPTUAL_POLICY_BLOCK = """\
DOMAIN POLICY — CONCEPTUAL (this run is Conceptual; do not invent code or \
derivation defaults)

SAFE DEFAULTS
- Default is CONCEPTUAL CASE/ARGUMENT.
- Rigor = named evidence + checkable reasoning chain.
- Do not create Programming work because notes say process, system, framework, \
implementation, method, model, strategy, or procedure.
- Do not create mathematical derivation because a theory has premises, steps, \
or logical structure.
- Quantitative evidence only when THIS concept depends on a note-backed metric, \
dataset, formula, or computed relationship.

MODE DECISION (per item; stop at first match)
1. Correctness rests on a named case/event/ruling/text/author/organisation/ \
theory/decision and the reasoning connecting it to the concept → CASE/ARGUMENT \
(default).
2. Concept requires comparing two or more named frameworks/actors/periods/ \
strategies/outcomes → COMPARISON.
3. Correctness depends on a note-backed quantitative model/metric/formula → \
STEM APPLICATION allowed for THAT sub-concept only.
4. Instruction explicitly requests software, OR notes contain source code whose \
behaviour is central to THIS item → Programming implementation allowed for \
THAT item only. Otherwise code is forbidden.

CONCEPTUAL CASE/ARGUMENT (default)
Slot labels are planning cues only — never copy them into JSON.
requirement: Explain how <NAMED_NOTE_CASE> demonstrates <CONCEPT>, including \
<CONCRETE_REASONING_CHAIN>.
depth_gate: Defines <CONCEPT>; accurately presents <NAMED_NOTE_CASE>; identifies \
<SPECIFIC_FACTS_OR_CLAIMS>; explains the reasoning connecting them to \
<SPECIFIC_CONCLUSION>.

CONCEPTUAL COMPARISON
requirement: Compare <NOTE_ARTIFACT_A> and <NOTE_ARTIFACT_B> with respect to \
<NOTE_DIMENSIONS>, explaining why <SPECIFIC_DIFF_OR_SIMILARITY> leads to \
<SPECIFIC_CONSEQUENCE>.
depth_gate: Accurately presents <NOTE_ARTIFACT_A> and <NOTE_ARTIFACT_B>; compares \
them on <NOTE_DIMENSIONS>; identifies <SPECIFIC_DIFF_OR_SIMILARITY>; explains \
its effect on <NAMED_OUTCOME>.

CONCEPT-SCOPED NOTE BINDING (CONCEPTUAL)
- Internally index named cases, events, rulings, people, texts, organisations, \
theories, strategies, and documented outcomes by concept.
- Bind only artifacts that teach THIS item's concept. Do not attach one case to \
a different theory merely because both appear in the same chapter.
- Prefer named note cases over unnamed "real-world example".
- Requirement and depth_gate must demand the same named artifact(s).

ITEM PASS (CONCEPTUAL)
KEEP only if named particulars are supported and mode is valid; else REWRITE to \
strongest same-concept note artifact; else DEMOTE; else DROP. Vague "a named \
case" / "explain clearly" / "discuss in detail" must be rewritten or dropped.

TOPIC_SPLIT (CONCEPTUAL)
Prefer specific case/theme headings. Do not force a calculation or code example \
into every section. Order foundations → key cases/arguments → comparison/ \
synthesis when draft order is unusable.

PROHIBITIONS
- No runnable code / API / function-call gates unless mode 4 passed.
- No derivation / formula_block / numerical-substitution gates unless mode 3 \
passed.
- No invented dates, rulings, quotations, statistics, organisations, or causal \
claims.
- No generic "the concept is clearly explained" gates.
- No square-bracket placeholders left in output."""

_MIXED_POLICY_BLOCK = """\
DOMAIN POLICY — MIXED (this run is Mixed; route each item locally — do not \
artificially balance families)

ROUTING
For each checklist item, choose LOCAL evidence mode from what THAT concept is:
- scientific / mathematical / empirical → STEM APPLICATION (default), STEM \
EXPLANATION, or exceptional STEM DERIVATION (≤ 2 in the whole plan);
- source-code / runtime / API behaviour → PROGRAMMING IMPLEMENTATION or \
BEHAVIOURAL EXPLANATION;
- named case / event / text / organisation / argument → CONCEPTUAL CASE or \
COMPARISON.
Do not route from surface verbs (model, system, process, algorithm, framework, \
implementation, analysis).

SAFE DEFAULTS
- Do not require each section to mix modes. One dominant local mode per section \
is normal.
- Uneven family counts are fine if that is what notes support.
- Create a cross-domain item only when the learning objective truly needs both \
artifacts; otherwise split into two items under the same section.
- Programming remains exceptional for scientific/conceptual sections unless \
source code + runtime are central.
- Equations remain exceptional for programming/conceptual sections unless the \
exact item depends on them.
- Zero derivations is normal; never derive every section.

STEM APPLICATION (when local mode is quantitative)
requirement / depth_gate must name the exact note-backed equation/relation and \
named quantities/symbols/values. Ban "specific values" / invented measurement \
frameworks. Bind concept-locally (no wrong global equation).

STEM DERIVATION (exceptional; ≤ 2 total)
Only when the pedagogical point IS the from-scratch build and notes support a \
real formula_block chain. Never require diagrams as sole evidence.

PROGRAMMING IMPLEMENTATION (when local mode is code)
Bind exact note-backed API/signature; name two concrete cases (never the \
phrases "normal-case scenario" / "edge-case scenario"); one inline runnable \
block. Apply the Programming Artifact Conflict Rule: rewrite draft API/scenario \
to same-concept note siblings (custom hooks, effects, context, optimization, \
server/async); if no sibling, demote/drop — do not invent memo/lazy/fetch/form \
demos.

CONCEPTUAL CASE/COMPARISON (when local mode is interpretive)
Bind named note-backed cases/events/texts; demand the reasoning chain. No \
unnamed "real-world example" when notes have a named artifact.

CONCEPT-SCOPED NOTE BINDING (MIXED)
Internally index artifacts by concept across equations, APIs, and named cases. \
An artifact may support an item only when it teaches that item's concept. \
Requirement and depth_gate must agree.

ITEM PASS (MIXED)
KEEP / REWRITE / DEMOTE / DROP as for other domains, using the local mode \
decision. Rewrite unsupported draft particulars to same-concept note siblings. \
Never invent code for STEM-local items or derivations for Programming-local \
items.

TOPIC_SPLIT (MIXED)
Preserve coherent syllabus order. Do not force one equation + one code sample + \
one case into every section.

CROSS-DOMAIN ITEM (rare)
Slot labels are planning cues only — fill with concrete literals.
requirement: Use <MODE1_ARTIFACT> together with <MODE2_ARTIFACT> to \
explain/determine <INTEGRATED_TARGET>, distinguishing what each contributes.
depth_gate: Presents and verifies <MODE1_ARTIFACT>; presents and verifies \
<MODE2_ARTIFACT>; explains their connection and reaches <INTEGRATED_CONCLUSION>.
If both cannot be evidenced in one section, split into two checklist items.

PROHIBITIONS
- No artificial family balancing.
- No code/derivation/calculation outside the local-mode rules above.
- No vague fillers or square-bracket placeholders."""

_STEM_VALIDATION_BLOCK = """\
SELF-CHECK BEFORE OUTPUT (STEM)
□ Domain equals <draft_plan>.domain exactly?
□ Zero code / API / runnable / script gates — STEM hard ban, no instruction or \
notes exception?
□ Derivation count ≤ 2, and zero is acceptable? No derivation-per-section?
□ Every derivation shares the same concrete start/end in requirement and \
depth_gate, with a real note-backed multi-step chain (no vague "principles of…" \
starts)?
□ Algorithm / protocol / experiment items use STEM EXPLANATION rather than \
invented numeric APPLICATION gates when notes lack a substitutable equation?
□ Every required item binds a concept-local note equation/relation/mechanism \
(not a flashy unrelated equation elsewhere)?
□ Every quantitative gate quotes the actual note formula/relation text — no \
"specific values" / "the sine formula" / "relevant formula"?
□ No invented measurement frameworks / unsupported results / leftover slot \
labels?
□ Preservation budget and +1 section / +2 items respected?
□ STRUCTURAL INTEGRITY: every section_id resolves; every topic_split owns ≥ 1 \
item?
Do not output until every check passes."""

_PROGRAMMING_VALIDATION_BLOCK = """\
SELF-CHECK BEFORE OUTPUT (PROGRAMMING)
□ Domain equals <draft_plan>.domain exactly?
□ No accidental algebraic derivation / formula_block gates for ordinary code \
behaviour?
□ Every required implementation gate names a note-backed API/signature, a \
concrete behaviour, and two concrete cases (not the forbidden phrases \
"normal-case scenario" / "edge-case scenario" / "named scenario")?
□ Artifact Conflict Rule applied to every item — including custom hooks, \
effects, context, optimization, and server/async demos?
□ Unsupported memoization / lazy loading / database-fetch / form-validation \
gates dropped or rewritten to note siblings?
□ No fabricated APIs/scenarios; no square-bracket or angle-slot labels left?
□ Preservation budget and +1 section / +2 items respected?
□ STRUCTURAL INTEGRITY: every section_id resolves; every topic_split owns ≥ 1 \
item?
Do not output until every check passes."""

_CONCEPTUAL_VALIDATION_BLOCK = """\
SELF-CHECK BEFORE OUTPUT (CONCEPTUAL)
□ Domain equals <draft_plan>.domain exactly?
□ No accidental code or derivation/calculation gates (unless the exact item \
exception rules passed)?
□ Every required item binds a named note-backed case/event/text/organisation/ \
theory?
□ No unnamed "real-world example" when notes supply a named artifact?
□ No invented dates/rulings/statistics/causal claims; no generic "clearly \
explained" gates?
□ Preservation budget and +1 section / +2 items respected?
□ STRUCTURAL INTEGRITY: every section_id resolves; every topic_split owns ≥ 1 \
item?
□ No unfilled bracket placeholders?
Do not output until every check passes."""

_MIXED_VALIDATION_BLOCK = """\
SELF-CHECK BEFORE OUTPUT (MIXED)
□ Domain equals <draft_plan>.domain exactly?
□ Each item routed locally (STEM / Programming / Conceptual) — not artificially \
balanced?
□ No code on STEM-local items; no derivation on Programming-local items; no \
forced equation on Conceptual-local items?
□ Derivation count ≤ 2 across the whole plan (zero OK)?
□ Every required item binds a concept-local note artifact; requirement and \
depth_gate agree?
□ Preservation budget and +1 section / +2 items respected?
□ STRUCTURAL INTEGRITY: every section_id resolves; every topic_split owns ≥ 1 \
item?
□ No unfilled bracket placeholders?
Do not output until every check passes."""

_USER_CLOSING_BY_DOMAIN: dict[str, str] = {
    "STEM": (
        "\nRealign the JSON plan now for this STEM topic. "
        "Preserve domain from <draft_plan>. "
        "Default to note-backed applications and explanations — not derivation "
        "in every section, and not code. "
        "Bind each required gate to a concept-local note equation, relation, "
        "mechanism, or experiment — quote the actual formula text from notes. "
        "Rewrite unsupported draft debt; never invent measurement frameworks "
        "or emit vague fillers like 'specific values' / 'the sine formula'. "
        "Do not import every note topic."
    ),
    "Programming": (
        "\nRealign the JSON plan now for this Programming topic. "
        "Preserve domain from <draft_plan>. "
        "Default to note-backed implementation gates with exact APIs and "
        "two concrete cases — never emit 'normal-case scenario' / "
        "'edge-case scenario' placeholder phrasing, and never leave slot "
        "labels in the JSON. "
        "Apply the Artifact Conflict Rule to every item: rewrite draft "
        "APIs/scenarios (including custom hooks, effects, context, "
        "optimization, server/async) to same-concept note demos; drop "
        "unsupported memoization/lazy-loading/database-fetch/form-validation "
        "gates when notes lack them. "
        "Do not import every note API."
    ),
    "Conceptual": (
        "\nRealign the JSON plan now for this Conceptual topic. "
        "Preserve domain from <draft_plan>. "
        "Default to named note-backed cases and reasoning chains — not code "
        "and not derivation. "
        "Rewrite vague examples to concrete note artifacts. "
        "Do not invent cases, dates, or causal claims."
    ),
    "Mixed": (
        "\nRealign the JSON plan now for this Mixed topic. "
        "Preserve domain from <draft_plan>. "
        "Route each checklist item locally to STEM, Programming, or Conceptual "
        "evidence — do not force every section to mix modes or balance families. "
        "Bind concept-local note artifacts; rewrite unsupported draft debt. "
        "Do not invent code for scientific items or derivations for code items."
    ),
}


def _normalize_domain(domain: str | None) -> str:
    """Return a canonical domain label; unknown/empty falls back to Mixed."""
    cleaned = (domain or "").strip()
    if cleaned in _VALID_DOMAINS:
        return cleaned
    # Tolerate common casing drift from state.
    titled = cleaned[:1].upper() + cleaned[1:] if cleaned else ""
    for valid in _VALID_DOMAINS:
        if cleaned.lower() == valid.lower() or titled == valid:
            return valid
    return "Mixed"


def _domain_policy_block(domain: str) -> str:
    return {
        "STEM": _STEM_POLICY_BLOCK,
        "Programming": _PROGRAMMING_POLICY_BLOCK,
        "Conceptual": _CONCEPTUAL_POLICY_BLOCK,
        "Mixed": _MIXED_POLICY_BLOCK,
    }[domain]


def _domain_validation_block(domain: str) -> str:
    return {
        "STEM": _STEM_VALIDATION_BLOCK,
        "Programming": _PROGRAMMING_VALIDATION_BLOCK,
        "Conceptual": _CONCEPTUAL_VALIDATION_BLOCK,
        "Mixed": _MIXED_VALIDATION_BLOCK,
    }[domain]


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


def build_checklist_realign_system_prompt(*, domain: str | None = None) -> str:
    """System prompt for post-research checklist realignment against GT notes.

    ``domain`` must be the fixed draft/graph-state domain. Only that domain's
    policy and validation blocks are included.
    """
    resolved = _normalize_domain(domain)
    return f"""\
{_REALIGN_ROLE_BLOCK}

STEP 1 — DOMAIN
{DOMAIN_REUSE_FROM_DRAFT_PLAN_BLOCK}

STEP 2 — REALIGN UNDER THE FIXED DOMAIN POLICY
{_PRESERVATION_BUDGET_BLOCK}

{_domain_policy_block(resolved)}

STEP 3 — topic_split
{_TOPIC_SPLIT_REALIGN_SIZING_BLOCK}
{TOPIC_SPLIT_STYLE_BLOCK}

STEP 4 — must_cover_checklist fields
{_CHECKLIST_ITEM_FIELDS_BLOCK}

{STRUCTURAL_INTEGRITY_BLOCK}

STEP 5 — SELF-CHECK BEFORE WRITING OUTPUT
{_domain_validation_block(resolved)}

{JSON_OUTPUT_SCHEMA}"""


def build_checklist_realign_user_message(
    topic_title: str,
    *,
    teaching_instruction: str = "",
    draft_plan: dict[str, Any],
    research_notes: str,
    domain: str | None = None,
) -> str:
    """User message: topic, instruction, draft plan JSON, truncated research notes.

    ``domain`` defaults to ``draft_plan["domain"]`` when omitted.
    """
    resolved = _normalize_domain(
        domain if domain is not None else draft_plan.get("domain")
    )
    parts: list[str] = [
        f"<topic>{topic_title}</topic>",
        f"\n<domain>{resolved}</domain>",
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
    parts.append(_USER_CLOSING_BY_DOMAIN[resolved])

    return "\n".join(parts)
