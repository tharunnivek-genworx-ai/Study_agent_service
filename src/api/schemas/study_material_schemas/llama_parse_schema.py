{
    "type": "object",
    "properties": {
        "document_metadata": {
            "type": "object",
            "description": "Top-level metadata inferred from the document.",
            "properties": {
                "detected_title": {
                    "type": "string",
                    "description": "The title of the document as it appears on the cover page or first heading. If not found, infer from the most prominent heading.",
                },
                "detected_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of the main technical topics explicitly covered in this document. Only list topics that are actually present, do not invent.",
                },
                "total_pages": {
                    "type": "integer",
                    "description": "Total number of pages detected in the document.",
                },
                "has_code": {
                    "type": "boolean",
                    "description": "True if the document contains any code blocks or code snippets.",
                },
                "has_images": {
                    "type": "boolean",
                    "description": "True if the document contains any images, diagrams, charts, or figures.",
                },
                "has_tables": {
                    "type": "boolean",
                    "description": "True if the document contains any tables.",
                },
            },
            "required": [
                "detected_title",
                "detected_topics",
                "has_code",
                "has_images",
                "has_tables",
            ],
        },
        "sections": {
            "type": "array",
            "description": "The full document body broken into sections by heading. Each section preserves order from the source document.",
            "items": {
                "type": "object",
                "properties": {
                    "section_index": {
                        "type": "integer",
                        "description": "Sequential index of this section starting from 1.",
                    },
                    "heading": {
                        "type": "string",
                        "description": "The section heading exactly as it appears in the source. Include the heading level prefix (e.g. '## 2. Key Concepts').",
                    },
                    "heading_level": {
                        "type": "integer",
                        "description": "Heading depth: 1 for H1, 2 for H2, 3 for H3, etc.",
                    },
                    "body_text": {
                        "type": "string",
                        "description": "All paragraph and list text under this heading, in source order. Preserve formatting. Do not truncate. Do not summarize.",
                    },
                    "code_blocks": {
                        "type": "array",
                        "description": "All code blocks found within this section.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "block_index": {
                                    "type": "integer",
                                    "description": "Sequential index of this code block within the section, starting from 1.",
                                },
                                "language": {
                                    "type": "string",
                                    "description": "Programming or markup language detected (e.g. python, bash, yaml, sql, json, javascript). Use 'unknown' if not determinable.",
                                },
                                "code": {
                                    "type": "string",
                                    "description": "The full, complete code for executable or config snippets only. Do NOT put diagrams, flowcharts, mermaid, or markup syntax here — those belong in the images array. Do NOT truncate, abbreviate, or replace any part with ellipsis or placeholder text.",
                                },
                                "caption": {
                                    "type": "string",
                                    "description": "Any label, title, or caption associated with this code block in the source. Null if none.",
                                },
                                "is_reconstructed": {
                                    "type": "boolean",
                                    "description": "True if any portion of this code block was reconstructed due to a page break or rendering artifact.",
                                },
                            },
                            "required": [
                                "block_index",
                                "language",
                                "code",
                                "is_reconstructed",
                            ],
                        },
                    },
                    "images": {
                        "type": "array",
                        "description": "All images, diagrams, charts, and figures found within this section.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "image_index": {
                                    "type": "integer",
                                    "description": "Sequential index of this image within the section, starting from 1.",
                                },
                                "image_type": {
                                    "type": "string",
                                    "enum": [
                                        "architecture_diagram",
                                        "flowchart",
                                        "chart",
                                        "screenshot",
                                        "table_in_image",
                                        "illustration",
                                        "other",
                                    ],
                                    "description": "The type of visual content.",
                                },
                                "figure_label": {
                                    "type": "string",
                                    "description": "The exact figure caption or title as printed in the source (e.g. 'Figure 3: System Overview', 'Fig. Agile Model'). Use the empty string if the source has no printed caption. This is NOT a semantic name — do not invent one here.",
                                },
                                "semantic_name": {
                                    "type": "string",
                                    "description": "A short, meaningful, machine-friendly name you MUST always produce for every image, based on the nearest heading and what the image shows. Use lowercase words separated by underscores, no spaces, no punctuation, no file extension (e.g. 'waterfall_model_diagram', 'incremental_process_flow', 'agile_sprint_cycle_chart'). If several images under the same heading are similar, append a numeric suffix ('waterfall_model_diagram_1', 'waterfall_model_diagram_2'). This field is required and must never be empty.",
                                },
                                "source_page": {
                                    "type": "integer",
                                    "description": "The 1-based physical page index in the PDF file (page 1 = first page of the uploaded file). Do NOT use printed footer/header page labels such as 'Page 11' from the document body — count the actual page position in the PDF.",
                                },
                                "figure_index_on_page": {
                                    "type": "integer",
                                    "description": "When multiple distinct figures appear on the same source_page, this is their reading-order index on that page starting from 1. Use 1 when only one figure is on the page. This field is required for every image.",
                                },
                                "document_figure_index": {
                                    "type": "integer",
                                    "description": "Global reading-order index of this figure across the entire document, starting from 1 for the first figure and incrementing by 1 for each subsequent figure in the order they appear.",
                                },
                                "full_description": {
                                    "type": "string",
                                    "description": "A complete, detailed description of every element visible in the image — all components, labels, arrows, values, axis names, legend entries, annotations, and text inside the image. Write 4–8 sentences minimum. Never write just a one-line summary. This text is the sole source for teaching diagram content downstream — do not rely on diagram-as-code elsewhere.",
                                },
                                "purpose": {
                                    "type": "string",
                                    "description": "One sentence describing what concept or step this image is illustrating in context.",
                                },
                            },
                            "required": [
                                "image_index",
                                "image_type",
                                "semantic_name",
                                "source_page",
                                "figure_index_on_page",
                                "document_figure_index",
                                "full_description",
                                "purpose",
                            ],
                        },
                    },
                    "tables": {
                        "type": "array",
                        "description": "All tables found within this section.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "table_index": {
                                    "type": "integer",
                                    "description": "Sequential index of this table within the section.",
                                },
                                "caption": {
                                    "type": "string",
                                    "description": "The table title or caption from the source. Null if not present.",
                                },
                                "markdown_table": {
                                    "type": "string",
                                    "description": "The full table rendered in markdown table format. Include every row and every column. Do not collapse, merge, or omit rows.",
                                },
                            },
                            "required": ["table_index", "markdown_table"],
                        },
                    },
                },
                "required": ["section_index", "heading", "heading_level", "body_text"],
            },
        },
        "unsectioned_content": {
            "type": "string",
            "description": "Any text, code, or content that appears before the first heading or outside any detected section. Preserve fully. Null if none.",
        },
        "extraction_notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Any issues, anomalies, or reconstructions encountered during extraction. Examples: 'Code block on page 4 had a page break mid-function, reconstructed.', 'Figure 2 caption was partially cut off.' Leave empty array if no issues.",
        },
    },
    "required": ["document_metadata", "sections", "extraction_notes"],
}
