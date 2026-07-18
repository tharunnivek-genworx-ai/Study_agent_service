"""Cross-website merge prompt (design §11.1 / §4d union-with-dedupe)."""

CROSS_WEBSITE_MERGE_PROMPT = """You produce one dense teaching-prep ground-truth notebook by UNION of
unique notes across up to three web sources on the same topic. A separate
lesson-writing agent will use this document — it is NOT the lesson itself.

You are NOT re-summarizing into a short essay or topic overview. You are
assembling teaching-prep notes a teacher would keep before writing a lesson.

You must not:
- add any information not present in the provided website summaries
- resolve disagreements between sources by guessing which is correct — if two
  sources genuinely conflict, preserve both statements and note the conflict
- invent section headings, tutorial structure, or motivational framing
- fill gaps using outside knowledge
- discard a unique code block, equation, date, or named entity to shorten output

You must:
- UNION unique facts, bullets, and short paragraphs from all sources
- dedupe near-duplicates across sources, keeping the more complete version
- preserve every equation, code snippet, date, and named example exactly as
  given in the source summaries
- target a dense 1500–3000 token notebook when source material supports it;
  never shorten by dropping unique detail

BEFORE FINALIZING — DENSIFY PASS (one scan):
Re-read all source summaries. Fold in any date, equation, code block, named
entity, or definition present in a source but missing from your draft WITHOUT
dropping anything already written.

FEW-SHOT (pattern only — invented micro-sources):

Site A notes:
"- Widget Law (19XX): F = k·q"
"- connect(timeout_ms) sets a timeout"

Site B notes:
"- Widget Law: F = k·q (coefficient k has units)"
"- WidgetAPI.connect(timeout_ms) — ms units"

GOOD merged style (union + dedupe, not re-summarize):
{"ground_truth_reference": "- Widget Law (19XX): F = k·q — coefficient k has units (Site A + B)\\n- WidgetAPI.connect(timeout_ms) — ms units (Site B)"}

BAD (re-summarized overview — do NOT produce):
{"ground_truth_reference": "The Widget Law and API describe fundamental widget behavior."}

Output strict JSON, nothing else:
{"ground_truth_reference": "<string>"}
"""
