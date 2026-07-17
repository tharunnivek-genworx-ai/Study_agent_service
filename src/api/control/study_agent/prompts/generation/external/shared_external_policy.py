"""Shared external-mode policy for study generation (prefer notes + invent-for-gaps)."""

SHARED_EXTERNAL_POLICY = """
EXTERNAL RESEARCH NOTES POLICY
Research notes are provided in <research_notes>. Prefer them as ground truth when
they cover a concept. For checklist / topic_split concepts the notes omit, invent
complete teaching material from authoritative knowledge at full depth_gate standard.
Notes do not demote, drop, or shrink checklist items.

Per checklist / topic_split section:
1. Scan <research_notes> for definitions, mechanisms, code, equations, named rules,
   or examples that cover that section's concept.
2. If notes cover the concept → adapt that content into trainee-facing lesson tone.
   Do not invent a parallel demo, alternate API, or substitute example for a concept
   the notes already teach.
3. If notes lack that concept → invent complete teaching material (definition,
   mechanism, and concrete example) sufficient to satisfy the depth_gate — the same
   completeness required when no notes are present.
4. Do not contradict facts stated in the notes (APIs, formulas, dates, named cases).
   You may still add correct teaching content that goes beyond the notes.
5. Rewrite into trainee-facing lesson prose. Do not dump raw bullet notebooks from
   the notes into section content.
6. Do not add sections beyond topic_split. Match each section's id and heading.
7. FINAL CHECK: major examples for note-covered concepts trace to the notes (adapted,
   not substituted); concepts the notes omit are still taught fully to depth_gate.

FEW-SHOT (pattern only — invented micro-topic; do not copy subject matter):

Checklist section: "WidgetAPI connection timeouts"
Notes contain: "WidgetAPI.connect(timeout_ms) — ms units; raises TimeoutError"

BAD (substitute invention when notes already cover the concept — do NOT produce):
Teach FakeTimeoutHelper.retry() with api.example.com instead of WidgetAPI.connect.

GOOD (adapt notes into lesson tone — produce this style):
Explain WidgetAPI.connect(timeout_ms), keep the real signature and TimeoutError
behaviour, and show a minimal readable snippet adapted from the notes — expanded
into a full section that meets COMPLETE SECTION STANDARD.

Checklist section: "Retry backoff"
Notes omit retry / backoff entirely.

BAD (under-teach or invent facts that contradict notes — do NOT produce):
A one-sentence stub because notes said nothing, or claim WidgetAPI.connect has
built-in exponential backoff when the notes never say that.

GOOD (invent fully for the gap — produce this style):
Write a complete retry-backoff section to checklist / depth_gate standard. Keep
WidgetAPI facts from the notes unchanged where they appear; do not claim the notes
documented backoff.
"""
