"""Shared building blocks for the concept_checklist (curriculum architect) prompts."""

from __future__ import annotations

DOMAIN_CLASSIFICATION_BLOCK = """\
Classify the topic into exactly one of:
  STEM         — mathematics, physics, chemistry, biology, engineering, statistics; correctness depends on equations, derivations, proofs, or empirical facts.
  Programming  — code, algorithms, data structures, APIs, frameworks, protocols; correctness depends on syntax and runtime behaviour.
  Conceptual   — history, philosophy, law, ethics, social sciences, literature, business/management; correctness depends on named facts and logical reasoning.
  Mixed        — the topic spans more than one of the above.
Output exactly one word for the "domain" field: STEM, Programming, Conceptual, or Mixed. Never copy the option template string as-is.
Classify by what the topic itself fundamentally IS, not by how rigorous its explanation needs to be. A programming topic (an API, a hook, a data structure, a protocol) stays Programming even when explaining it well requires careful reasoning about state, control flow, or timing — that is still "syntax and runtime behaviour," never a mathematical derivation. Reserve STEM for topics whose correctness genuinely rests on an equation, proof, or physical/empirical fact.
If the topic is Mixed, this top-level label is only used for routing later pipeline steps. Every individual checklist item still gets its OWN evidence family decided independently — see the must_cover_checklist rules below. Decide each item's family from what that specific item is about, never from the document's overall label."""

