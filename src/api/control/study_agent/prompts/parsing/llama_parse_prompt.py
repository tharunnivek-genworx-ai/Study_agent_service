# src/api/control/study_agent/prompts/parsing/llama_parse_prompt.py
"""LlamaParse PDF extraction prompt — domain-aware, modular.

Previously the monolithic LLAMAPARSE_PARSING_INSTRUCTION lived inside
regeneration_prompt.py. This module replaces it. Import from here:

    from src.api.control.study_agent.prompts.parsing.llama_parse_prompt import (
        build_parsing_instruction,
        LLAMAPARSE_PARSING_INSTRUCTION,
    )

Or via the package / legacy shim:

    from src.api.control.study_agent.prompts.parsing import build_parsing_instruction
    from src.api.control.study_agent.prompts.llamaparse_prompt import (
        build_parsing_instruction,
    )
"""

from __future__ import annotations

from src.api.utils.prompt_utils.domain_merge import domains_to_include

# ── Universal Blocks (always included regardless of domain) ───────────────────

_GENERAL_RULES_BLOCK = """\
GENERAL EXTRACTION RULES
1. Extract ALL visible text on every page, in the exact reading order it appears.
2. Do NOT skip, truncate, or summarize any section — including appendices, footnotes,
   sidebars, captions, and headers.
3. Do NOT add commentary, interpretation, or filler text. Only extract what is present.
4. Preserve the original heading hierarchy using markdown (# ## ###) exactly as it
   appears in the source. Do not flatten or promote heading levels.
5. Preserve bold, italic, and inline code formatting where visible.
6. If a section spans multiple pages, continue extracting without any page-break marker
   or interruption. The output must read as a single continuous document."""

_IMAGE_EXTRACTION_COMMON_BLOCK = """\
IMAGE AND DIAGRAM EXTRACTION
For every image, diagram, chart, screenshot, or figure present:
0. EVERY visual figure MUST become its own structured entry in that section's "images"
   array, each with its own "semantic_name". This is mandatory and applies to ALL figures,
   including process flowcharts, architecture diagrams, framework diagrams, cycle diagrams,
   and charts. NEVER describe a figure only inside "body_text" or only as a one-line prose
   sentence and then omit it from the "images" array. A diagram title in body_text STILL
   requires a full "images" entry with a complete "full_description" listing every visible
   label, role, arrow, and artifact. Do not merge two separate figures into a single image
   entry, and do not drop a figure just because the surrounding text already explains it.
   The number of image entries you produce must equal the number of distinct visual figures
   actually present in the source — including figures on the last pages of the document.
   Do NOT generate mermaid, flowchart markup, PlantUML, Graphviz, or any diagram-as-code
   in "code_blocks". Diagrams belong ONLY in the "images" array via rich "full_description".
1. Insert a clearly labelled block at the exact position where the image appears:
   [IMAGE: <Figure number or heading if present>]
   Description: <A full, precise description of what the image shows.>
   Content: <Describe all visible labels, values, legend items, axis titles, node
   names, arrows, annotations, and any text inside the image.>
   Purpose: <One sentence on what concept or step this image is illustrating.>
2. For architecture diagrams or flowcharts, describe every component, every connection,
   and the direction of every arrow.
3. For charts and graphs, extract axis labels, all data series names, approximate
   values or ranges visible, and the chart title.
4. For screenshots of code editors, terminals, or UI, treat the visible content as
   a code block or structured list as appropriate.
5. For tables embedded in images, extract the table data in markdown table format.
6. Do NOT replace an image with just "[image]" or "[figure]" — a full description
   is mandatory.
7. For EVERY image or figure, produce a short meaningful semantic_name based on the
   nearest heading and what the image shows. Use lowercase, words separated by underscores,
   no spaces (e.g. "waterfall_model_diagram", "agile_sprint_cycle_chart"). Append a number
   suffix for multiple images under the same heading (e.g. "waterfall_model_diagram_1").
   The "semantic_name" field is mandatory and must never be left empty.
8. Keep "semantic_name" separate from "figure_label". The "figure_label" field is ONLY
   for a caption literally printed in the source (e.g. "Fig. Agile Model"); leave it as
   an empty string when no printed caption exists. Never copy the semantic name into figure_label.
9. For EVERY image entry populate these three page-index fields:
   - "source_page": the 1-based PHYSICAL page index in the PDF file itself (page 1 = the
     very first page of the uploaded PDF). This is NOT the number printed in the document
     footer or header — count from the start of the file.
   - "figure_index_on_page": reading-order index of this figure on that physical page,
     starting at 1. If two figures share the same page, the first is 1 and the second is 2.
   - "document_figure_index": global reading-order index across the entire document,
     starting at 1 for the first figure anywhere in the document.
   All three fields are mandatory and must never be omitted or left null.
10. SECTION STRUCTURE for multi-topic pages: when a page introduces a sub-topic with its
    own heading, place the diagram's "images" entry in the section whose heading best
    matches that sub-topic — not only in a parent bullet-list section. Prefer a dedicated
    section per sub-topic when the source clearly separates them.
11. "full_description" must be exhaustive — list every box label, role name, arrow
    direction, connection, and cycle step visible in the figure. Write 4–8 sentences
    minimum per figure. One-sentence summaries are NOT acceptable; enumerate the actual
    components in reading order so downstream AI can teach from text alone without seeing
    the image.
12. Do NOT put diagram or flowchart content into "code_blocks". If the source shows a
    visual diagram, capture it ONLY in "images" with a thorough "full_description" — never
    as mermaid, pseudo-code, or markup syntax."""

