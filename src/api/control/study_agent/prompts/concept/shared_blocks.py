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
Every must_cover_checklist item belongs to exactly ONE of the three evidence families below. Pick the family for each item individually based on what that specific item is actually about. For each family, copy its depth_gate skeleton and fill in only the bracketed parts — do not invent a new sentence structure, and do not blend wording from a different family's skeleton.

FAMILY A — MATHEMATICAL
Use only when the item's own correctness rests on an equation, proof, or empirical/physical fact (this is the STEM standard).
requirement skeleton:
  "<Derive/Prove/Calculate/Show that> <target>, starting from <named equation or law>, showing <the required steps> until <the final result>."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "Derivation begins from [named starting equation or law]; each algebraic or logical step is shown explicitly in formula notation; all variables defined with units; correct final result [state the result] reached and stated."
Worked example:
  requirement:  "Derive the time complexity of merge sort step-by-step from the recurrence relation T(n) = 2T(n/2) + n, showing each substitution until the closed form is reached."
  depth_gate:   "Derivation begins from the recurrence relation T(n) = 2T(n/2) + n; each algebraic step is shown explicitly via substitution; all variables defined; correct closed-form result O(n log n) reached and stated."

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
These words belong ONLY to Family A. If the item you are writing is Family B or Family C, none of these words may appear anywhere in its requirement or its depth_gate, no matter how naturally they seem to fit the topic:
  derive, derivation, derived, prove, proof, theorem, algebraic, formula notation, closed form, recurrence relation.
If you catch one of these words in a Family B or C item, delete the sentence and rewrite it from that family's skeleton above. There is no topic for which a Family B or C item is allowed to use Family A's vocabulary.
These words belong ONLY to Family B. They must not appear in a Family A or Family C item's requirement or depth_gate:
  code block, runnable, function call, API.
(Exception: if the teaching instruction explicitly asks for a supporting code example inside a STEM or Conceptual section, that code is additive to — never a substitute for — that item's own Family A or Family C evidence.)"""

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
