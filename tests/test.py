#!/usr/bin/env python3
# test.py
"""
Standalone map-reduce PDF summarization pipeline test for StudyGuru.

Tests whether:
  chunk LlamaParse JSON by page groups
    → summarize each chunk with a fast model
    → aggregate all summaries
    → generate final study material from aggregated summaries

...produces quality study material without hitting rate limits from oversized contexts.

Usage
-----
  # Reuse a previously logged LlamaParse JSON (no LLAMA_PARSE_API_KEY needed):
  python test.py reference.pdf --cached-json ./artifacts/topic_LlamaParse/raw_....json \\
      --topic "FastAPI Request Lifecycle"

  # Fresh LlamaParse extraction from a PDF (needs LLAMA_PARSE_API_KEY):
  python test.py reference.pdf --topic "FastAPI Request Lifecycle"

  # With a teaching instruction and custom chunk size:
  python test.py reference.pdf --cached-json log.json \\
      --topic "CI/CD with GitHub Actions" \\
      --instruction "Write for senior devs migrating from Jenkins" \\
      --pages-per-chunk 8

  # Print per-chunk summaries to stdout as they complete:
  python test.py reference.pdf --cached-json log.json --topic "Kubernetes" --print-summaries

  # Inspect the JSON structure without running the pipeline:
  python test.py reference.pdf --cached-json log.json --inspect-only

Environment
-----------
  GROQ_API_KEY            Required. Primary Groq key.
  GROQ_API_KEY_2/3/4      Optional. Used for rate-limit key rotation.
  LLAMA_PARSE_API_KEY     Required only when --cached-json is NOT provided.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# ── Optional .env loading ─────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # rely on shell-exported env vars

# ── Try importing from the project (run from project root) ───────────────────
# If these imports fail (e.g. running outside the project), we fall back to a
# standalone LLM caller that reads keys directly from env vars.
_HAS_PROJECT_LLM = False
_project_invoke_llm = None

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from src.api.utils.LLM_utils.groq_retry import (
        invoke_llm_rotating as _project_invoke_llm,  # type: ignore[assignment]
    )

    _HAS_PROJECT_LLM = True
    print("[INFO] Using project invoke_llm_rotating for LLM calls.")
except Exception as _import_err:
    print(
        f"[INFO] Project LLM not importable ({_import_err}). Using standalone caller."
    )

# ── Prompt imports ────────────────────────────────────────────────────────────
try:
    from chunk_summarizer_prompt import (
        AGGREGATE_GENERATION_SYSTEM_PROMPT,
        AGGREGATE_GENERATION_USER_TEMPLATE,
        CHUNK_SUMMARIZER_SYSTEM_PROMPT,
        CHUNK_SUMMARIZER_USER_TEMPLATE,
    )
except ImportError as _prompt_err:
    print(f"[ERROR] chunk_summarizer_prompts.py not found: {_prompt_err}")
    print("        Place chunk_summarizer_prompts.py in the same directory as test.py.")
    sys.exit(1)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_PAGES_PER_CHUNK = 10
DEFAULT_FAST_MODEL = "llama-3.1-8b-instant"  # Summarization: cheap + fast
DEFAULT_GEN_MODEL = "llama-3.3-70b-versatile"  # Final generation: high quality
CARRYOVER_CHAR_LIMIT = 600  # Tail chars passed as carryover to next chunk
OUTPUT_DIR = Path("./test_pipeline_output")
INTER_CHUNK_DELAY_SECONDS = 0.5  # Polite pause between chunk LLM calls


# ══════════════════════════════════════════════════════════════════════════════
# LLM CALLER
# Wraps project's invoke_llm_rotating when available; standalone fallback otherwise.
# ══════════════════════════════════════════════════════════════════════════════


def _get_groq_keys() -> list[str]:
    return [
        k
        for k in [
            os.getenv("GROQ_API_KEY"),
            os.getenv("GROQ_API_KEY_2"),
            os.getenv("GROQ_API_KEY_3"),
            os.getenv("GROQ_API_KEY_4"),
        ]
        if k
    ]


# ── Token counting utility ────────────────────────────────────────────────────
def get_string_tokens(text: str) -> int:
    """Estimate token count using tiktoken (cl100k_base), falling back to character division if unavailable."""
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        return len(text) // 4


async def _invoke_standalone(
    system_prompt: str,
    user_message: str,
    *,
    model: str,
    temperature: float,
    timeout: int = 120,
) -> tuple[str, dict]:
    """
    Minimal async Groq caller used when project imports are unavailable.
    Rotates through all GROQ_API_KEY_* environment variables on rate-limit errors.
    Returns a tuple of (response_content, token_usage_dict).
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_groq import ChatGroq

    keys = _get_groq_keys()
    if not keys:
        raise RuntimeError(
            "No GROQ API keys found in environment. "
            "Set GROQ_API_KEY (and optionally GROQ_API_KEY_2/3/4)."
        )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    last_exc: Exception | None = None

    for key in keys:
        try:
            llm = ChatGroq(
                model=model, api_key=key, temperature=temperature, timeout=timeout
            )
            response = await llm.ainvoke(messages)

            # Extract usage metadata
            usage = getattr(response, "usage_metadata", None) or {}
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            total_tokens = usage.get("total_tokens")

            if input_tokens is None or output_tokens is None:
                input_tokens = get_string_tokens(system_prompt + user_message)
                output_tokens = get_string_tokens(str(response.content))
                total_tokens = input_tokens + output_tokens

            return str(response.content).strip(), {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }
        except Exception as exc:
            msg = str(exc).lower()
            if (
                "429" in msg
                or "rate limit" in msg
                or "ratelimit" in msg
                or "quota" in msg
            ):
                logger.warning("Rate limit on current key — rotating: %s", exc)
                last_exc = exc
                continue
            raise  # Non-rate-limit errors are re-raised immediately

    raise last_exc or RuntimeError("All Groq API keys exhausted.")