_TABLES_BLOCK = """\
TABLES
1. Render every table in full markdown table format.
2. Include the table title or caption above the table if present.
3. Do not summarize or collapse rows. Every row must appear in the output.
4. If a table spans multiple pages, merge all rows into a single markdown table.
5. Preserve column headers exactly as written."""

_CONTINUITY_BLOCK = """\
MULTI-PAGE AND CROSS-PAGE CONTINUITY
1. Treat the entire document as one continuous extraction. Never insert page numbers,
   page break markers, or "--- Page N ---" dividers into the output.
2. If a sentence or paragraph is cut at a page boundary, join it seamlessly.
3. If a numbered or bulleted list is split across pages, continue the list without
   restarting numbering or inserting a gap.
4. If a section heading appears at the bottom of a page with no body text following
   it on that page, still include it and continue with its body from the next page."""

_OUTPUT_STRUCTURE_BLOCK = """\
OUTPUT STRUCTURE
Produce the output in the following order, using the exact section markers below.
If a section is not present in the source document, write:
[SECTION NOT PRESENT IN SOURCE]
---
## EXTRACTED CONTENT
<All main body text, headings, paragraphs, lists, tables, code blocks, and image
descriptions in the order they appear in the source document.>
## SUMMARY OF KEY TOPICS
<A bullet list of the main technical topics and concepts covered in this document.
Do not invent topics — only list what is explicitly covered.>
## CODE BLOCKS INVENTORY
<A numbered list of every code block found, with:
- Block number
- Language detected
- First line of the block (for identification)
- Page range it appeared on (approximate)>
## IMAGES AND DIAGRAMS INVENTORY
<A numbered list of every image/diagram found, with:
- Image number (document_figure_index)
- source_page and figure_index_on_page
- Type (diagram, chart, screenshot, table, etc.)
- Brief label from the document if present>
---"""

_ABSOLUTE_RULES_BLOCK = """\
ABSOLUTE RULES
- Never truncate a code block under any circumstances.
- Never describe an image with only a single word or tag.
- Never add interpretation, opinion, or commentary to any extracted content.
- Never reorder sections to match a preferred structure — preserve source order.
- Never omit a section just because it seems repetitive or basic.
- Never omit the last sections or figures of the document — extract through the final page.
- If any content is genuinely illegible or unreadable, mark it exactly as:
  [ILLEGIBLE: approximate location or context]"""


