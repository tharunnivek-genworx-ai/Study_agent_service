"""Shared building blocks for the concept_checklist (curriculum architect) prompts."""

from __future__ import annotations

DOMAIN_REUSE_FROM_PREVIOUS_PLAN_BLOCK = """\
Copy the "domain" field from <previous_plan> verbatim into your output. The topic's domain is fixed for this run — never reclassify it, including during ACTION F (full restructure). Restructuring changes topic_split and must_cover_checklist only."""

REFERENCE_CONTEXT_BLOCK = """\
- These are structured sections extracted from the mentor's reference PDF — treat them as the source of truth for what the study material must cover.
- Align topic_split headings with the major themes and headings in the reference sections.
- Derive must_cover_checklist items from substantive concepts, definitions, diagrams, code examples, and facts found in those sections.
- Every important reference section should map to at least one topic_split entry and/or must_cover_checklist item.
- Do not invent topics absent from the reference unless the teaching_instruction explicitly requires additional content."""

REWORK_PLAN_CONTEXT_BLOCK = """\
<previous_plan> in the user message is the concept plan from the prior run. Use it as the starting point for this revision.
When <mentor_feedback> or <regeneration_goal> is provided, treat it as the mentor's explicit revision request — authoritative over reference-derived defaults for scope, format, and section structure when they conflict.
Output a complete revised JSON plan (domain + topic_split + must_cover_checklist), not a partial delta. Unless ACTION F (full restructure) applies, preserve every untouched topic_split entry and must_cover_checklist item from <previous_plan> verbatim — identical id, heading/concept, requirement, priority, section_id, and depth_gate."""

DOMAIN_CLASSIFICATION_BLOCK = """\
Classify the topic into exactly one of:
  STEM         — mathematics, physics, chemistry, biology, engineering, statistics; correctness depends on equations, derivations, proofs, or empirical facts.
  Programming  — code, algorithms, data structures, APIs, frameworks, protocols; correctness depends on syntax and runtime behaviour.
  Conceptual   — history, philosophy, law, ethics, social sciences, literature, business/management; correctness depends on named facts and logical reasoning.
  Mixed        — the topic spans more than one of the above.
Output exactly one word: STEM, Programming, Conceptual, or Mixed.
Classify by what the topic itself fundamentally IS, not by how rigorous its explanation needs to be. A programming topic stays Programming even when explaining it well requires careful reasoning about state, control flow, or timing — that is still "syntax and runtime behaviour," never a mathematical derivation. Reserve STEM for topics whose correctness genuinely rests on an equation, proof, or physical/empirical fact.
If the topic is Mixed, this top-level label only routes later pipeline steps. Every checklist item still gets its own evidence family decided independently — see below. Decide each item's family from what that item is about, never from the document's overall label.
If mastery of the topic as a whole genuinely requires writing and running source code as the primary evidence, classify Programming (or Mixed when STEM and code are both first-class). Do not classify as STEM and then smuggle Family B code gates into the checklist."""

STEM_NO_RUNNABLE_CODE_BLOCK = """\
HARD RULE — STEM DOMAIN FORBIDS RUNNABLE CODE (applies whenever domain = STEM)
Downstream STEM study-material sections have no code_blocks field, and STEM QC fails any section that contains code. Therefore, when the document-level domain is STEM:
- Family B is forbidden for every must_cover_checklist item — zero exceptions, including "recommended" items and application/outlook sections.
- Never write a requirement or depth_gate that demands a runnable code block, script, notebook, library call (e.g. sympy/numpy/scipy/qiskit), API demo, or "implement an algorithm in code."
- Computational or CS-adjacent applications inside a STEM topic (e.g. numerical methods, simulations, "quantum algorithms," cryptography as physics/math) MUST still never be Family B — ban code, then choose the correct non-code family:
  - Prefer Family C (named algorithm, protocol, experiment, thought experiment, or application case + causal/interpretive reasoning) when the item is about how a system/application works rather than computing a numeric result from a named equation.
  - Use Family A only when that item's own evidence genuinely is a named equation, a real derivation, or a concrete quantitative substitution — never invent A1/A2 merely because Family B is banned.
- Words like implement, algorithm, method, simulation, computation, or "quantum computing" do NOT authorize Family B when domain is STEM; they authorize math/prose evidence only — and for algorithms/protocols/experiments that prose is usually Family C, not a fake numeric A2 gate.
- If the teaching_instruction asks for code examples on an otherwise STEM topic, still emit only Family A/C gates. Do not invent Family B depth_gates — code cannot be the mastery evidence for a STEM-domain plan.
- A STEM plan whose every item is Family A and/or C (with zero Family B) is the required shape, not merely the preferred one.
This rule is keyed only to the domain label STEM — never to a specific topic name."""