async def call_llm(
    system_prompt: str,
    user_message: str,
    *,
    model: str,
    temperature: float = 0.3,
) -> tuple[str, dict]:
    """
    Unified LLM caller. Uses project's invoke_llm_rotating when available
    (which handles key rotation and retries), falls back to standalone caller.
    Returns a tuple of (response_content, token_usage_dict).
    """
    if _HAS_PROJECT_LLM and _project_invoke_llm is not None:
        from langchain_core.messages import HumanMessage, SystemMessage

        content, _, total_tokens = await _project_invoke_llm(
            messages=[
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ],
            model=model,
            temperature=temperature,
            timeout=120,
        )

        # Estimate input and output tokens
        input_tokens = get_string_tokens(system_prompt + user_message)
        if total_tokens is not None:
            output_tokens = max(0, total_tokens - input_tokens)
        else:
            output_tokens = get_string_tokens(content)
            total_tokens = input_tokens + output_tokens

        return content.strip(), {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    return await _invoke_standalone(
        system_prompt, user_message, model=model, temperature=temperature
    )


# ══════════════════════════════════════════════════════════════════════════════
# JSON LOADING
# ══════════════════════════════════════════════════════════════════════════════


def load_structured_json(json_path: str) -> dict:
    """
    Load a LlamaParse structured_data JSON saved by _save_llamaparse_artifact.
    Expects a dict with a top-level 'sections' key (raw LlamaCloud JSON).
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Cached JSON not found: {json_path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object at top level, got {type(data).__name__}. "
            f"Ensure you're providing the raw LlamaParse artifact "
            f"(saved by _save_llamaparse_artifact with label='raw')."
        )
    return data


def inspect_json_structure(data: dict) -> None:
    """
    Print a diagnostic overview of the JSON structure.
    Useful for debugging when sections are empty or field names differ.
    """
    print("\n" + "═" * 60)
    print("  JSON STRUCTURE DIAGNOSTIC")
    print("═" * 60)
    print(f"  Top-level keys : {list(data.keys())}")

    sections = data.get("sections") or []
    print(f"  Section count  : {len(sections)}")

    if sections:
        first = sections[0]
        print(f"  First section keys  : {list(first.keys())}")

        # Body text field detection
        body_fields = [
            f
            for f in ("body_text", "text", "content", "markdown", "extracted_text")
            if first.get(f)
        ]
        print(f"  Body text fields found : {body_fields or '[none detected]'}")

        images = first.get("images") or []
        print(f"  First section images   : {len(images)}")
        if images:
            print(f"  First image keys       : {list(images[0].keys())}")
            page_fields = [
                f
                for f in ("source_page", "page_number")
                if images[0].get(f) is not None
            ]
            print(
                f"  Page number fields     : {page_fields or '[none — will use position estimate]'}"
            )

        codes = first.get("code_blocks") or []
        print(f"  First section code blocks : {len(codes)}")

    print("═" * 60 + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# FRESH LLAMAPARSE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════


def _run_fresh_extraction_sync(pdf_path: str, topic_title: str) -> dict:
    """
    Run a fresh LlamaParse extraction synchronously.
    Called via asyncio.to_thread from main() to avoid blocking the event loop.
    Requires LLAMA_PARSE_API_KEY in environment.
    Saves the raw JSON to OUTPUT_DIR so you can reuse it with --cached-json.
    """
    api_key = os.getenv("LLAMA_PARSE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLAMA_PARSE_API_KEY environment variable not set. "
            "Either set it or use --cached-json to skip extraction."
        )

    try:
        from src.api.utils.reference_llamaparse_utils.llama_parse_extractor import (
            extract_structured_reference,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Cannot import extract_structured_reference. "
            "Run from the project root, or use --cached-json."
        ) from exc

    # Dummy UUIDs — the extractor needs them but we don't need DB for this test
    node_id = uuid4()
    material_id = uuid4()

    logger.info("Starting LlamaParse extraction: %s", pdf_path)
    logger.info("  node_id (test dummy)     : %s", node_id)
    logger.info("  material_id (test dummy) : %s", material_id)

    result = extract_structured_reference(
        pdf_path,
        api_key,
        node_id=node_id,
        reference_material_id=material_id,
        topic_title=topic_title,
        material_label=Path(pdf_path).stem,
    )

    # Save so the user can --cached-json on the next run
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = OUTPUT_DIR / f"llamaparse_raw_{stamp}.json"
    raw_path.write_text(
        json.dumps(result.structured_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Raw LlamaParse JSON saved → %s", raw_path)
    logger.info("  Re-run with: --cached-json %s", raw_path)

    return result.structured_data


# ══════════════════════════════════════════════════════════════════════════════
# SECTION CHUNKING
# ══════════════════════════════════════════════════════════════════════════════


def _section_start_page(section: dict) -> int | None:
    """Infer the starting page of a section from its image metadata."""
    pages = []
    for image in section.get("images") or []:
        for field in ("source_page", "page_number"):
            val = image.get(field)
            if val is not None:
                try:
                    pages.append(int(val))
                except (ValueError, TypeError):
                    pass
                break
    return min(pages) if pages else None


def _section_end_page(section: dict) -> int | None:
    """Infer the ending page of a section from its image metadata."""
    pages = []
    for image in section.get("images") or []:
        for field in ("source_page", "page_number"):
            val = image.get(field)
            if val is not None:
                try:
                    pages.append(int(val))
                except (ValueError, TypeError):
                    pass
                break
    return max(pages) if pages else None


def chunk_sections_by_pages(
    sections: list[dict],
    pages_per_chunk: int = DEFAULT_PAGES_PER_CHUNK,
) -> list[dict]:
    """
    Group sections into chunks spanning approximately pages_per_chunk pages.

    Page numbers are inferred from image metadata (source_page / page_number).
    For sections with no image metadata, position is estimated sequentially
    (each section counted as ~1 page). This fallback is safe — chunking is
    approximate and the summarizer sees complete sections regardless.

    Returns a list of chunk dicts:
      chunk_index   : 1-based index
      total_chunks  : total number of chunks
      sections      : list of section dicts in this chunk
      page_start    : first estimated page in chunk
      page_end      : last estimated page in chunk
      page_range    : human-readable string e.g. "pages 1–10"
    """
    if not sections:
        return []

    # Assign an estimated page to each section
    indexed: list[tuple[dict, int]] = []
    cursor = 1
    for sec in sections:
        start = _section_start_page(sec)
        if start is not None:
            indexed.append((sec, start))
            end = _section_end_page(sec)
            cursor = (end or start) + 1
        else:
            indexed.append((sec, cursor))
            cursor += 1

    # Group by page window
    chunks_raw: list[tuple[list[dict], int, int]] = []
    current_secs: list[dict] = []
    chunk_fp = indexed[0][1]
    chunk_lp = indexed[0][1]

    for sec, page in indexed:
        if current_secs and (page - chunk_fp) >= pages_per_chunk:
            chunks_raw.append((list(current_secs), chunk_fp, chunk_lp))
            current_secs = [sec]
            chunk_fp = page
            chunk_lp = page
        else:
            current_secs.append(sec)
            chunk_lp = max(chunk_lp, page)

    if current_secs:
        chunks_raw.append((list(current_secs), chunk_fp, chunk_lp))

    total = len(chunks_raw)
    return [
        {
            "chunk_index": i + 1,
            "total_chunks": total,
            "sections": secs,
            "page_start": fp,
            "page_end": lp,
            "page_range": f"page {fp}" if fp == lp else f"pages {fp}–{lp}",
        }
        for i, (secs, fp, lp) in enumerate(chunks_raw)
    ]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION → TEXT CONVERSION
# Converts structured section dicts into readable markdown for the summarizer.
# ══════════════════════════════════════════════════════════════════════════════


def _section_body_text(section: dict) -> str:
    """Extract the main text body from a section, trying multiple likely field names."""
    for field in (
        "body_text",
        "text",
        "content",
        "markdown",
        "extracted_text",
        "raw_text",
    ):
        val = section.get(field)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _section_code_blocks(section: dict) -> list[dict]:
    """Extract code blocks from a section, trying multiple likely field names."""
    for field in ("code_blocks", "code", "snippets", "examples"):
        val = section.get(field)
        if val and isinstance(val, list):
            return val
    return []


def sections_to_text(sections: list[dict]) -> str:
    """
    Convert a list of section dicts to readable markdown text.
    Handles headings, body text, [FIGURE: ...] blocks from image metadata,
    and fenced code blocks.

    This is the input the chunk summarizer LLM receives.
    """
    parts: list[str] = []

    for section in sections:
        heading = (section.get("heading") or section.get("title") or "").strip()
        if heading:
            parts.append(f"\n## {heading}\n")

        body = _section_body_text(section)
        if body:
            parts.append(body)

        # Emit [FIGURE: ...] blocks that the summarizer prompt instructs the LLM
        # to enumerate with Components / Connections / Purpose.
        for image in section.get("images") or []:
            figure_label = (image.get("figure_label") or "").strip()
            semantic_name = (image.get("semantic_name") or "").strip()
            full_description = (
                image.get("full_description") or image.get("description") or ""
            ).strip()
            caption = figure_label or semantic_name or "Figure"

            if full_description:
                parts.append(f"\n[FIGURE: {caption}]")
                parts.append(full_description)
                parts.append("")

        # Code blocks
        for cb in _section_code_blocks(section):
            lang = cb.get("language") or cb.get("lang") or ""
            code = (cb.get("content") or cb.get("code") or cb.get("text") or "").strip()
            if code:
                parts.append(f"\n```{lang}")
                parts.append(code)
                parts.append("```\n")

    result = "\n".join(parts).strip()
    return result


def get_carryover_tail(raw_text: str) -> str:
    """
    Return the tail of the previous chunk's raw text as carryover context.
    Attempts to align the cut to a paragraph boundary so the carryover
    starts at a natural point rather than mid-sentence.
    """
    if not raw_text:
        return "[No previous content — this is the first chunk.]"

    if len(raw_text) <= CARRYOVER_CHAR_LIMIT:
        return raw_text

    tail = raw_text[-CARRYOVER_CHAR_LIMIT:]

    # Try to start at a newline so we don't begin mid-sentence
    newline_idx = tail.find("\n")
    if 0 < newline_idx < CARRYOVER_CHAR_LIMIT // 2:
        tail = tail[newline_idx:].strip()

    return f"[...excerpt from end of previous chunk...]\n\n{tail}"


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ══════════════════════════════════════════════════════════════════════════════


async def run_pipeline(
    structured_data: dict,
    *,
    topic_title: str,
    teaching_instruction: str,
    pages_per_chunk: int,
    fast_model: str,
    gen_model: str,
    print_summaries: bool = False,
) -> dict:
    """
    Full map-reduce pipeline:
      1. Chunk sections by page group
      2. Summarize each chunk sequentially with the fast model
      3. Aggregate all summaries into one block
      4. Generate final study material with the full model

    Returns a results dict containing all intermediate and final outputs.
    """
    sections = structured_data.get("sections") or []
    if not sections:
        raise ValueError(
            "No 'sections' key found in structured_data (or it is empty). "
            "Run --inspect-only to diagnose the JSON structure."
        )

    logger.info("Document sections: %d total", len(sections))

    # ── Step 1: Chunk ─────────────────────────────────────────────────────────
    chunks = chunk_sections_by_pages(sections, pages_per_chunk=pages_per_chunk)
    logger.info(
        "Chunked into %d groups (~%d pages each):", len(chunks), pages_per_chunk
    )
    for c in chunks:
        logger.info(
            "  Chunk %d/%d — %d section(s) | %s",
            c["chunk_index"],
            c["total_chunks"],
            len(c["sections"]),
            c["page_range"],
        )

    # ── Step 2: Summarize each chunk ──────────────────────────────────────────
    summaries: list[dict] = []
    previous_raw_text = ""

    for chunk in chunks:
        idx = chunk["chunk_index"]
        total = chunk["total_chunks"]

        logger.info("Summarizing chunk %d/%d (%s)...", idx, total, chunk["page_range"])

        chunk_text = sections_to_text(chunk["sections"])

        if not chunk_text.strip():
            logger.warning(
                "  Chunk %d produced no extractable text — skipping. "
                "Check whether sections have body_text / text / content fields.",
                idx,
            )
            summaries.append(
                {
                    "chunk_index": idx,
                    "page_range": chunk["page_range"],
                    "summary": "[EMPTY CHUNK — no text extracted from sections]",
                    "raw_text": "",
                }
            )
            previous_raw_text = ""
            continue

        carryover = get_carryover_tail(previous_raw_text)

        user_msg = CHUNK_SUMMARIZER_USER_TEMPLATE.format(
            chunk_index=idx,
            total_chunks=total,
            page_range=chunk["page_range"],
            carryover_context=carryover,
            chunk_content=chunk_text,
        )

        try:
            summary, usage = await call_llm(
                CHUNK_SUMMARIZER_SYSTEM_PROMPT,
                user_msg,
                model=fast_model,
                temperature=0.2,
            )
        except Exception as exc:
            logger.error("  Chunk %d summarization failed: %s", idx, exc)
            summary = f"[SUMMARIZATION FAILED for chunk {idx}: {exc}]"
            usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        # Split input tokens into prompt tokens and reference material tokens
        ref_material_tokens = get_string_tokens(chunk_text) + (
            get_string_tokens(carryover) if carryover else 0
        )
        total_in = usage.get("input_tokens", 0)
        prompt_tokens = max(0, total_in - ref_material_tokens)
        usage["prompt_tokens"] = prompt_tokens
        usage["ref_material_tokens"] = ref_material_tokens

        word_count = len(summary.split())
        logger.info("  ✓ Chunk %d summarized (~%d words output)", idx, word_count)

        if print_summaries:
            print(f"\n{'─' * 60}")
            print(f"  Chunk {idx}/{total} Summary | {chunk['page_range']}")
            print(f"{'─' * 60}")
            print(summary)

        summaries.append(
            {
                "chunk_index": idx,
                "page_range": chunk["page_range"],
                "summary": summary,
                "raw_text": chunk_text,
                "token_usage": usage,
            }
        )

        previous_raw_text = chunk_text

        # Brief pause to respect rate limits between chunk calls
        if idx < total:
            await asyncio.sleep(INTER_CHUNK_DELAY_SECONDS)

    # ── Step 3: Aggregate summaries ───────────────────────────────────────────
    aggregated = _build_aggregated_block(summaries)
    agg_words = len(aggregated.split())
    logger.info(
        "Aggregated %d summaries → %d words (this is what goes into final generation)",
        len(summaries),
        agg_words,
    )

    # ── Step 4: Final generation ──────────────────────────────────────────────
    effective_instruction = teaching_instruction.strip() or (
        "No specific instruction provided. "
        "Write for a new IT hire with basic programming knowledge "
        "who is unfamiliar with this specific topic."
    )

    gen_user_msg = AGGREGATE_GENERATION_USER_TEMPLATE.format(
        topic_title=topic_title,
        teaching_instruction=effective_instruction,
        all_summaries=aggregated,
    )

    logger.info("Generating final study material with %s...", gen_model)

    final_content, gen_usage = await call_llm(
        AGGREGATE_GENERATION_SYSTEM_PROMPT,
        gen_user_msg,
        model=gen_model,
        temperature=0.3,
    )

    logger.info("✓ Study material generated (~%d words)", len(final_content.split()))

    raw_json_str = json.dumps(structured_data, ensure_ascii=False)
    raw_json_tokens = get_string_tokens(raw_json_str)
    aggregated_summaries_tokens = get_string_tokens(aggregated)
    final_input_tokens = gen_usage.get("input_tokens", 0)

    # Split final generation input tokens
    final_prompt_tokens = max(0, final_input_tokens - aggregated_summaries_tokens)
    gen_usage["prompt_tokens"] = final_prompt_tokens
    gen_usage["ref_material_tokens"] = aggregated_summaries_tokens

    return {
        "topic_title": topic_title,
        "total_chunks": len(summaries),
        "pages_per_chunk": pages_per_chunk,
        "fast_model": fast_model,
        "gen_model": gen_model,
        "summaries": summaries,
        "aggregated_summaries": aggregated,
        "final_content": final_content,
        "token_metrics": {
            "raw_json_tokens": raw_json_tokens,
            "aggregated_summaries_tokens": aggregated_summaries_tokens,
            "final_input_tokens": final_input_tokens,
            "chunk_summaries_tokens": [item["token_usage"] for item in summaries],
            "final_generation_tokens": gen_usage,
        },
    }


def _build_aggregated_block(summaries: list[dict]) -> str:
    """
    Concatenate all chunk summaries with clear separators.
    The separators help the final generator track which summary covers which pages
    and follow CONTINUED / CONTINUES INTO NEXT SECTION markers across boundaries.
    """
    parts: list[str] = []
    for item in summaries:
        parts.append(
            f"{'=' * 60}\n"
            f"CHUNK {item['chunk_index']} SUMMARY | {item['page_range']}\n"
            f"{'=' * 60}\n"
        )
        parts.append(item["summary"].strip())
        parts.append("\n")
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# OUTPUT SAVING
# ══════════════════════════════════════════════════════════════════════════════


def save_results(results: dict) -> Path:
    """
    Save all pipeline outputs under OUTPUT_DIR/<topic>_<timestamp>/.

    Directory layout:
      chunk_summaries/chunk_NNN.md  — per-chunk summary (what the fast model produced)
      aggregated_summaries.md       — what was fed into the final generation step
      study_material.md             — final study material output
      run_metadata.json             — run configuration for reproducibility
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in results["topic_title"]
    )[:40]
    run_dir = OUTPUT_DIR / f"{safe}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Per-chunk summaries
    chunk_dir = run_dir / "chunk_summaries"
    chunk_dir.mkdir()
    for item in results["summaries"]:
        f = chunk_dir / f"chunk_{item['chunk_index']:03d}.md"
        f.write_text(
            f"# Chunk {item['chunk_index']} | {item['page_range']}\n\n{item['summary']}",
            encoding="utf-8",
        )

    # Aggregated summaries (the actual input to the final LLM call)
    (run_dir / "aggregated_summaries.md").write_text(
        results["aggregated_summaries"], encoding="utf-8"
    )

    # Final study material
    (run_dir / "study_material.md").write_text(
        results["final_content"], encoding="utf-8"
    )

    # Run metadata
    meta = {
        k: v
        for k, v in results.items()
        if k not in ("summaries", "aggregated_summaries", "final_content")
    }
    meta["timestamp"] = stamp
    meta["chunk_count"] = results["total_chunks"]
    (run_dir / "run_metadata.json").write_text(
        json.dumps(meta, indent=2, default=str), encoding="utf-8"
    )

    return run_dir


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            Test the StudyGuru map-reduce PDF summarization pipeline.
            Chunks a LlamaParse JSON by page groups, summarizes each chunk
            with a fast model, then generates study material from the aggregated summaries.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pdf_path",
        help="Path to the reference PDF. Used for fresh extraction, or just for context when --cached-json is provided.",
    )
    parser.add_argument(
        "--cached-json",
        metavar="PATH",
        help=(
            "Path to a previously saved LlamaParse JSON "
            "(the 'raw' artifact from _save_llamaparse_artifact). "
            "When provided, skips LlamaParse extraction entirely — no LLAMA_PARSE_API_KEY needed."
        ),
    )
    parser.add_argument(
        "--topic",
        default="Unknown Topic",
        metavar="TITLE",
        help="Topic title for study material generation. Default: 'Unknown Topic'",
    )
    parser.add_argument(
        "--instruction",
        default="",
        metavar="TEXT",
        help="Teaching instruction for the final generator. Defaults to new IT hire audience.",
    )
    parser.add_argument(
        "--pages-per-chunk",
        type=int,
        default=DEFAULT_PAGES_PER_CHUNK,
        metavar="N",
        help=f"Pages per chunk for the map step. Default: {DEFAULT_PAGES_PER_CHUNK}",
    )
    parser.add_argument(
        "--fast-model",
        default=DEFAULT_FAST_MODEL,
        metavar="MODEL",
        help=f"Groq model for chunk summarization. Default: {DEFAULT_FAST_MODEL}",
    )
    parser.add_argument(
        "--gen-model",
        default=DEFAULT_GEN_MODEL,
        metavar="MODEL",
        help=f"Groq model for final generation. Default: {DEFAULT_GEN_MODEL}",
    )
    parser.add_argument(
        "--print-summaries",
        action="store_true",
        help="Print each chunk summary to stdout as it completes.",
    )
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Load the JSON and print its structure, then exit without running the pipeline.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Skip saving outputs to disk.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # ── Load or extract structured JSON ───────────────────────────────────────
    if args.cached_json:
        logger.info("Loading cached JSON: %s", args.cached_json)
        structured_data = load_structured_json(args.cached_json)
    else:
        logger.info("No --cached-json provided. Running fresh LlamaParse extraction.")
        structured_data = await asyncio.to_thread(
            _run_fresh_extraction_sync, args.pdf_path, args.topic
        )

    # ── Inspect-only mode ─────────────────────────────────────────────────────
    if args.inspect_only:
        inspect_json_structure(structured_data)
        return

    inspect_json_structure(structured_data)  # Always print diagnostic before running

    # ── Pipeline header ───────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  StudyGuru Map-Reduce Summarization Pipeline Test")
    print(f"  Topic          : {args.topic}")
    print(f"  Pages per chunk: {args.pages_per_chunk}")
    print(f"  Fast model     : {args.fast_model}  (chunk summarization)")
    print(f"  Gen model      : {args.gen_model}  (final generation)")
    print("═" * 70 + "\n")

    # ── Run pipeline ──────────────────────────────────────────────────────────
    results = await run_pipeline(
        structured_data,
        topic_title=args.topic,
        teaching_instruction=args.instruction,
        pages_per_chunk=args.pages_per_chunk,
        fast_model=args.fast_model,
        gen_model=args.gen_model,
        print_summaries=args.print_summaries,
    )

    # ── Print final result ────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  FINAL STUDY MATERIAL")
    print("═" * 70 + "\n")
    print(results["final_content"])

    # ── Print token usage and efficiency report ───────────────────────────────
    metrics = results.get("token_metrics", {})
    if metrics:
        print("\n" + "═" * 70)
        print("  TOKEN USAGE & EFFICIENCY REPORT")
        print("═" * 70)

        raw_json_tokens = metrics.get("raw_json_tokens", 0)
        agg_tokens = metrics.get("aggregated_summaries_tokens", 0)
        metrics.get("final_input_tokens", 0)

        print(f"  Raw LlamaParse JSON   : {raw_json_tokens:,} tokens")
        print(f"  Aggregated Summaries : {agg_tokens:,} tokens")

        # Calculate context reduction
        if raw_json_tokens > 0:
            reduction = (1 - (agg_tokens / raw_json_tokens)) * 100
            print(
                f"  Context size reduced  : {reduction:.1f}% smaller context for final model"
            )
        else:
            print("  Context size reduced  : N/A")

        print("\n  1) Chunk Summarization (8B Model):")
        total_summarizer_tokens = 0
        for i, item in enumerate(metrics.get("chunk_summaries_tokens", [])):
            inp = item.get("input_tokens", 0)
            out = item.get("output_tokens", 0)
            tot = item.get("total_tokens", 0)
            p_in = item.get("prompt_tokens", 0)
            c_in = item.get("ref_material_tokens", 0)
            total_summarizer_tokens += tot
            print(
                f"    - Chunk {i + 1:02d} (pages approx): {tot:,} tokens (In: {inp:,} [Prompt: {p_in:,} | Content: {c_in:,}] | Out: {out:,})"
            )
        print(f"    * Total summarizer tokens: {total_summarizer_tokens:,} tokens")

        print("\n  2) Final Study Material Generation (70B Model):")
        gen_tokens = metrics.get("final_generation_tokens", {})
        gen_in = gen_tokens.get("input_tokens", 0)
        gen_out = gen_tokens.get("output_tokens", 0)
        gen_tot = gen_tokens.get("total_tokens", 0)
        p_in = gen_tokens.get("prompt_tokens", 0)
        c_in = gen_tokens.get("ref_material_tokens", 0)
        print(
            f"    - Input tokens passed : {gen_in:,} tokens [Prompt: {p_in:,} | Summaries Content: {c_in:,}]"
        )
        print(f"    - Output tokens gen   : {gen_out:,} tokens")
        print(f"    - Total gen tokens    : {gen_tot:,} tokens")

        total_pipeline_tokens = total_summarizer_tokens + gen_tot
        print("\n  3) Overall Efficiency Summary:")
        print(
            f"    - Total tokens consumed across pipeline: {total_pipeline_tokens:,} tokens"
        )
        print("═" * 70 + "\n")

    # ── Save outputs ──────────────────────────────────────────────────────────
    if not args.no_save:
        run_dir = save_results(results)
        print(f"\n{'═' * 70}")
        print(f"  Outputs saved → {run_dir}")
        print("    chunk_summaries/      per-chunk summaries (fast model output)")
        print("    aggregated_summaries.md  input to final generation step")
        print("    study_material.md        final generated content")
        print("    run_metadata.json        run config for reproducibility")
        print("═" * 70)


if __name__ == "__main__":
    asyncio.run(main())