# ── Domain-Specific Code Extraction Blocks ────────────────────────────────────
# Priority: Programming (most comprehensive) > STEM (computational only) > Conceptual (minimal).
# Mixed/None uses the Programming block since it covers all executable code types.

_PROGRAMMING_CODE_EXTRACTION_BLOCK = """\
CODE EXTRACTION — CRITICAL
Code blocks are the most important content in this document. Apply these rules strictly:
1. Extract every code block completely. Do not truncate, abbreviate, or replace any
   portion with "...", "[rest of code]", "[continued]", or any similar placeholder.
2. If a code block starts on one page and continues on the next, join it into a single
   uninterrupted fenced code block. Never split a code block across sections.
3. Detect the programming language from context and apply the correct fenced markdown
   language tag (e.g. ```python, ```bash, ```yaml, ```sql, ```json).
4. Preserve all indentation exactly. Spaces and tabs are semantically significant in
   languages like Python and YAML — do not collapse or alter them.
5. Preserve all comments inside code, including inline comments (# this does X) and
   block comments.
6. If a line of code is partially cut off at the edge of a page due to formatting,
   reconstruct the full line using context. Mark it with a trailing comment:
   # [reconstructed from page break]
7. Never merge two separate code blocks into one. Keep each distinct example separate.
8. Do NOT extract diagrams, flowcharts, or architecture drawings as code blocks. Those
   belong in the "images" array with a detailed "full_description" — not as mermaid or
   markup."""

_STEM_CODE_EXTRACTION_BLOCK = """\
CODE EXTRACTION — COMPUTATIONAL ONLY
Extract code blocks only when they represent genuine executable source code (Python,
MATLAB, R, Julia, C, Fortran, etc.) used for numerical computation, simulation, or
data processing. Do not extract mathematical notation or derivation steps as code.
1. Extract every computational code block completely — no truncation, abbreviation, or
   placeholder (no "...", "[rest of code]", "[continued]").
2. If a code block starts on one page and continues on the next, join it into a single
   uninterrupted fenced block. Never split a code block across sections.
3. Detect the language and apply the correct fenced markdown language tag.
4. Preserve all indentation, inline comments, and block comments exactly.
5. Never merge two separate code blocks into one.
6. Do NOT extract mathematical equations, derivation steps, or chemical reactions as
   code blocks — those belong in the body text as notation or in the "images" array if
   they appear as rendered figures.
7. Do NOT generate mermaid, pseudo-code, or any diagram-as-code. Visual figures belong
   in the "images" array only."""

_CONCEPTUAL_CODE_EXTRACTION_BLOCK = """\
CODE EXTRACTION
Conceptual documents rarely contain executable source code. Apply these rules:
1. If genuine executable code is present (e.g. a policy automation script, a pseudocode
   example, or a configuration file), extract it completely with the correct language tag.
   No truncation or placeholder abbreviations.
2. Do NOT treat structured frameworks, process descriptions, or bulleted checklists as
   code blocks even if they appear in a fixed-width font — extract them as body text.
3. Never merge two separate code blocks into one.
4. Do NOT extract process diagrams, framework visuals, or organisational structures as
   code blocks or mermaid markup. All visual figures belong in the "images" array."""


# ── Domain-Specific Content Extraction Blocks ─────────────────────────────────