EVIDENCE_FAMILY_BLOCK = """\
Every must_cover_checklist item belongs to exactly ONE of the three evidence families below. Decide the family for each item individually, based on what that specific item is actually about — never from surface vocabulary in the topic, teaching_instruction, or your own draft wording. Words like "implement," "apply," "method," "technique," "process," "procedure," or "system" occur naturally in STEM and Conceptual writing and do NOT, by themselves, indicate Family B.

FAMILY DECISION TEST — before drafting each item, run these checks in order and stop at the first one that matches:
0. STEM DOMAIN LOCK (runs first when domain = STEM): If the document-level domain is STEM, skip the CODE TEST entirely for this item. Family B is unavailable. Continue at check 2 (EQUATION/EMPIRICAL) or 3 (NAMED-CASE). Never answer YES to the CODE TEST under a STEM domain.
1. CODE TEST (Programming or Mixed only): Would correctly satisfying this item require producing source code that runs in a programming language (a function, script, API call, data structure, or algorithm implementation), where the actual evidence of mastery is the code itself plus its runtime behaviour?
   - YES -> FAMILY B. (Under Mixed: only for items whose local evidence is genuinely software runtime behaviour — never for STEM-local scientific/math items.)
   - NO -> continue. A mathematical technique (a solving method, a multi-step algebraic or numeric procedure), a chemical or physical mechanism, or any pencil-and-paper or laboratory procedure is NOT code merely because it proceeds in steps. Having ordered steps is necessary but nowhere near sufficient for Family B — code is the specific, narrow case where those steps are written as an executable program.
2. EQUATION/EMPIRICAL TEST: Does this item's own correctness rest on an equation, a derivation or proof, or a quantitative/empirical/physical fact (a formula, a reaction mechanism, a measured or computed result)?
   - YES -> FAMILY A. Continue to the A1/A2 DEPTH TEST below before drafting.
   - NO -> continue.
3. NAMED-CASE TEST: Does this item's own correctness rest on a named case, ruling, organisation, event, or other real-world particular, explained through prose reasoning?
   - YES -> FAMILY C.

If you are torn between two families for the same item, prefer A or C over B. Family B is the narrowest and most specific of the three families and must never be treated as a default or a fallback. When domain is STEM, Family B count must be exactly zero — do not manufacture a code item for applications, algorithms, or "implementations." When domain is Mixed, STEM-local items still follow the STEM no-code rule; only Programming-local items may be Family B. Conversely, a Programming-domain plan can still contain Family A or C items (e.g. a complexity proof, or a named historical protocol decision) when that specific item's own correctness doesn't hinge on runnable code.

STEM APPLICATION / ALGORITHM / EXPERIMENT ROUTING — when domain is STEM (or the item is STEM-local under Mixed), after Family B is ruled out:
- Named algorithms, protocols, experiments, thought experiments, historical demos, and qualitative "how this application works" items → prefer FAMILY C, not Family A.
- "Algorithm," "protocol," "experiment," or "quantum computing / cryptography application" does NOT by itself mean EQUATION/EMPIRICAL → Family A, and does NOT mean A2 "substitute specific values."
- Choose Family A for those topics ONLY when the item's mastery evidence is genuinely a named equation with a concrete substitution, or a real A1-viable derivation. Otherwise write Family C.

A1/A2 DEPTH TEST — every item that reaches FAMILY A by the test above still splits into exactly one of two depth modes. This decision is NOT optional and is NOT a stylistic preference — it is the single most commonly mis-applied step in this prompt, so run it explicitly, every time, for every Family A item:
   - A1 (ground-up derivation) applies ONLY when the section's whole pedagogical point is watching a result get built from a more primitive definition or law — i.e. the concept IS the derivation, not a fact that merely happens to have a derivation behind it. This is rare: most documents have zero or one moment like this, occasionally two when the document covers two genuinely separate foundational pillars (e.g. differentiation and integration both built from their own limit definitions in the same calculus document).
   - A2 (applied/worked use) is the default for every other Family A item — including the large majority of equation- or fact-grounded concepts: applying an already-established formula, rule, or law to a concrete case; reading a value off a model or mechanism; computing a result from given data. A2 is just as rigorous and falsifiable as A1 — it is not a downgrade to vague prose — it simply does not re-derive the underlying equation from first principles.
   - Default to A2. Only choose A1 if you can name, in one sentence, why a learner seeing the from-scratch build-up (rather than a correct worked application) is the actual point of that specific section. If you can't name that reason in one sentence, it's A2.
   - Hard ceiling: across the ENTIRE must_cover_checklist you output, at most 2 items total may be A1. This ceiling is a property of the whole document, not of any one section. If you find yourself wanting a 3rd A1 item, every concept past the first one or two foundational build-ups is, by definition, an application of an already-established result — write it as A2.

A1 VIABILITY GATE — HARD RULE before drafting any A1 requirement/depth_gate (same weight as the STEM no-code ban; failing this gate means you must NOT emit A1):
1. Name the exact starting equation, law, definition, or construction in concrete form (not a vague theme such as "principles of…", "wave-particle duality", "basic postulates", or "fundamental ideas" unless that name itself IS a specific equation or formal definition you will write out).
2. Name the exact final result that the derivation reaches.
3. Confirm the requirement and the depth_gate name the SAME starting artifact and the SAME final result — a mismatch (e.g. requirement starts from "wave-particle duality" while depth_gate starts from "the wave function equation") is an automatic failure; rewrite as A2 or Family C, or align both fields to one real start→end pair.
4. Confirm you can list, in your head, at least 4 sequential mechanical transformations from that start to that end, each of which could become its own formula_block. If you cannot, A1 is not viable — use A2 (if a named equation + concrete quantities exist) or Family C (if the point is interpretive/case-based). Do not invent fake intermediate steps to hit the count.
If any of 1–4 fails, do not write an A1 item for that concept.

For each family/mode, copy its requirement and depth_gate skeleton and fill in only the bracketed parts — do not invent a new sentence structure, and do not blend wording from a different family's or mode's skeleton.

FAMILY A1 — MATHEMATICAL / LOGICAL DERIVATION
Use ONLY for the concepts in the entire document where the point is to build a result from first principles —
whether the starting point is a named equation or law (algebraic derivation) or a foundational definition,
axiom, or construction (geometric, logical, or limit-based derivation).
Pass the A1 VIABILITY GATE above before using this skeleton. If the gate fails, do not use Family A1.
requirement skeleton:
  "<Derive/Prove/Show that> <target>, starting from <named equation, law, or foundational construction>, showing <the required steps> until <the final result>."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "Derivation begins from [named starting equation, law, or construction]; the chain contains at least [pick a
  concrete number, 4 or higher, appropriate to how many genuine steps this specific result actually takes] sequential
  steps, each expressed as its own formula_block entry that follows mechanically from the one before it; all
  variables or terms are defined (with units, where physical) on first use; correct final result [state the result]
  reached and stated."

SCHEMA COMPATIBILITY — READ BEFORE WRITING ANY A1 DEPTH_GATE:
The study-material schema for STEM sections has ONLY formula_blocks (equations in LaTeX or plain-text) — there is
no diagram, figure, image, or visual-construction field anywhere downstream. Never write a depth_gate that can only
be satisfied by something visual: banned phrasing includes "shown in diagram notation," "illustrated in a figure,"
"drawn," or "depicted." If the topic's canonical proof or derivation is traditionally visual or geometric (area
arguments, similar-triangle constructions, geometric optics, free-body diagrams, vector diagrams), the depth_gate
must instead require every one of those visual relationships to be translated into its own explicit quantitative
or symbolic equation inside a formula_block (e.g. an area equality written as an equation, a ratio written as a
fraction, a substitution written as an equation) — never leave a step describable only in words about a picture.

Worked example (algebraic):
  requirement:  "Derive the time complexity of merge sort step-by-step from the recurrence relation T(n) = 2T(n/2) + n, showing each substitution until the closed form is reached."
  depth_gate:   "Derivation begins from the recurrence relation T(n) = 2T(n/2) + n; the chain contains at least 4 sequential steps, each expressed as its own formula_block entry that follows mechanically from the one before it; all variables defined; correct closed-form result O(n log n) reached and stated."

Worked example (geometric/constructive, translated into equation form per the compatibility rule above):
  requirement:  "Derive the relationship between a solid's cross-sectional area and its volume using Cavalieri's principle, starting from the definition of two solids with equal cross-sectional areas at every height, showing each integration step until the volume formula is reached."
  depth_gate:   "Derivation begins from Cavalieri's principle stated as an equation relating equal cross-sectional areas A(h) at every height h; the chain contains at least 4 sequential steps, each expressed as its own formula_block entry (the area function, the integral setup, the evaluated integral, the final closed form) that follows mechanically from the one before it; all variables defined with units; correct final volume formula reached and stated."

FAMILY A2 — MATHEMATICAL/EMPIRICAL APPLICATION
Use for every other equation-, formula-, or fact-grounded item: applying a named law, rule, or formula to a specific case, or reading/computing a result from given data. This is the default Family A mode.
requirement skeleton:
  "<Calculate/Apply/Determine/Solve for> <target> using <the named equation, rule, or law>, substituting <the specific values or variables involved>, and explain what the result means."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "States the applicable [named equation, rule, or law]; substitutes the specific [values or variables] used; arrives at the correct result [state the result]; explains what the result means in context."
A2 FILL GUIDANCE — Prefer a named equation/relation and its named quantities over inventing a new quantitative framework. If the topic supplies no numeric literals, use the named quantities symbolically or choose a standard classroom instance of that named relation; do not introduce an unrelated measurement framework or parameter class merely to make the item numeric.
A2 HARD FILL RULE — the finished requirement and depth_gate must name:
  (a) the exact equation, law, or relation (write it or its standard name — not "the applicable equation" / "the relevant formula"), AND
  (b) the concrete values OR named symbols being substituted (e.g. "ħ, m, and L for the infinite square well" or "Δx = 0.1 nm" — not the skeleton leftovers "the specific values or variables involved" / "the specific values used").
If you cannot name both (a) and (b), A2 is the wrong family for this item — rewrite as Family C (named case/protocol/experiment) or drop the quantitative framing. Never use A2 for "explain an algorithm / protocol / experiment" items that have no real substitution to perform.
Worked example:
  requirement:  "Calculate the resonance stabilization energy of benzene using experimental heats of hydrogenation, substituting the measured values for cyclohexene and benzene, and explain what the result indicates about aromatic stability."
  depth_gate:   "States the applicable heats of hydrogenation for cyclohexene and benzene; substitutes the specific measured values; arrives at the correct resonance energy of approximately 36 kcal/mol reached and stated; explains what this value indicates about benzene's stability relative to a hypothetical non-aromatic cyclohexatriene."

FAMILY B — IMPLEMENTATION
Use ONLY when the document-level domain is Programming or Mixed, and ONLY for items whose own correctness rests on syntax and runtime behaviour (this is the Programming standard). NEVER use Family B when domain is STEM — see STEM_NO_RUNNABLE_CODE_BLOCK.
- Study material is one document with inline examples — never require a multi-file repo, starter project, or separate downloadable runnable project file.
- For Family B depth_gates, the evidence is a single self-contained code block in the section text, not an external project package the learner must build or submit.
requirement skeleton:
  "<Implement/Build/Write/Debug> <artifact> that <behaviour>, and explain what the code does/outputs and why, including <a named scenario or edge case>."
depth_gate skeleton (fill only the brackets, keep the rest of the sentence exactly as written):
  "At least one self-contained, runnable code block demonstrating [the behaviour or concept]; explanation explicitly states what the code outputs or returns and why; behaviour is shown for [a normal-case scenario] and for [an edge-case scenario]."
Worked example:
  requirement:  "Implement a working debounce function in JavaScript with a configurable delay, and explain line-by-line what happens when the returned closure is called before the timer expires."
  depth_gate:   "At least one self-contained, runnable JavaScript code block implementing the debounce function; explanation explicitly states what the function returns and why; behaviour is shown for a call that completes after the delay and for a call that is cancelled by a later call before the delay expires."

FAMILY C — INTERPRETIVE
Use for history, philosophy, law, ethics, social sciences, literature, business/management — anything whose own correctness rests on named facts and reasoning, not equations or code (this is the Conceptual standard).
Also use Family C inside STEM-domain plans for named experiments, thought experiments, algorithms-as-concepts, protocols, and application cases whose mastery evidence is prose reasoning about a named particular — not a derivation chain and not a numeric substitution. This is the correct non-code home for many STEM "application" items after Family B is banned.
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
  code block, runnable, function call, API, script, notebook.
When domain is STEM, these Family-B-only words must not appear in ANY item's requirement or depth_gate — rewrite the item as Family A or C instead. There is no STEM exception that makes runnable code an acceptable depth_gate.

SKELETON COMPLETION CHECK — apply after drafting, before output
- Every bracketed placeholder copied from a skeleton (anything written as [like this]) must be replaced with real, topic-specific content before output. A literal "[" or "]" surviving into a requirement or depth_gate is the same failure as leaving the skeleton template unfilled, even when the family classification itself was correct.
- Re-read each finished requirement and depth_gate as a reviewer who has never seen these skeletons: if a sentence only parses as a fill-in-the-blank form rather than a complete, topic-specific statement, rewrite it before output.
- Count your A1 items across the whole checklist one more time. If the count is 3 or more, this is an automatic failure — pick the weakest-justified one(s) and rewrite as A2 before output.
- Re-run the A1 VIABILITY GATE on every remaining A1 item. If start≠end across requirement vs depth_gate, the start is a vague theme, or you cannot honestly claim ≥4 mechanical steps, rewrite that item as A2 or Family C before output.
- For every A2 item, confirm the depth_gate names a concrete equation/law and concrete values or symbols — if it still says "specific values" / "variables involved" without naming them, rewrite as Family C or fill the names before output."""

