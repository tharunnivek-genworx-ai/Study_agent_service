"""Action taxonomy: governs how mentor feedback / a regeneration goal may touch
topic_split and must_cover_checklist. Used by both improvement_prompt and
regeneration_prompt — the rules are identical, only the input tag name differs."""

from __future__ import annotations


def build_action_taxonomy_block(
    feedback_tag: str,
    feedback_word: str,
    *,
    step_number: int = 2,
) -> str:
    """feedback_tag: e.g. 'mentor_feedback' or 'regeneration_goal' (the XML tag name).
    feedback_word: e.g. 'feedback' or 'goal' (used in prose)."""
    return f"""\
STEP {step_number} — CLASSIFY THE {feedback_word.upper()}'S ACTION, THEN APPLY ONLY THAT ACTION'S RULE
This classification is the single highest-priority decision in this task. Read <{feedback_tag}>, decide which ONE action below it is, and apply only that action's rule to <previous_plan>. Never apply two actions' rules in the same run unless the {feedback_word} explicitly names two distinct edits (e.g. "add a section on X and remove the section on Y" — apply Action A to X and Action C to Y, nothing else moves).

DEFAULT (applies before any action-specific rule, and always applies to anything the classified action does not target):
<previous_plan> is the ground truth for both topic_split and must_cover_checklist. Every topic_split section and every checklist item that existed in <previous_plan> survives into the new plan with identical id, heading/concept, requirement, priority, section_id, and depth_gate — UNLESS the action you classify below explicitly says otherwise for that specific item. Silently renaming, merging, splitting, reordering, rewording, or dropping an untouched section or item is a failure even if the new JSON is well-formed.

ACTION A — ADD A NEW TOPIC OR SUBTOPIC
Trigger: the {feedback_word} asks for content that does not already exist in <previous_plan>. Classify into one of two cases before acting:

CASE 1 — NEW TOP-LEVEL SECTION ("add a section on X", "include a topic about Y", "also cover Z") — the requested content has no parent section in <previous_plan>.
- Append ONE new topic_split entry (next unused ts_N id) for the new topic. Do not rename, reorder, or touch any existing ts_N entry.
- Add 1–2 new must_cover_checklist items whose section_id points at this NEW ts_N — see the STRUCTURAL INTEGRITY rule: the new topic_split entry and the new checklist item(s) must both appear in this same output.
- Do not touch any other section's topic_split entry or checklist items.

CASE 2 — SUBTOPIC WITHIN AN EXISTING SECTION ("under the X section add Y", "inside X add a subtopic on Y", "add Y as a subtopic of X", "within X include Y") — the content is explicitly scoped inside a section that already exists in <previous_plan>.
- Do NOT create a new topic_split entry. The parent section already exists.
- Add one new must_cover_checklist item whose section_id points at the EXISTING parent ts_N (not a new id). Write its requirement and depth_gate as a clearly scoped sub-concept within that parent.
- The document writer places this item's content inside the parent section's subsections array — never as a separate top-level section. The existing checklist item(s) for the parent remain unchanged alongside the new item (the 2-item-per-section cap still applies).
- Do not touch any other section's topic_split entry or checklist items.

When the {feedback_word} is ambiguous, prefer CASE 2 if a plausible parent section already exists in <previous_plan>; use CASE 1 only if the content genuinely has no home in any existing section.

ACTION B — EXTEND / DEEPEN AN EXISTING TOPIC
Trigger: the {feedback_word} asks for more depth on something that already has a topic_split entry ("make X more detailed", "go deeper on Y", "explain Z thoroughly", "cover every sub-part of X").
- Do NOT create a new topic_split entry — the topic already exists. This is the most common mistake to avoid: depth requests are not section requests.
- Prefer raising the existing checklist item's depth over adding a new one: rewrite that item's requirement and depth_gate using the richer end of its evidence family's skeleton — name a second scenario, a second named case, or a further worked step — without changing its evidence family.
- Only add a second checklist item under the SAME existing section_id if the {feedback_word} names a genuinely distinct sub-concept the current item doesn't isolate (e.g. existing item covers useEffect's basic use, {feedback_word} specifically asks for cleanup-function behaviour as its own depth_gate). A topic_split section may still own at most 2 items.
- Do not touch any other section's topic_split entry or checklist items.

ACTION C — REMOVE A SUBTOPIC OR TOPIC
Trigger: ("remove X", "drop the section on Y", "we don't need Z anymore").
- If the removal names a whole topic_split section: delete that ts_N entry AND every must_cover_checklist item whose section_id points to it.
- If the removal names only a sub-concept inside a section (not the whole section): delete only the matching checklist item(s). Keep the topic_split entry if at least one other checklist item still points to it; if removing the item(s) would leave that topic_split entry with zero checklist items, also delete the now-empty topic_split entry.
- Do not touch any other section's topic_split entry or checklist items.

ACTION D — UNSCOPED "ADD/MAKE DETAILED" REQUEST (no named sub-topic, no ceiling stated)
Trigger: ("add some more sub-topics and make it detailed", "make this topic more detailed" with nothing more specific).
- Default to Action B's behaviour (no new topic_split entry, raise depth on the existing item, optionally one more item under the SAME existing section_id) — adding a topic_split section is the more disruptive change and should only happen when the {feedback_word}'s wording clearly points at content unrelated to any existing section.
- Only fall through to Action A Case 1's behaviour (one new topic_split entry) if, on reflection, the requested content genuinely doesn't belong under any existing section_id.
- You have discretion on exactly how many new items / how much extra depth to add (up to the 2-items-per-section cap) — use judgement, but never restructure or touch sections the {feedback_word} didn't imply.

ACTION E — TONE / STYLE / AUDIENCE / FORMAT, NO STRUCTURAL CHANGE NAMED
Trigger: ("make it sound more beginner-friendly", "rewrite this in a more engaging tone", "simplify the language", a generic "full rewrite" request that names no new or removed topic).
- topic_split and must_cover_checklist are UNCHANGED — copy <previous_plan> verbatim, including every id, heading, purpose, concept, requirement, priority, section_id, and depth_gate.
- Tone/style/audience changes are handled at the document-writing stage, not in this plan; this plan node never adds, removes, or re-depths a section for this kind of request.

ACTION F — EXPLICIT FULL RESTRUCTURE
Trigger: only when the {feedback_word} explicitly says to restructure the whole document, reorganise the topics, rebuild it from scratch, or change the structure of the whole thing.
- This is the ONLY action that authorises discarding <previous_plan>'s topic_split/must_cover_checklist shape entirely. Rebuild both as if this were a fresh generation, honouring the teaching_instruction and any reference_sections, using the sizing and style rules below. Keep "domain" from <previous_plan> unchanged.
- This is the ONLY action not bound by the DEFAULT preservation rule above."""
