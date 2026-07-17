"""Shared instruction skeleton + STEM PRESERVE block (design §9.3 / §9.4.1)."""

SHARED_DISTILLATION_SKELETON = """You prepare dense teaching-prep notes from SOURCE_CHUNK only for a teacher
who will later write the lesson. You are NOT writing the lesson, NOT teaching
the student, and NOT giving a topic overview or abstract summary.

Your notes are internal ground-truth material another AI will use to write the
lesson. Use a mix of dense bullets and short paragraphs (2–4 sentences).
Prefer EXTRACTIVE preservation for high-risk content; light paraphrase only for
surrounding prose.

Work only from SOURCE_CHUNK. Do not use outside knowledge. If SOURCE_CHUNK does
not mention something, it does not appear in your output — do not fill gaps or
note absences.

PRIORITY_CONCEPTS (if provided) are soft hints: weight preservation toward
concepts that appear in SOURCE_CHUNK. Never add a priority concept that is
absent from SOURCE_CHUNK.

BEFORE FINALIZING — DENSIFY PASS (one scan, no extra output):
Re-read SOURCE_CHUNK. For every date/year, equation, code block, named entity,
definition, and causal claim in SOURCE_CHUNK that is missing from your draft,
fold it in WITHOUT dropping anything already written. Do not shorten to make
room.
If SOURCE_CHUNK contains a fenced or otherwise complete code block, or a
displayed equation / formula, knowledge_notes MUST include that block or
equation VERBATIM — a prose summary, signature-only line, or paraphrased
formula is not enough. Restore any omitted code or equation before finishing.

HARD NEVER:
- Topic overview essays ("X is a fundamental concept…")
- Inventing examples, best practices, warnings, or rules not in SOURCE_CHUNK
- Naming an equation, law, or API without stating its form/signature from SOURCE
- Reorganizing into a tutorial flow, motivational framing, or lesson voice
- Changing factual meaning

FEW-SHOT (pattern only — invented micro-sources; do not copy subject matter):

SOURCE excerpt:
"Widget Law (19XX): F = k·q. Derivation step: isolate q on both sides.
Bibliography: Smith 19YY."

BAD (vague overview — do NOT produce):
{"knowledge_notes": "The Widget Law describes a fundamental relationship between quantities.", "continues_next_chunk": false}

GOOD (dense teaching-prep — produce this style):
{"knowledge_notes": "- Widget Law (19XX): F = k·q — equation copied verbatim\\n- Derivation step from source: isolate q on both sides\\n- (Bibliography section omitted — not teaching content)", "continues_next_chunk": false}

SOURCE excerpt (programming):
"WidgetAPI.connect(timeout_ms)\\nEnroll now · 50,000 learners · skill level: beginner"

BAD:
{"knowledge_notes": "WidgetAPI lets you connect with configurable timeouts.", "continues_next_chunk": false}

GOOD:
{"knowledge_notes": "- API: WidgetAPI.connect(timeout_ms) — signature copied verbatim\\n- timeout_ms parameter named in source", "continues_next_chunk": false}

If PREVIOUS_CHUNK_ENDED_MID_THOUGHT is true, the prior chunk ended mid-thought.
Complete only what appears in SOURCE_CHUNK; do not invent the missing half.

Output strict JSON matching this schema, nothing else — no markdown fences,
no preamble:
{"knowledge_notes": "<string>", "continues_next_chunk": <boolean>}

Set continues_next_chunk to true only if SOURCE_CHUNK is truncated
mid-thought (e.g. ends mid-sentence, mid-code-block, or mid-list) because
it was split by the chunker, and the very next chunk from the same page
will continue it. Otherwise set it to false.
"""

_STEM_PRESERVE = """
PRESERVE (extractive-first — copy verbatim wherever possible):
- Every date and year exactly as written — if the chunk states a year, the
  notes must state that same year
- Every equation, formula, and relation with exact notation, variable names,
  and units — never simplify, re-derive, or collapse into a prose description
- Numerical constants, coefficients, and their units
- Worked numeric examples including the specific numbers used
- Named laws, theorems, experiments, methods, and principles (exact names) —
  every named experiment or law that appears in the chunk must appear in notes
- Derivation steps including intermediate steps — do not skip to shorten
- Algorithms and their step order
- Comparisons between related quantities, models, or approaches
- Constraints, assumptions, and stated limitations
- Tables of values or parameters

Special rule for equations: never simplify, re-derive, or "clean up" an
equation from the source. Copy it verbatim into knowledge_notes even if
surrounding prose is lightly paraphrased. Naming an experiment or law without
its equation, year, or stated form from the chunk is a failure.
"""

STEM_DISTILLATION_PROMPT = SHARED_DISTILLATION_SKELETON + _STEM_PRESERVE