CHECKLIST_RULES_BLOCK = """\
- A depth_gate must be a bar that generic or surface-level coverage cannot satisfy. "A clear description is provided" or "examples are given" is never acceptable on its own — the filled skeleton above already enforces this; do not weaken it.
- priority: "required" — absence is a critical failure. "recommended" — absence is a significant gap.
- section_id must name the single topic_split section where a reviewer will find all depth_gate evidence. Never assign a checklist item to an introductory section (typically ts_1) unless that section is where the concept's complete treatment — not just a definition or overview — actually lives.
- Each topic_split section should own at most 2 must_cover items, and every section should own at least 1 — a section with zero checklist items is uncovered, not efficiently scoped. Only give a concept its own dedicated topic_split section when the mentor explicitly requests a new section or topic (Action A Case 1, D-fallthrough, or F); when the mentor asks for a subtopic within an existing section (Action A Case 2), add the must_cover item under the existing ts_N instead of creating a new section.
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
- Conversely, every topic_split entry MUST be the section_id of at least one must_cover_checklist item. A topic_split
  entry with zero checklist items pointing at it is an invalid plan and must never be produced — before output,
  either add a checklist item that points to it, or remove that topic_split entry. This is not a stylistic
  preference; treat it exactly like the orphaned-section_id case above.
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