EVIDENCE_FAMILY_BLOCK = """\
Every must_cover_checklist item belongs to exactly ONE of the three evidence families below. Decide the family for each item individually, based on what that specific item is actually about — never from the document's overall "domain" label, and never from surface vocabulary in the topic, teaching_instruction, or your own draft wording. Words like "implement," "apply," "method," "technique," "process," "procedure," or "system" occur naturally in STEM and Conceptual writing and do NOT, by themselves, indicate Family B.

FAMILY DECISION TEST — before drafting each item, run these checks in order and stop at the first one that matches:
1. CODE TEST: Would correctly satisfying this item require producing source code that runs in a programming language (a function, script, API call, data structure, or algorithm implementation), where the actual evidence of mastery is the code itself plus its runtime behaviour?
   - YES -> FAMILY B.
   - NO -> continue. A mathematical technique (a solving method, a multi-step algebraic or numeric procedure), a chemical or physical mechanism, or any pencil-and-paper or laboratory procedure is NOT code merely because it proceeds in steps. Having ordered steps is necessary but nowhere near sufficient for Family B — code is the specific, narrow case where those steps are written as an executable program.
2. EQUATION/EMPIRICAL TEST: Does this item's own correctness rest on an equation, a derivation or proof, or a quantitative/empirical/physical fact (a formula, a reaction mechanism, a measured or computed result)?
   - YES -> FAMILY A. Continue to the A1/A2 DEPTH TEST below before drafting.
   - NO -> continue.
3. NAMED-CASE TEST: Does this item's own correctness rest on a named case, ruling, organisation, event, or other real-world particular, explained through prose reasoning?
   - YES -> FAMILY C.

If you are torn between two families for the same item, prefer A or C over B. Family B is the narrowest and most specific of the three families and must never be treated as a default or a fallback. A STEM-domain plan with several Family A items and zero Family B items is the normal, expected shape for a topic with no software component — do not manufacture a Family B item just because the plan's overall domain label is STEM or Mixed. Conversely, a Programming-domain plan can still contain Family A or C items (e.g. a complexity proof, or a named historical protocol decision) when that specific item's own correctness doesn't hinge on runnable code.

A1/A2 DEPTH TEST — every item that reaches FAMILY A by the test above still splits into exactly one of two depth modes. This decision is NOT optional and is NOT a stylistic preference — it is the single most commonly mis-applied step in this prompt, so run it explicitly, every time, for every Family A item:
   - A1 (ground-up derivation) applies ONLY when the section's whole pedagogical point is watching a result get built from a more primitive definition or law — i.e. the concept IS the derivation, not a fact that merely happens to have a derivation behind it. This is rare: most documents have zero or one moment like this, occasionally two when the document covers two genuinely separate foundational pillars (e.g. differentiation and integration both built from their own limit definitions in the same calculus document).
   - A2 (applied/worked use) is the default for every other Family A item — including the large majority of equation- or fact-grounded concepts: applying an already-established formula, rule, or law to a concrete case; reading a value off a model or mechanism; computing a result from given data. A2 is just as rigorous and falsifiable as A1 — it is not a downgrade to vague prose — it simply does not re-derive the underlying equation from first principles.
   - Default to A2. Only choose A1 if you can name, in one sentence, why a learner seeing the from-scratch build-up (rather than a correct worked application) is the actual point of that specific section. If you can't name that reason in one sentence, it's A2.
   - Hard ceiling: across the ENTIRE must_cover_checklist you output, at most 2 items total may be A1. This ceiling is a property of the whole document, not of any one section. If you find yourself wanting a 3rd A1 item, every concept past the first one or two foundational build-ups is, by definition, an application of an already-established result — write it as A2.

For each family/mode, copy its requirement and depth_gate skeleton and fill in only the bracketed parts — do not invent a new sentence structure, and do not blend wording from a different family's or mode's skeleton.

FAMILY A1 — MATHEMATICAL DERIVATION
Use ONLY for the concepts in the entire document where the point is to build a result from first principles.
requirement skeleton:
  "<Derive/Prove/Show that> <target>, starting from <named equation or law>, showing <the required steps> until <the final result>."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "Derivation begins from [named starting equation or law]; each algebraic or logical step is shown explicitly in formula notation; all variables defined with units; correct final result [state the result] reached and stated."
Worked example:
  requirement:  "Derive the time complexity of merge sort step-by-step from the recurrence relation T(n) = 2T(n/2) + n, showing each substitution until the closed form is reached."
  depth_gate:   "Derivation begins from the recurrence relation T(n) = 2T(n/2) + n; each algebraic step is shown explicitly via substitution; all variables defined; correct closed-form result O(n log n) reached and stated."

FAMILY A2 — MATHEMATICAL/EMPIRICAL APPLICATION
Use for every other equation-, formula-, or fact-grounded item: applying a named law, rule, or formula to a specific case, or reading/computing a result from given data. This is the default Family A mode.
requirement skeleton:
  "<Calculate/Apply/Determine/Solve for> <target> using <the named equation, rule, or law>, substituting <the specific values or variables involved>, and explain what the result means."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "States the applicable [named equation, rule, or law]; substitutes the specific [values or variables] used; arrives at the correct result [state the result]; explains what the result means in context."
Worked example:
  requirement:  "Calculate the resonance stabilization energy of benzene using experimental heats of hydrogenation, substituting the measured values for cyclohexene and benzene, and explain what the result indicates about aromatic stability."
  depth_gate:   "States the applicable heats of hydrogenation for cyclohexene and benzene; substitutes the specific measured values; arrives at the correct resonance energy of approximately 36 kcal/mol reached and stated; explains what this value indicates about benzene's stability relative to a hypothetical non-aromatic cyclohexatriene."

FAMILY B — IMPLEMENTATION
Use for code, algorithms, data structures, APIs, frameworks, protocols — anything whose own correctness rests on syntax and runtime behaviour (this is the Programming standard).
requirement skeleton:
  "<Implement/Build/Write/Debug> <artifact> that <behaviour>, and explain what the code does/outputs and why, including <a named scenario or edge case>."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "At least one self-contained, runnable code block demonstrating [the behaviour or concept]; explanation explicitly states what the code outputs or returns and why; behaviour is shown for [a normal-case scenario] and for [an edge-case scenario]."
Worked example:
  requirement:  "Implement a working debounce function in JavaScript with a configurable delay, and explain line-by-line what happens when the returned closure is called before the timer expires."
  depth_gate:   "At least one self-contained, runnable JavaScript code block implementing the debounce function; explanation explicitly states what the function returns and why; behaviour is shown for a call that completes after the delay and for a call that is cancelled by a later call before the delay expires."

FAMILY C — INTERPRETIVE
Use for history, philosophy, law, ethics, social sciences, literature, business/management — anything whose own correctness rests on named facts and reasoning, not equations or code (this is the Conceptual standard).
requirement skeleton:
  "Explain how <a named case, ruling, organisation, or event> demonstrates <the concept>, including <the causal or interpretive reasoning>."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "[The concept] is defined in prose; the specific named case, ruling, organisation, or event — [name it] — is presented; the causal or interpretive reasoning connecting it to [the concept] is explained."
Worked example:
  requirement:  "Explain how the separation of powers doctrine was applied in Marbury v. Madison, including the chain of reasoning that led the court to establish judicial review."
  depth_gate:   "Separation of powers is defined in prose; the specific case Marbury v. Madison (1803) is named and presented; the causal/interpretive reasoning connecting the ruling to the establishment of judicial review is explained."

HARD WORD BAN — apply after drafting, before output
These words belong ONLY to Family A1. If the item you are writing is A2, B, or C, none of these words may appear anywhere in its requirement or its depth_gate, no matter how naturally they seem to fit the topic:
  derive, derivation, derived, prove, proof, theorem, algebraic, formula notation, closed form, recurrence relation.
If you catch one of these words in an A2, B, or C item, delete the sentence and rewrite it from that family/mode's skeleton above. There is no topic for which an A2, B, or C item is allowed to use Family A1's vocabulary.
These words belong ONLY to Family B. They must not appear in an A1, A2, or Family C item's requirement or depth_gate:
  code block, runnable, function call, API.
(Exception: if the teaching instruction explicitly asks for a supporting code example inside a STEM or Conceptual section, that code is additive to — never a substitute for — that item's own A1/A2 or Family C evidence.)

SKELETON COMPLETION CHECK — apply after drafting, before output
- Every bracketed placeholder copied from a skeleton (anything written as [like this]) must be replaced with real, topic-specific content before output. A literal "[" or "]" surviving into a requirement or depth_gate is the same failure as leaving the skeleton template unfilled, even when the family classification itself was correct.
- Re-read each finished requirement and depth_gate as a reviewer who has never seen these skeletons: if a sentence only parses as a fill-in-the-blank form rather than a complete, topic-specific statement, rewrite it before output.
- Count your A1 items across the whole checklist one more time. If the count is 3 or more, this is an automatic failure — pick the weakest-justified one(s) and rewrite as A2 before output."""

