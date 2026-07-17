"""Website reduction prompt (design §10.1 / §4d union-with-dedupe)."""

WEBSITE_REDUCTION_PROMPT = """You prepare one set of dense teaching-prep notes for a teacher who will
later write the lesson. You are merging multiple sequential teaching-prep
note chunks that all came from the SAME single web page.
You are not writing the lesson, not teaching the student, and not giving a
topic overview.

Your only job is to union the chunk notes into one coherent notebook for
that page, removing only near-duplicate overlap introduced by chunk
boundaries.

Defense in depth: if CHUNK_NOTES contains only a single note (no multiple
chunks to merge), return that note unchanged as website_summary.

You must not:
- rewrite the notes into a shorter overview, abstract, or essay
- add any information not present in the chunks provided
- invent transitions, headings, structure, examples, or best practices
- change the factual meaning of any statement
- drop a unique bullet, code block, equation, date, or named entity that
  appears in only one chunk (that is not duplication)
- shorten by discarding detail in order to "compress" or "summarize"

You must:
- merge near-duplicate facts across chunk boundaries into a single, more
  complete statement (keep the fuller version)
- preserve all equations, code snippets, dates, named entities, and
  figures exactly as given in the chunks
- preserve dense bullets and short paragraphs from the input notes
- preserve the original ordering where possible

Output strict JSON, nothing else:
{"website_summary": "<string>"}
"""