_STEM_EXTRACTION_BLOCK = """\
FORMULA, EQUATION, AND DERIVATION EXTRACTION — STEM CRITICAL
Mathematical equations, chemical reactions, derivation steps, and scientific notation
are primary content in STEM documents. Apply these rules with the same strictness as
code extraction in a Programming document — these are the most important content here.
1. Extract every formula, equation, reaction, and derivation step completely. Never
   paraphrase, abbreviate, or substitute a prose description for the actual notation.
2. Preserve every variable, subscript, superscript, Greek letter, and operator symbol
   exactly as it appears. If LaTeX or MathML is visible in the source, extract it
   verbatim. If only a rendered image of the equation is present, represent it in
   unambiguous plain-text notation (e.g. "E = m*c^2", "integral from 0 to T of f(x) dx",
   "delta_G = delta_H - T*delta_S").
3. For derivation sequences: preserve the reading order of every step — never merge two
   derivation steps into one line. If steps span multiple pages, join them seamlessly in
   the correct logical sequence without inserting a page-break marker between steps.
4. Carry variable definitions forward: when the source defines a variable inline
   (e.g. "where v is velocity in m/s"), include that definition in the extracted text
   immediately following the formula that introduces the variable.
5. For chemical reactions: extract reactants, arrow notation, products, and any stated
   conditions (temperature, pressure, catalyst, solvent) exactly as written. Never
   reorder, abbreviate, or balance a reaction beyond what the source shows.
6. Physical and mathematical constants must be extracted with their stated values and
   units. Do not substitute a constant's value when the source uses its symbol — preserve
   the symbol and extract any adjacent value definition verbatim.
7. Worked numerical examples must be extracted step by step. If a worked example spans
   multiple pages, join all steps into one continuous extraction block.
8. Tables containing numerical data, unit conversions, physical constants, or experimental
   results must be extracted in full markdown table format — do not summarise rows,
   collapse ranges, or omit units from column headers."""

_PROGRAMMING_EXTRACTION_BLOCK = """\
ARCHITECTURE, API, AND SYSTEM DESIGN EXTRACTION
1. ARCHITECTURE AND SYSTEM DIAGRAMS: for every architecture diagram, data flow diagram,
   or system design visual, describe in "full_description": every component box (its name
   and its stated role or responsibility), every connection between components (what
   connects to what), the direction and label of every arrow or edge, and any boundary
   boxes (e.g. "service boundary", "VPC", "cluster"). Enumerate components in reading
   order top-to-bottom, left-to-right.
2. API REFERENCE AND METHOD SIGNATURE TABLES: extract in full markdown table format.
   Preserve every column (method name, parameters, parameter types, return type,
   description, exceptions) and every row. Do not collapse overloaded signatures.
3. SEQUENCE DIAGRAMS: extract every actor or lifeline name in left-to-right order.
   For each message, record: the message label, the source lifeline, the destination
   lifeline, and the direction (synchronous, asynchronous, return). Preserve the
   top-to-bottom temporal order of all messages.
4. UML CLASS DIAGRAMS: for each class, extract the class name, every attribute with
   its type and visibility modifier, and every method with its signature and visibility.
   Describe all relationships (inheritance, composition, aggregation, dependency) as
   prose in "full_description", stating which class is on each end.
5. TERMINAL AND IDE SCREENSHOTS: extract the visible text content as a code block with
   the language tag "text" (or the detected shell/language if identifiable). Preserve
   line numbers if visible. Preserve prompt symbols ($ #) exactly."""

