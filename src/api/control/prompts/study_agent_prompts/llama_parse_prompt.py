LLAMAPARSE_PARSING_INSTRUCTION = """
You are extracting content from a technical study document or reference material uploaded by a mentor.
This content will be used as authoritative source material to generate IT training documents for new employees.
Your extraction must be exhaustive, faithful, and structured. Do not summarize, paraphrase, or omit anything.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERAL EXTRACTION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Extract ALL visible text on every page, in the exact reading order it appears.
2. Do NOT skip, truncate, or summarize any section — including appendices, footnotes,
   sidebars, captions, and headers.
3. Do NOT add commentary, interpretation, or filler text. Only extract what is present.
4. Preserve the original heading hierarchy using markdown (# ## ###) exactly as it
   appears in the source. Do not flatten or promote heading levels.
5. Preserve bold, italic, and inline code formatting where visible.
6. If a section spans multiple pages, continue extracting without any page-break marker
   or interruption. The output must read as a single continuous document.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CODE EXTRACTION — CRITICAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
8. Do NOT extract diagrams, flowcharts, or architecture drawings as code blocks. Those belong
   in the "images" array with a detailed "full_description" — not as mermaid or markup.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMAGE AND DIAGRAM EXTRACTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For every image, diagram, chart, screenshot, or figure present:

0. EVERY visual figure MUST become its own structured entry in that section's "images"
   array, each with its own "semantic_name". This is mandatory and applies to ALL figures,
   including process flowcharts, architecture diagrams, framework diagrams (e.g. a Scrum
   framework diagram), cycle diagrams, and charts. NEVER describe a figure only inside
   "body_text" or only as a one-line prose sentence and then omit it from the "images" array
   — if a page shows a diagram, there must be a matching image entry for it. A diagram title
   in body_text such as "# THE AGILE: SCRUM FRAMEWORK AT A GLANCE" followed by a short summary
   STILL requires a full "images" entry with a complete "full_description" listing every
   visible label, role, arrow, and artifact. Do not merge two separate figures into a single
   image entry, and do not drop a figure just because the surrounding text already explains
   it. The number of image entries you produce must equal the number of distinct visual
   figures actually present in the source — including figures on the last pages of the document.
   Do NOT generate mermaid, flowchart markup, PlantUML, Graphviz, or any diagram-as-code in
   "code_blocks". Diagrams belong ONLY in the "images" array via rich "full_description" text.

1. Insert a clearly labelled block at the exact position where the image appears in
   the document flow. Use this format:

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
7. For EVERY image or figure, you MUST produce a short, meaningful semantic name based on
   the nearest heading and what the image shows, and place it in the "semantic_name" field
   of that image's metadata. Use lowercase, words separated by underscores, and no spaces,
   for example:
   - "waterfall_model_diagram"
   - "incremental_process_flow"
   - "agile_sprint_cycle_chart"
   If multiple images under the same heading have similar content, append a number suffix,
   e.g. "waterfall_model_diagram_1", "waterfall_model_diagram_2".
   The "semantic_name" field is mandatory and must never be left empty.
8. Keep "semantic_name" separate from "figure_label". The "figure_label" field is ONLY for a
   caption that is literally printed in the source (e.g. "Fig. Agile Model",
   "THE AGILE: SCRUM FRAMEWORK AT A GLANCE"); leave it as an empty string when no printed
   caption exists. Never copy the semantic name into figure_label.
9. For EVERY image entry you MUST also populate these three page-index fields for inventory:
   - "source_page": the 1-based PHYSICAL page index in the PDF file itself (page 1 = the very
     first page of the uploaded PDF, page 2 = the second page, and so on). This is NOT the
     number printed in the document footer or header (e.g. "Software Engineering Page 11" is a
     printed page label — do NOT use 11 as source_page unless the figure literally appears on
     the 11th physical page of the PDF file). Count from the start of the file.
   - "figure_index_on_page": reading-order index of this figure on that physical page,
     starting at 1. Use 1 when only one figure appears on the page. If two figures share the
     same page, the first is 1 and the second is 2.
   - "document_figure_index": global reading-order index across the entire document, starting
     at 1 for the first figure anywhere in the document and incrementing by 1 for each
     subsequent figure in the order they appear.
   All three fields are mandatory and must never be omitted or left null.
10. SECTION STRUCTURE for multi-topic pages: when a page introduces a sub-topic with its own
    heading (e.g. "### Scrum" or a diagram title under "Other process models…"), place the
    diagram's "images" entry in the section whose heading best matches that sub-topic — not
    only in a parent bullet-list section. Prefer a dedicated section per sub-topic when the
    source clearly separates them.
11. "full_description" must be exhaustive — list every box label, role name, arrow direction,
    connection, and cycle step visible in the figure. Write 4–8 sentences minimum per figure.
    One-sentence summaries like "Diagram of the Scrum Framework showing the flow from…" are
    NOT acceptable; enumerate the actual components in reading order so downstream AI can
    teach from text alone without seeing the image.
12. Do NOT put diagram or flowchart content into "code_blocks". If the source shows a visual
    diagram, capture it ONLY in "images" with a thorough "full_description" — never as
    mermaid, pseudo-code, or markup syntax.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TABLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Render every table in full markdown table format.
2. Include the table title or caption above the table if present.
3. Do not summarize or collapse rows. Every row must appear in the output.
4. If a table spans multiple pages, merge all rows into a single markdown table.
5. Preserve column headers exactly as written.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MULTI-PAGE AND CROSS-PAGE CONTINUITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Treat the entire document as one continuous extraction. Never insert page numbers,
   page break markers, or "--- Page N ---" dividers into the output.
2. If a sentence or paragraph is cut at a page boundary, join it seamlessly.
3. If a numbered or bulleted list is split across pages, continue the list without
   restarting numbering or inserting a gap.
4. If a section heading appears at the bottom of a page with no body text following
   it on that page, still include it and continue with its body from the next page.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

---

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Never truncate a code block under any circumstances.
- Never describe an image with only a single word or tag.
- Never add interpretation, opinion, or commentary to any extracted content.
- Never reorder sections to match a preferred structure — preserve source order.
- Never omit a section just because it seems repetitive or basic.
- Never omit the last sections or figures of the document — extract through the final page.
- If any content is genuinely illegible or unreadable, mark it exactly as:
  [ILLEGIBLE: approximate location or context]
"""