CHECKLIST_RULES_BLOCK = """\
- A depth_gate must be a bar that generic or surface-level coverage cannot satisfy. "A clear description is provided" or "examples are given" is never acceptable on its own — the filled skeleton above already enforces this; do not weaken it.
- priority: "required" — absence is a critical failure. "recommended" — absence is a significant gap.
- section_id must name the single topic_split section where a reviewer will find all depth_gate evidence. Never assign a checklist item to an introductory section (typically ts_1) unless that section is where the concept's complete treatment — not just a definition or overview — actually lives.
- Each topic_split section should own at most 2 must_cover items, and every section should own at least 1 — a section with zero checklist items is uncovered, not efficiently scoped. If a concept needs its own depth_gate, give it a dedicated section rather than stacking unrelated requirements.
- Include ONLY the fields id, concept, requirement, priority, section_id, and depth_gate. No motivation, no depth, no coverage_notes, no family/domain label on the item itself.
- Push every filled skeleton toward the richer end of its bracket content rather than the bare minimum — name the specific equation/law, the specific named case, or two genuinely distinct code scenarios. Going deeper never means switching to a different family's skeleton."""

TOPIC_SPLIT_SIZING_BLOCK = """\
- Choose 4–8 sections. Default to the middle-to-upper part of that range (5–6 sections) for any topic that has more than one genuinely distinct sub-concept, mechanism, or use case — this is the common case. Only collapse to 3 sections when the topic is so narrow that a 4th section would just restate an earlier section in different words; 3 is a rare exception, not a safe default. 8 is the maximum, reserved for very broad topics.
- If the teaching_instruction signals breadth, importance, or completeness (e.g. it calls the topic foundational, asks that learners understand "all of it", or asks for thorough coverage), treat that as a direct instruction to use the upper part of the 4–8 range — not the lower part."""

TOPIC_SPLIT_STYLE_BLOCK = """\
- Headings must be specific to this topic. Write "Schrödinger Equation" not "Core Equations". Write "useState Hook" not "Core Concepts".
- purpose: one concrete sentence stating what a learner gains from this section.
- Include ONLY the fields id, heading, and purpose. Nothing else."""

# This is the direct fix for the ts_7 orphan bug seen in RUNS_OUTPUT.
STRUCTURAL_INTEGRITY_BLOCK = """\
STRUCTURAL INTEGRITY — applies to every output, no exceptions, this is checked before anything else
- Every must_cover_checklist item's section_id MUST match the id of a topic_split entry that is present in THIS SAME JSON output. A checklist item pointing at a section_id you did not also output (e.g. an item with section_id "ts_7" when topic_split only goes up to ts_6) is an invalid plan and must never be produced.
- Conversely, every topic_split entry should be the section_id of at least one must_cover_checklist item. A topic_split entry with zero checklist items pointing at it is an uncovered section.
- If you decide a checklist item needs a section_id that does not yet exist, you must add the matching topic_split entry to this same output BEFORE you finish — never invent a new section_id without creating its topic_split counterpart in the same response.
- Before output, walk through every must_cover_checklist item and confirm its section_id resolves to an entry you actually wrote; walk through every topic_split entry and confirm at least one checklist item resolves to it."""

JSON_OUTPUT_SCHEMA = """\
OUTPUT FORMAT — return ONLY this JSON object, nothing else. No preamble, no markdown.
{
  "domain": "STEM|Programming|Conceptual|Mixed",
  "topic_split": [
    {
      "id": "ts_1",
      "heading": "<topic-specific heading>",
      "purpose": "<one concrete sentence>"
    }
  ],
  "must_cover_checklist": [
    {
      "id": "mc_1",
      "concept": "<short concept name>",
      "requirement": "<one measurable topic-specific sentence, built from its evidence family's skeleton>",
      "priority": "required|recommended",
      "section_id": "ts_N",
      "depth_gate": "<filled evidence-family skeleton — the minimum yes/no evidence for a reviewer>"
    }
  ]
}"""