_CONCEPTUAL_EXTRACTION_BLOCK = """\
ARGUMENT, CASE STUDY, FRAMEWORK, AND CAUSAL CHAIN EXTRACTION
Conceptual documents are structured around arguments, named examples, causal chains,
and analytical frameworks. These are primary content — extract their structure faithfully.
1. ARGUMENTS: when the source states a claim followed by supporting evidence or reasoning,
   preserve the sequence exactly — do not flatten into a single sentence. Extract:
   (a) the claim as stated, (b) each piece of supporting evidence in the order given,
   (c) any stated conclusion or implication. If the argument is structured as a numbered
   list or bullet set, preserve that structure.
2. CASE STUDIES AND NAMED EXAMPLES: extract the named actor (organisation, person,
   legislation, event, or court ruling), the described context, the action or decision
   taken, and the stated outcome. Never condense a case study into a single sentence —
   preserve every named detail the source provides, including dates, figures, and
   attributed outcomes.
3. CAUSAL CHAINS: when the source explains why something happened (precondition → trigger
   → mechanism → outcome), preserve every link in the chain. Do not merge the mechanism
   into the outcome or skip intermediate steps. If the source names multiple contributing
   factors, list them all.
4. FRAMEWORKS AND MODELS: when the source presents a named framework, model, or typology
   (e.g. Porter's Five Forces, Maslow's Hierarchy, a legal classification scheme, an
   agile maturity model), extract every component, every level or tier, and every
   definition provided. Tables that define framework components must be extracted in
   full markdown table format.
5. STATISTICS AND ATTRIBUTED METRICS: extract every percentage, figure, or metric exactly
   as stated, including the source attribution if the document provides one (e.g.
   "according to Gartner, 2023" or "McKinsey Global Institute reported"). Never omit the
   attribution or silently round the figure.
6. COMPARISON TABLES: extract every column and every row without collapsing cells. The
   document may compare two frameworks, two policy approaches, or two historical periods —
   every cell matters and must be preserved exactly."""


# ── Domain-Specific Image Addition Blocks ─────────────────────────────────────
# These supplement _IMAGE_EXTRACTION_COMMON_BLOCK with domain-specific guidance.

_STEM_IMAGE_ADDITION_BLOCK = """\
STEM IMAGE RULES (supplement to IMAGE AND DIAGRAM EXTRACTION above)
- SCIENTIFIC GRAPHS (stress-strain curves, phase diagrams, titration curves, Bode plots,
  Feynman diagrams, etc.): extract axis labels with units, all curve or series labels,
  all annotated data points or inflection points, the graph title, and the described
  physical or chemical significance of any marked region or transition point.
- REACTION MECHANISM DIAGRAMS: name every reactant, intermediate, and product. Describe
  every arrow type (bond-breaking, bond-forming, electron-pair movement, proton transfer).
  State the reaction conditions shown (temperature, solvent, catalyst, pressure).
- MATHEMATICAL FUNCTION PLOTS: state the function label or equation if printed on the
  figure, the axis ranges shown, any marked asymptotes, critical points, inflection
  points, or discontinuities, and any annotations on the curve itself.
- EXPERIMENTAL APPARATUS DIAGRAMS: name every component in reading order, state what each
  connects to, and describe the flow of material, current, or signal through the diagram."""

_PROGRAMMING_IMAGE_ADDITION_BLOCK = """\
PROGRAMMING IMAGE RULES (supplement to IMAGE AND DIAGRAM EXTRACTION above)
- CLASS AND ENTITY-RELATIONSHIP DIAGRAMS: extract every entity or class name, every
  attribute with its type, every method with its signature. Describe every relationship
  line: state the relationship type (inheritance, composition, aggregation, dependency,
  foreign-key association) and the cardinality on each end (one-to-one, one-to-many, etc.).
- SEQUENCE DIAGRAMS: extract every actor or lifeline name in left-to-right order. Record
  each message in top-to-bottom order: its label, source, destination, and synchrony type.
  Note any activation boxes, opt/alt/loop frames, and their conditions.
- STATE MACHINE AND ACTIVITY DIAGRAMS: name every state or activity node. Describe every
  transition arrow with its guard condition or trigger label. Identify the initial and
  terminal states. Note any fork/join bars or decision nodes with their branch conditions.
- ALGORITHM FLOWCHARTS: extract every decision node with both its yes and no branch
  labels, every process box with its label, and the flow direction between nodes in
  reading order. Note the start and end nodes explicitly."""

_CONCEPTUAL_IMAGE_ADDITION_BLOCK = """\
CONCEPTUAL IMAGE RULES (supplement to IMAGE AND DIAGRAM EXTRACTION above)
- PROCESS AND WORKFLOW DIAGRAMS: name every stage, role, or step box in reading order.
  Describe every arrow direction and label. State the start condition and end condition.
  If swimlanes are present, name each swimlane and note which boxes fall within it.
- ORGANISATIONAL CHARTS: name every role or department box. State its level in the
  hierarchy. Describe every reporting line — note whether lines are solid (direct report)
  or dashed (dotted-line / functional report) if that distinction is visible.
- FRAMEWORK AND MODEL DIAGRAMS (pyramids, matrices, cycles, radar charts): name every
  tier, quadrant, phase, or axis with its label exactly as printed. Describe the implied
  progression or relationship between components (e.g. "tiers build on each other
  bottom-to-top", "quadrants are defined by the intersection of two axes named X and Y").
- TIMELINE DIAGRAMS: extract every labelled event or milestone in chronological order,
  with its position on the timeline (date, period, or relative label such as "Phase 1")."""


# ── Build Functions ───────────────────────────────────────────────────────────


def _build_code_extraction_block(domain: str | None) -> str:
    """
    Programming and Mixed/None: full critical code extraction (covers all executable code).
    STEM only: computational-code extraction (no programming language details).
    Conceptual only: minimal extraction (warns against treating prose as code).
    """
    included = domains_to_include(domain)
    if "Programming" in included:
        return _PROGRAMMING_CODE_EXTRACTION_BLOCK
    if "STEM" in included:
        return _STEM_CODE_EXTRACTION_BLOCK
    return _CONCEPTUAL_CODE_EXTRACTION_BLOCK


def _build_domain_extraction_block(domain: str | None) -> str:
    """Include all domain-specific content extraction supplements."""
    included = domains_to_include(domain)
    parts: list[str] = []
    if "STEM" in included:
        parts.append(_STEM_EXTRACTION_BLOCK)
    if "Programming" in included:
        parts.append(_PROGRAMMING_EXTRACTION_BLOCK)
    if "Conceptual" in included:
        parts.append(_CONCEPTUAL_EXTRACTION_BLOCK)
    return "\n\n".join(parts)


def _build_image_addition_block(domain: str | None) -> str:
    """Include all domain-specific image extraction supplements."""
    included = domains_to_include(domain)
    parts: list[str] = []
    if "STEM" in included:
        parts.append(_STEM_IMAGE_ADDITION_BLOCK)
    if "Programming" in included:
        parts.append(_PROGRAMMING_IMAGE_ADDITION_BLOCK)
    if "Conceptual" in included:
        parts.append(_CONCEPTUAL_IMAGE_ADDITION_BLOCK)
    return "\n\n".join(parts)


def build_parsing_instruction(domain: str | None = None) -> str:
    """
    Build the LlamaParse extraction instruction for a specific domain.

    domain=None or domain="" → all-domain version (safe default when domain is unknown).
    domain="STEM"            → formula/equation focus; minimal code extraction.
    domain="Programming"     → critical code extraction; architecture/API extraction.
    domain="Conceptual"      → argument/case-study extraction; minimal code extraction.
    domain="Mixed"           → all blocks included (same as None).
    """
    blocks = [
        _GENERAL_RULES_BLOCK,
        _build_code_extraction_block(domain),
        _build_domain_extraction_block(domain),
        _IMAGE_EXTRACTION_COMMON_BLOCK,
        _build_image_addition_block(domain),
        _TABLES_BLOCK,
        _CONTINUITY_BLOCK,
        _OUTPUT_STRUCTURE_BLOCK,
        _ABSOLUTE_RULES_BLOCK,
    ]
    return "\n\n".join(b for b in blocks if b.strip())


# Backward-compatible constant — all-domain version; equivalent to the original
# monolithic LLAMAPARSE_PARSING_INSTRUCTION that lived in regeneration_prompt.py.
LLAMAPARSE_PARSING_INSTRUCTION = build_parsing_instruction(domain=None)
