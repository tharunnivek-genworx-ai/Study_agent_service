#!/usr/bin/env python3
# test.py
"""
Standalone HIERARCHICAL map-reduce PDF summarization pipeline test for StudyGuru.

Flow (NEW vs OLD):
  OLD: chunk by pages → summarize each chunk (fast model) → concat all → one 70B call
  NEW: chunk by pages → sub-chunk by tokens → summarize sub-chunks (fast model)
         → merge sub-chunk summaries per page-chunk (fast model)
         → hierarchical reduce (batched 70B calls, possibly multi-level)
         → final study material generation (70B, from single master outline)

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

  # Tune token budgets:
  python test.py reference.pdf --cached-json log.json --topic "X" \\
      --max-subchunk-tokens 600 --max-reduce-batch-tokens 3500

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
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# ── Optional .env loading ─────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # rely on shell-exported env vars

# ── Try importing from the project (run from project root) ───────────────────
_HAS_PROJECT_LLM = False
_project_invoke_llm: Any = None

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from src.api.utils.LLM_utils.groq_retry import (
        invoke_llm_rotating as _project_invoke_llm,
    )

    _HAS_PROJECT_LLM = True
    print("[INFO] Using project invoke_llm_rotating for LLM calls.")
except Exception as _import_err:
    print(
        f"[INFO] Project LLM not importable ({_import_err}). Using standalone caller."
    )

# ── Prompt imports ────────────────────────────────────────────────────────────
from hierarchical_prompt import (  # noqa: E402
    FINAL_GENERATION_SYSTEM_PROMPT,
    FINAL_GENERATION_USER_TEMPLATE,
    PAGE_CHUNK_MERGE_SYSTEM_PROMPT,
    PAGE_CHUNK_MERGE_USER_TEMPLATE,
    REDUCE_MERGE_SYSTEM_PROMPT,
    REDUCE_MERGE_USER_TEMPLATE,
    SUBCHUNK_SUMMARIZER_SYSTEM_PROMPT,
    SUBCHUNK_SUMMARIZER_USER_TEMPLATE,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ── Tuning guide ──────────────────────────────────────────────────────────────
#
# MAX_TOKENS_PER_SUBCHUNK_INPUT (~500–800):
#   Controls how many tokens of body text go into a single sub-chunk before we
#   split. Lower = more LLM calls but safer for free-tier RPM limits.
#   Higher = fewer calls but may produce less detailed sub-summaries.
#
# MAX_TOKENS_PER_PAGE_SUMMARY_INPUT (~2000–4000):
#   When merging sub-chunk summaries for a page-chunk, this is the max combined
#   token budget for the merge prompt. If sub-summaries exceed this, they are
#   truncated (rare in practice since each sub-summary is small).
#
# MAX_TOKENS_PER_BATCH_REDUCE_INPUT (~3000–5000):
#   How many tokens of page-chunk summaries to pass into each reduce batch call.
#   Keep under ~4000 for free-tier 70B to avoid TPM limits.
#
# MAX_REDUCE_BATCH_SIZE (3–6):
#   Max number of page-chunk summaries per reduce batch, as an item-count guard
#   in addition to the token guard above. Whichever limit is hit first splits.
#
# To inspect whether budgets are working: watch [SUBCHUNK], [MERGE], [REDUCE Lx]
# log lines. If you see "tokens ~= X" values near or above the limits, lower them.
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_PAGES_PER_CHUNK = 10
DEFAULT_FAST_MODEL = "llama-3.1-8b-instant"  # sub-chunk summarizer + merge
DEFAULT_GEN_MODEL = "llama-3.3-70b-versatile"  # reduce + final generation
CARRYOVER_CHAR_LIMIT = 600
OUTPUT_DIR = Path("./test_pipeline_output")
INTER_CHUNK_DELAY_SECONDS = 0.5
INTER_SUBCHUNK_DELAY_SECONDS = 0.3  # polite pause between sub-chunk calls

# Token budget constants — override via CLI flags --max-subchunk-tokens / --max-reduce-batch-tokens
DEFAULT_MAX_TOKENS_PER_SUBCHUNK_INPUT = 700  # body text tokens per sub-chunk
DEFAULT_MAX_TOKENS_PER_PAGE_SUMMARY_INPUT = 3000  # merge prompt total input budget
DEFAULT_MAX_TOKENS_PER_BATCH_REDUCE_INPUT = 4000  # reduce batch input budget
DEFAULT_MAX_REDUCE_BATCH_SIZE = 5  # max summaries per reduce batch


# ══════════════════════════════════════════════════════════════════════════════
# LLM CALLER
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
    """Estimate token count using tiktoken (cl100k_base), falling back to char/4."""
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
                model=model,
                api_key=key,
                temperature=temperature,
                timeout=timeout,
            )  # type: ignore[call-arg]
            response = await llm.ainvoke(messages)
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
            raise

    raise last_exc or RuntimeError("All Groq API keys exhausted.")


async def call_llm(
    system_prompt: str,
    user_message: str,
    *,
    model: str,
    temperature: float = 0.3,
) -> tuple[str, dict]:
    """
    Unified LLM caller. Uses project's invoke_llm_rotating when available,
    falls back to standalone caller.
    Returns (response_content, token_usage_dict).
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
    """Load a LlamaParse structured_data JSON. Expects a dict with 'sections' key."""
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Cached JSON not found: {json_path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object at top level, got {type(data).__name__}. "
            "Ensure you're providing the raw LlamaParse artifact."
        )
    return data


def inspect_json_structure(data: dict) -> None:
    """Print a diagnostic overview of the JSON structure."""
    print("\n" + "═" * 60)
    print("  JSON STRUCTURE DIAGNOSTIC")
    print("═" * 60)
    print(f"  Top-level keys : {list(data.keys())}")
    sections = data.get("sections") or []
    print(f"  Section count  : {len(sections)}")
    if sections:
        first = sections[0]
        print(f"  First section keys  : {list(first.keys())}")
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
    """Run a fresh LlamaParse extraction synchronously."""
    api_key = os.getenv("LLAMA_PARSE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLAMA_PARSE_API_KEY environment variable not set. "
            "Either set it or use --cached-json to skip extraction."
        )
    try:
        from src.api.control.study_agent.utils.parsing.llama_parse_extractor import (
            extract_structured_reference,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Cannot import extract_structured_reference. "
            "Run from the project root, or use --cached-json."
        ) from exc

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
# SECTION CHUNKING (UNCHANGED FROM ORIGINAL)
# ══════════════════════════════════════════════════════════════════════════════


def _section_start_page(section: dict) -> int | None:
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
    Returns list of chunk dicts with chunk_index, total_chunks, sections,
    page_start, page_end, page_range.
    """
    if not sections:
        return []

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
# SECTION → TEXT CONVERSION (UNCHANGED FROM ORIGINAL)
# ══════════════════════════════════════════════════════════════════════════════


def _section_body_text(section: dict) -> str:
    """Extract main body text from a section, trying multiple field names."""
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
    """Extract code blocks from a section."""
    for field in ("code_blocks", "code", "snippets", "examples"):
        val = section.get(field)
        if val and isinstance(val, list):
            return val
    return []


def sections_to_text(sections: list[dict]) -> str:
    """Convert a list of section dicts to readable markdown text."""
    parts: list[str] = []
    for section in sections:
        heading = (section.get("heading") or section.get("title") or "").strip()
        if heading:
            parts.append(f"\n## {heading}\n")
        body = _section_body_text(section)
        if body:
            parts.append(body)
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
        for cb in _section_code_blocks(section):
            lang = cb.get("language") or cb.get("lang") or ""
            code = (cb.get("content") or cb.get("code") or cb.get("text") or "").strip()
            if code:
                parts.append(f"\n```{lang}")
                parts.append(code)
                parts.append("```\n")
    return "\n".join(parts).strip()


def get_carryover_tail(raw_text: str) -> str:
    """Return tail of the previous chunk's raw text as carryover context."""
    if not raw_text:
        return "[No previous content — this is the first chunk.]"
    if len(raw_text) <= CARRYOVER_CHAR_LIMIT:
        return raw_text
    tail = raw_text[-CARRYOVER_CHAR_LIMIT:]
    newline_idx = tail.find("\n")
    if 0 < newline_idx < CARRYOVER_CHAR_LIMIT // 2:
        tail = tail[newline_idx:].strip()
    return f"[...excerpt from end of previous chunk...]\n\n{tail}"


# ══════════════════════════════════════════════════════════════════════════════
# NEW: TOKEN-BASED SUB-CHUNKING
# Splits a body text string into semantic sub-chunks within a token budget.
# ══════════════════════════════════════════════════════════════════════════════


def split_text_into_subchunks(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS_PER_SUBCHUNK_INPUT,
) -> list[str]:
    """
    Split body text into semantic sub-chunks, each within max_tokens.

    Strategy (in order of preference):
      1. Split on double newlines (paragraph boundaries) — cleanest splits.
      2. If a paragraph is still too long, split on headings (## / ### lines).
      3. If still too long, split on single newlines.
      4. If still too long, split on sentence boundaries (. / ! / ?).

    Accumulates units until the token budget is about to be exceeded,
    then starts a new sub-chunk.

    How to tune:
      - Larger max_tokens → fewer, richer sub-chunks, but risks TPM limits.
      - Smaller max_tokens → more sub-chunks, safer for free tier, but more LLM calls.
    """
    if not text.strip():
        return []

    # Step 1: split into paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    # Step 2: further split any paragraph that is itself over budget
    units: list[str] = []
    for para in paragraphs:
        if get_string_tokens(para) <= max_tokens:
            units.append(para)
        else:
            # Try heading splits
            heading_parts = re.split(r"(?m)^(#{1,3} .+)$", para)
            heading_parts = [p.strip() for p in heading_parts if p.strip()]
            sub_units: list[str] = []
            for hp in heading_parts:
                if get_string_tokens(hp) <= max_tokens:
                    sub_units.append(hp)
                else:
                    # Try single-newline splits
                    line_parts = [ln.strip() for ln in hp.split("\n") if ln.strip()]
                    current_lines: list[str] = []
                    current_tokens = 0
                    for line in line_parts:
                        lt = get_string_tokens(line)
                        if current_tokens + lt > max_tokens and current_lines:
                            sub_units.append("\n".join(current_lines))
                            current_lines = [line]
                            current_tokens = lt
                        else:
                            current_lines.append(line)
                            current_tokens += lt
                    if current_lines:
                        sub_units.append("\n".join(current_lines))
            units.extend(sub_units)

    # Step 3: accumulate units into sub-chunks within the token budget
    subchunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for unit in units:
        unit_tokens = get_string_tokens(unit)
        if current_parts and current_tokens + unit_tokens > max_tokens:
            # Flush current sub-chunk
            subchunks.append("\n\n".join(current_parts))
            current_parts = [unit]
            current_tokens = unit_tokens
        else:
            current_parts.append(unit)
            current_tokens += unit_tokens

    if current_parts:
        subchunks.append("\n\n".join(current_parts))

    return subchunks


# ══════════════════════════════════════════════════════════════════════════════
# NEW: HIERARCHICAL REDUCE BATCHING
# Batches page-chunk summaries for multi-level reduce.
# ══════════════════════════════════════════════════════════════════════════════


def batch_summaries_for_reduce(
    summaries: list[str],
    max_items_per_batch: int = DEFAULT_MAX_REDUCE_BATCH_SIZE,
    max_tokens_per_batch: int = DEFAULT_MAX_TOKENS_PER_BATCH_REDUCE_INPUT,
) -> list[list[str]]:
    """
    Group a list of summary strings into batches for a reduce step.
    Respects BOTH a max item count AND a max token budget per batch.
    Whichever limit is hit first causes a new batch to start.

    How to inspect: after calling this, log len(batches) and sum token sizes.
    If batches are all size 1, your max_tokens_per_batch is too small relative
    to your summary sizes — either increase it or reduce MAX_TOKENS_PER_SUBCHUNK_INPUT
    to produce smaller per-chunk summaries.
    """
    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_tokens = 0

    for summary in summaries:
        st = get_string_tokens(summary)
        if current_batch and (
            len(current_batch) >= max_items_per_batch
            or current_tokens + st > max_tokens_per_batch
        ):
            batches.append(current_batch)
            current_batch = [summary]
            current_tokens = st
        else:
            current_batch.append(summary)
            current_tokens += st

    if current_batch:
        batches.append(current_batch)

    return batches


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE (REFACTORED — HIERARCHICAL)
# ══════════════════════════════════════════════════════════════════════════════


async def _summarize_subchunk(
    subchunk_text: str,
    subchunk_index: int,
    total_subchunks: int,
    page_range: str,
    fast_model: str,
) -> tuple[str, dict]:
    """
    Summarize a single sub-chunk with the fast model.
    Returns (summary_text, token_usage_dict).
    [NEW] This is the innermost summarization step — replaces direct chunk summarization.
    """
    user_msg = SUBCHUNK_SUMMARIZER_USER_TEMPLATE.format(
        page_range=page_range,
        subchunk_index=subchunk_index,
        total_subchunks=total_subchunks,
        subchunk_text=subchunk_text,
    )
    approx_input = get_string_tokens(SUBCHUNK_SUMMARIZER_SYSTEM_PROMPT + user_msg)
    logger.info(
        "  [SUBCHUNK %d/%d] page_range=%s approx_input_tokens~=%d",
        subchunk_index,
        total_subchunks,
        page_range,
        approx_input,
    )
    summary, usage = await call_llm(
        SUBCHUNK_SUMMARIZER_SYSTEM_PROMPT,
        user_msg,
        model=fast_model,
        temperature=0.2,
    )
    approx_output = get_string_tokens(summary)
    logger.info(
        "  [SUBCHUNK %d/%d] done — output~=%d tokens (%d words)",
        subchunk_index,
        total_subchunks,
        approx_output,
        len(summary.split()),
    )
    return summary, usage


async def _merge_subchunk_summaries(
    subchunk_summaries: list[str],
    page_range: str,
    fast_model: str,
    max_input_tokens: int = DEFAULT_MAX_TOKENS_PER_PAGE_SUMMARY_INPUT,
) -> tuple[str, dict]:
    """
    Merge all sub-chunk summaries for a page-chunk into one coherent summary.
    [NEW] This is the page-chunk-level merge step — produces the "page-chunk summary"
    that used to be produced by a direct chunk summarization call.

    If sub-summaries combined exceed max_input_tokens, later ones are truncated
    to keep the merge prompt within budget (log a warning if this happens).
    """
    # Build the sub-summaries block, respecting token budget
    parts: list[str] = []
    running_tokens = 0
    for i, s in enumerate(subchunk_summaries):
        header = f"--- Sub-chunk {i + 1}/{len(subchunk_summaries)} ---\n"
        block = header + s.strip()
        bt = get_string_tokens(block)
        if running_tokens + bt > max_input_tokens:
            logger.warning(
                "  [MERGE] Sub-summary budget exceeded at sub-chunk %d/%d "
                "(used %d / %d tokens). Truncating remaining.",
                i + 1,
                len(subchunk_summaries),
                running_tokens,
                max_input_tokens,
            )
            break
        parts.append(block)
        running_tokens += bt

    sub_summaries_block = "\n\n".join(parts)
    approx_input = get_string_tokens(
        PAGE_CHUNK_MERGE_SYSTEM_PROMPT
        + PAGE_CHUNK_MERGE_USER_TEMPLATE.format(
            page_range=page_range, sub_summaries_block=sub_summaries_block
        )
    )
    logger.info(
        "  [MERGE] Merging %d sub-summaries for %s — approx_input_tokens~=%d",
        len(subchunk_summaries),
        page_range,
        approx_input,
    )

    user_msg = PAGE_CHUNK_MERGE_USER_TEMPLATE.format(
        page_range=page_range,
        sub_summaries_block=sub_summaries_block,
    )
    merged, usage = await call_llm(
        PAGE_CHUNK_MERGE_SYSTEM_PROMPT,
        user_msg,
        model=fast_model,
        temperature=0.2,
    )
    approx_output = get_string_tokens(merged)
    logger.info(
        "  [MERGE] Done for %s — output~=%d tokens (%d words)",
        page_range,
        approx_output,
        len(merged.split()),
    )
    return merged, usage


async def _hierarchical_reduce(
    page_chunk_summaries: list[str],
    page_ranges: list[str],
    gen_model: str,
    max_batch_size: int = DEFAULT_MAX_REDUCE_BATCH_SIZE,
    max_batch_tokens: int = DEFAULT_MAX_TOKENS_PER_BATCH_REDUCE_INPUT,
) -> tuple[str, list[dict]]:
    """
    Hierarchically reduce page-chunk summaries to a single master outline.
    [NEW] Replaces the old _build_aggregated_block + single 70B call approach.

    How it works:
      Level 1: batch all page-chunk summaries → call 70B per batch → mid-level outlines
      Level 2: if >1 mid-level outline, batch those → call 70B per batch → higher outlines
      Repeat until only 1 summary remains — that is the master outline.

    Logs: [REDUCE Lx BATCH y/z] prefix for each LLM call, with token sizes.

    Returns: (master_outline_text, list_of_reduce_metrics_dicts)
    """
    current_summaries = list(page_chunk_summaries)
    current_labels = list(page_ranges)  # human-readable labels for logging
    all_reduce_metrics: list[dict] = []
    level = 0

    while len(current_summaries) > 1:
        level += 1
        batches = batch_summaries_for_reduce(
            current_summaries,
            max_items_per_batch=max_batch_size,
            max_tokens_per_batch=max_batch_tokens,
        )
        num_batches = len(batches)
        logger.info(
            "[REDUCE L%d] %d summaries → %d batch(es) (max %d items / ~%d tokens each)",
            level,
            len(current_summaries),
            num_batches,
            max_batch_size,
            max_batch_tokens,
        )

        next_summaries: list[str] = []
        next_labels: list[str] = []
        batch_offset = 0

        for b_idx, batch in enumerate(batches):
            batch_labels = current_labels[batch_offset : batch_offset + len(batch)]
            batch_offset += len(batch)
            batch_label = (
                f"Reduce Level {level}, Batch {b_idx + 1}/{num_batches} "
                f"covering: {', '.join(batch_labels)}"
            )

            # Build the summaries block
            summaries_block_parts = []
            for j, (s, lbl) in enumerate(zip(batch, batch_labels, strict=False)):
                summaries_block_parts.append(
                    f"{'=' * 50}\nSUMMARY {j + 1} | {lbl}\n{'=' * 50}\n{s.strip()}"
                )
            summaries_block = "\n\n".join(summaries_block_parts)

            approx_input = get_string_tokens(
                REDUCE_MERGE_SYSTEM_PROMPT
                + REDUCE_MERGE_USER_TEMPLATE.format(
                    batch_label=batch_label, summaries_block=summaries_block
                )
            )
            logger.info(
                "  [REDUCE L%d BATCH %d/%d] %d summaries, approx_input_tokens~=%d — calling %s",
                level,
                b_idx + 1,
                num_batches,
                len(batch),
                approx_input,
                gen_model,
            )

            user_msg = REDUCE_MERGE_USER_TEMPLATE.format(
                batch_label=batch_label,
                summaries_block=summaries_block,
            )
            merged_outline, usage = await call_llm(
                REDUCE_MERGE_SYSTEM_PROMPT,
                user_msg,
                model=gen_model,
                temperature=0.2,
            )
            approx_output = get_string_tokens(merged_outline)
            logger.info(
                "  [REDUCE L%d BATCH %d/%d] Done — output~=%d tokens (%d words)",
                level,
                b_idx + 1,
                num_batches,
                approx_output,
                len(merged_outline.split()),
            )

            all_reduce_metrics.append(
                {
                    "level": level,
                    "batch": b_idx + 1,
                    "num_batches": num_batches,
                    "items_in_batch": len(batch),
                    "approx_input_tokens": approx_input,
                    "approx_output_tokens": approx_output,
                    "token_usage": usage,
                    "labels": batch_labels,
                }
            )

            next_summaries.append(merged_outline)
            next_labels.append(f"L{level}B{b_idx + 1}({', '.join(batch_labels)})")

            # Polite pause between reduce calls to respect rate limits
            if b_idx < num_batches - 1:
                await asyncio.sleep(INTER_CHUNK_DELAY_SECONDS)

        current_summaries = next_summaries
        current_labels = next_labels

    master_outline = current_summaries[0] if current_summaries else ""
    logger.info(
        "[REDUCE] Complete after %d level(s). Master outline: ~%d tokens (%d words)",
        level,
        get_string_tokens(master_outline),
        len(master_outline.split()),
    )
    return master_outline, all_reduce_metrics


async def run_pipeline(
    structured_data: dict,
    *,
    topic_title: str,
    teaching_instruction: str,
    pages_per_chunk: int,
    fast_model: str,
    gen_model: str,
    print_summaries: bool = False,
    max_subchunk_tokens: int = DEFAULT_MAX_TOKENS_PER_SUBCHUNK_INPUT,
    max_reduce_batch_tokens: int = DEFAULT_MAX_TOKENS_PER_BATCH_REDUCE_INPUT,
    max_reduce_batch_size: int = DEFAULT_MAX_REDUCE_BATCH_SIZE,
) -> dict:
    """
    Full hierarchical map-reduce pipeline:

    [NEW vs OLD]
    OLD flow: chunk → summarize chunk (fast) → concat all → one 70B generate call
    NEW flow:
      1. Chunk sections by page group (same as before)
      2. For each page chunk:
           a. Extract body text per section
           b. Token-split body text into sub-chunks (~max_subchunk_tokens each)
           c. Summarize each sub-chunk with fast model  [NEW: sub-chunk level]
           d. Merge sub-chunk summaries → page-chunk summary  [NEW: merge step]
      3. Hierarchical reduce: batch page-chunk summaries → 70B → mid-level outlines
         → repeat until one master outline remains  [NEW: multi-level reduce]
      4. Final generation from master outline  [NEW: prompt takes outline, not raw summaries]

    Returns a results dict with all intermediate and final outputs.
    """
    sections = structured_data.get("sections") or []
    if not sections:
        raise ValueError(
            "No 'sections' key found in structured_data (or it is empty). "
            "Run --inspect-only to diagnose the JSON structure."
        )

    logger.info("Document sections: %d total", len(sections))

    # ── Step 1: Chunk by pages ────────────────────────────────────────────────
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

    # ── Step 2: Sub-chunk + summarize + merge per page chunk ──────────────────
    # [NEW] Replaces the old "summarize entire chunk in one call" approach.
    summaries: list[dict] = []

    for chunk in chunks:
        idx = chunk["chunk_index"]
        total = chunk["total_chunks"]
        page_range = chunk["page_range"]

        logger.info(
            "Processing chunk %d/%d (%s) — extracting body text...",
            idx,
            total,
            page_range,
        )

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
                    "page_range": page_range,
                    "summary": "[EMPTY CHUNK — no text extracted from sections]",
                    "raw_text": "",
                    "subchunk_summaries": [],
                    "approx_input_tokens": 0,
                    "approx_output_tokens": 0,
                    "token_usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                    },
                }
            )
            continue

        # [NEW] Token-based sub-chunking of the page chunk's body text
        subchunks = split_text_into_subchunks(
            chunk_text, max_tokens=max_subchunk_tokens
        )
        total_subchunks = len(subchunks)
        approx_chunk_input_tokens = get_string_tokens(chunk_text)

        logger.info(
            "  Chunk %d/%d: ~%d tokens of body text → %d sub-chunk(s) (max %d tokens each)",
            idx,
            total,
            approx_chunk_input_tokens,
            total_subchunks,
            max_subchunk_tokens,
        )

        # [NEW] Summarize each sub-chunk with the fast model
        sub_summaries: list[str] = []
        sub_usages: list[dict] = []

        for sc_idx, sc_text in enumerate(subchunks, 1):
            sc_summary, sc_usage = await _summarize_subchunk(
                sc_text,
                subchunk_index=sc_idx,
                total_subchunks=total_subchunks,
                page_range=page_range,
                fast_model=fast_model,
            )
            sub_summaries.append(sc_summary)
            sub_usages.append(sc_usage)

            if print_summaries:
                print(f"\n{'─' * 50}")
                print(f"  [SUBCHUNK {sc_idx}/{total_subchunks}] {page_range}")
                print(f"{'─' * 50}")
                print(sc_summary)

            # Polite pause between sub-chunk calls
            if sc_idx < total_subchunks:
                await asyncio.sleep(INTER_SUBCHUNK_DELAY_SECONDS)

        # [NEW] Merge sub-chunk summaries into one page-chunk summary
        if len(sub_summaries) == 1:
            # Only one sub-chunk — no need to call the merge step
            logger.info(
                "  Chunk %d/%d: single sub-chunk, skipping merge step.", idx, total
            )
            page_chunk_summary = sub_summaries[0]
            merge_usage = sub_usages[0]  # use the one sub-chunk's usage
        else:
            page_chunk_summary, merge_usage = await _merge_subchunk_summaries(
                sub_summaries,
                page_range=page_range,
                fast_model=fast_model,
            )

        approx_output_tokens = get_string_tokens(page_chunk_summary)
        logger.info(
            "  ✓ Chunk %d/%d page-chunk summary ready: ~%d tokens (%d words)",
            idx,
            total,
            approx_output_tokens,
            len(page_chunk_summary.split()),
        )

        if print_summaries:
            print(f"\n{'═' * 60}")
            print(f"  Chunk {idx}/{total} PAGE-CHUNK SUMMARY | {page_range}")
            print(f"{'═' * 60}")
            print(page_chunk_summary)

        summaries.append(
            {
                "chunk_index": idx,
                "page_range": page_range,
                "summary": page_chunk_summary,
                "raw_text": chunk_text,
                "subchunk_summaries": sub_summaries,
                "subchunk_usages": sub_usages,
                "approx_input_tokens": approx_chunk_input_tokens,
                "approx_output_tokens": approx_output_tokens,
                "token_usage": merge_usage,
            }
        )

        # Polite pause between page-chunk processing
        if idx < total:
            await asyncio.sleep(INTER_CHUNK_DELAY_SECONDS)

    # ── Step 3: Hierarchical reduce ───────────────────────────────────────────
    # [NEW] Replaces the old "concat all → one big 70B call" approach.
    logger.info(
        "Starting hierarchical reduce of %d page-chunk summaries...", len(summaries)
    )

    page_chunk_summary_texts = [s["summary"] for s in summaries]
    page_chunk_labels = [s["page_range"] for s in summaries]

    master_outline, reduce_metrics = await _hierarchical_reduce(
        page_chunk_summary_texts,
        page_chunk_labels,
        gen_model=gen_model,
        max_batch_size=max_reduce_batch_size,
        max_batch_tokens=max_reduce_batch_tokens,
    )

    master_outline_tokens = get_string_tokens(master_outline)
    logger.info(
        "Master outline ready: ~%d tokens (%d words)",
        master_outline_tokens,
        len(master_outline.split()),
    )

    # ── Step 4: Final generation from master outline ──────────────────────────
    # [NEW] Prompt takes the master_outline (not raw concatenated chunk summaries).
    effective_instruction = teaching_instruction.strip() or (
        "No specific instruction provided. "
        "Write for a new IT hire with basic programming knowledge "
        "who is unfamiliar with this specific topic."
    )

    gen_user_msg = FINAL_GENERATION_USER_TEMPLATE.format(
        topic_title=topic_title,
        teaching_instruction=effective_instruction,
        master_outline=master_outline,
    )

    logger.info("Generating final study material with %s...", gen_model)
    final_content, gen_usage = await call_llm(
        FINAL_GENERATION_SYSTEM_PROMPT,
        gen_user_msg,
        model=gen_model,
        temperature=0.3,
    )
    logger.info("✓ Study material generated (~%d words)", len(final_content.split()))

    # ── Token metrics ─────────────────────────────────────────────────────────
    raw_json_str = json.dumps(structured_data, ensure_ascii=False)
    raw_json_tokens = get_string_tokens(raw_json_str)

    final_input_tokens = gen_usage.get("input_tokens", 0)
    final_prompt_tokens = max(0, final_input_tokens - master_outline_tokens)
    gen_usage["prompt_tokens"] = final_prompt_tokens
    gen_usage["ref_material_tokens"] = master_outline_tokens

    # Compute total sub-chunk call tokens across all chunks
    total_subchunk_tokens = sum(
        sum(u.get("total_tokens", 0) for u in s.get("subchunk_usages", []))
        for s in summaries
    )
    total_merge_tokens = sum(
        s["token_usage"].get("total_tokens", 0)
        for s in summaries
        if len(s.get("subchunk_summaries", [])) > 1  # only actual merge calls
    )
    total_reduce_tokens = sum(
        m["token_usage"].get("total_tokens", 0) for m in reduce_metrics
    )
    total_gen_tokens = gen_usage.get("total_tokens", 0)

    return {
        "topic_title": topic_title,
        "total_chunks": len(summaries),
        "pages_per_chunk": pages_per_chunk,
        "fast_model": fast_model,
        "gen_model": gen_model,
        "summaries": summaries,
        "master_outline": master_outline,
        # Keep aggregated_summaries key for backward compat (points to master outline)
        "aggregated_summaries": master_outline,
        "final_content": final_content,
        "reduce_metrics": reduce_metrics,
        "token_metrics": {
            "raw_json_tokens": raw_json_tokens,
            "master_outline_tokens": master_outline_tokens,
            # backward compat alias
            "aggregated_summaries_tokens": master_outline_tokens,
            "final_input_tokens": final_input_tokens,
            "total_subchunk_summarization_tokens": total_subchunk_tokens,
            "total_merge_tokens": total_merge_tokens,
            "total_reduce_tokens": total_reduce_tokens,
            "total_generation_tokens": total_gen_tokens,
            "chunk_summaries_tokens": [
                {
                    **s["token_usage"],
                    "approx_input_tokens": s["approx_input_tokens"],
                    "approx_output_tokens": s["approx_output_tokens"],
                    "num_subchunks": len(s.get("subchunk_summaries", [])),
                }
                for s in summaries
            ],
            "final_generation_tokens": gen_usage,
            "reduce_level_metrics": reduce_metrics,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# OUTPUT SAVING (EXTENDED)
# ══════════════════════════════════════════════════════════════════════════════


def save_results(results: dict) -> Path:
    """
    Save all pipeline outputs under OUTPUT_DIR/<topic>_<timestamp>/.

    Directory layout:
      chunk_summaries/chunk_NNN.md       — per-page-chunk summary (merged from sub-chunks)
      subchunk_summaries/chunk_NNN/      — individual sub-chunk summaries [NEW]
      master_outline.md                  — the single master outline produced by reduce [NEW]
      aggregated_summaries.md            — alias for master_outline.md (backward compat)
      study_material.md                  — final study material output
      run_metadata.json                  — run config + token metrics
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in results["topic_title"]
    )[:40]
    run_dir = OUTPUT_DIR / f"{safe}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Per-page-chunk summaries (merged)
    chunk_dir = run_dir / "chunk_summaries"
    chunk_dir.mkdir()
    for item in results["summaries"]:
        f = chunk_dir / f"chunk_{item['chunk_index']:03d}.md"
        f.write_text(
            f"# Chunk {item['chunk_index']} | {item['page_range']}\n\n{item['summary']}",
            encoding="utf-8",
        )

    # [NEW] Sub-chunk summaries — one directory per page-chunk
    subchunk_dir = run_dir / "subchunk_summaries"
    subchunk_dir.mkdir()
    for item in results["summaries"]:
        if item.get("subchunk_summaries"):
            sc_chunk_dir = subchunk_dir / f"chunk_{item['chunk_index']:03d}"
            sc_chunk_dir.mkdir(exist_ok=True)
            for sc_idx, sc_text in enumerate(item["subchunk_summaries"], 1):
                sc_file = sc_chunk_dir / f"subchunk_{sc_idx:03d}.md"
                sc_file.write_text(
                    f"# Sub-chunk {sc_idx} | {item['page_range']}\n\n{sc_text}",
                    encoding="utf-8",
                )

    # [NEW] Master outline
    (run_dir / "master_outline.md").write_text(
        results["master_outline"], encoding="utf-8"
    )
    # Backward compat alias
    (run_dir / "aggregated_summaries.md").write_text(
        results["master_outline"], encoding="utf-8"
    )

    # Final study material
    (run_dir / "study_material.md").write_text(
        results["final_content"], encoding="utf-8"
    )

    # Run metadata (exclude large text blobs)
    meta = {
        k: v
        for k, v in results.items()
        if k
        not in ("summaries", "master_outline", "aggregated_summaries", "final_content")
    }
    # Strip raw_text and subchunk bodies from summaries in metadata to keep it readable
    meta["chunk_summary_index"] = [
        {
            "chunk_index": s["chunk_index"],
            "page_range": s["page_range"],
            "num_subchunks": len(s.get("subchunk_summaries", [])),
            "approx_input_tokens": s.get("approx_input_tokens", 0),
            "approx_output_tokens": s.get("approx_output_tokens", 0),
        }
        for s in results["summaries"]
    ]
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
            Test the StudyGuru hierarchical map-reduce PDF summarization pipeline.
            Chunks a LlamaParse JSON by page groups, sub-chunks by token budget,
            summarizes sub-chunks, merges to page-chunk summaries, reduces
            hierarchically, then generates study material from a single master outline.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pdf_path",
        help="Path to the reference PDF. Used for fresh extraction, or context when --cached-json is provided.",
    )
    parser.add_argument(
        "--cached-json",
        metavar="PATH",
        help=(
            "Path to a previously saved LlamaParse JSON "
            "(the 'raw' artifact from _save_llamaparse_artifact). "
            "When provided, skips LlamaParse extraction entirely."
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
        help=f"Groq model for sub-chunk summarization and merge. Default: {DEFAULT_FAST_MODEL}",
    )
    parser.add_argument(
        "--gen-model",
        default=DEFAULT_GEN_MODEL,
        metavar="MODEL",
        help=f"Groq model for reduce and final generation. Default: {DEFAULT_GEN_MODEL}",
    )
    parser.add_argument(
        "--print-summaries",
        action="store_true",
        help="Print each sub-chunk and page-chunk summary to stdout as it completes.",
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
    # [NEW] Token budget CLI flags
    parser.add_argument(
        "--max-subchunk-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS_PER_SUBCHUNK_INPUT,
        metavar="N",
        help=(
            f"Max body text tokens per sub-chunk before splitting. "
            f"Default: {DEFAULT_MAX_TOKENS_PER_SUBCHUNK_INPUT}. "
            "Lower = more sub-chunks, safer for free-tier RPM."
        ),
    )
    parser.add_argument(
        "--max-reduce-batch-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS_PER_BATCH_REDUCE_INPUT,
        metavar="N",
        help=(
            f"Max token budget per reduce batch. "
            f"Default: {DEFAULT_MAX_TOKENS_PER_BATCH_REDUCE_INPUT}. "
            "Lower = more batches / reduce levels."
        ),
    )
    parser.add_argument(
        "--max-reduce-batch-size",
        type=int,
        default=DEFAULT_MAX_REDUCE_BATCH_SIZE,
        metavar="N",
        help=(
            f"Max number of summaries per reduce batch (item count guard). "
            f"Default: {DEFAULT_MAX_REDUCE_BATCH_SIZE}."
        ),
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

    inspect_json_structure(structured_data)

    # ── Pipeline header ───────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  StudyGuru Hierarchical Map-Reduce Summarization Pipeline Test")
    print(f"  Topic             : {args.topic}")
    print(f"  Pages per chunk   : {args.pages_per_chunk}")
    print(f"  Max subchunk tok  : {args.max_subchunk_tokens}")
    print(
        f"  Max reduce batch  : {args.max_reduce_batch_tokens} tokens / {args.max_reduce_batch_size} items"
    )
    print(f"  Fast model        : {args.fast_model}  (sub-chunk summarization + merge)")
    print(f"  Gen model         : {args.gen_model}  (reduce + final generation)")
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
        max_subchunk_tokens=args.max_subchunk_tokens,
        max_reduce_batch_tokens=args.max_reduce_batch_tokens,
        max_reduce_batch_size=args.max_reduce_batch_size,
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
        master_outline_tokens = metrics.get("master_outline_tokens", 0)

        print(f"  Raw LlamaParse JSON      : {raw_json_tokens:,} tokens")
        print(f"  Master Outline           : {master_outline_tokens:,} tokens")
        if raw_json_tokens > 0:
            reduction = (1 - (master_outline_tokens / raw_json_tokens)) * 100
            print(
                f"  Context size reduced     : {reduction:.1f}% smaller than raw JSON"
            )

        print("\n  1) Sub-chunk Summarization (fast model):")
        total_sc_tokens = metrics.get("total_subchunk_summarization_tokens", 0)
        for i, item in enumerate(metrics.get("chunk_summaries_tokens", [])):
            inp = item.get("input_tokens", 0)
            out = item.get("output_tokens", 0)
            tot = item.get("total_tokens", 0)
            nsc = item.get("num_subchunks", 1)
            approx_in = item.get("approx_input_tokens", 0)
            approx_out = item.get("approx_output_tokens", 0)
            print(
                f"    - Chunk {i + 1:02d}: {nsc} sub-chunk(s), "
                f"body~{approx_in} tok → summary~{approx_out} tok | "
                f"merge call In:{inp:,} Out:{out:,} Total:{tot:,}"
            )
        print(f"    * Total sub-chunk tokens: {total_sc_tokens:,}")

        print("\n  2) Merge Steps (fast model):")
        total_merge = metrics.get("total_merge_tokens", 0)
        print(f"    * Total merge tokens: {total_merge:,}")

        print("\n  3) Hierarchical Reduce (gen model):")
        reduce_metrics = metrics.get("reduce_level_metrics", [])
        for rm in reduce_metrics:
            print(
                f"    [L{rm['level']} Batch {rm['batch']}/{rm['num_batches']}] "
                f"{rm['items_in_batch']} items | "
                f"input~{rm['approx_input_tokens']:,} tok | "
                f"output~{rm['approx_output_tokens']:,} tok | "
                f"covering: {', '.join(rm['labels'])}"
            )
        total_reduce = metrics.get("total_reduce_tokens", 0)
        print(f"    * Total reduce tokens: {total_reduce:,}")

        print("\n  4) Final Study Material Generation (gen model):")
        gen_tokens = metrics.get("final_generation_tokens", {})
        gen_in = gen_tokens.get("input_tokens", 0)
        gen_out = gen_tokens.get("output_tokens", 0)
        gen_tot = gen_tokens.get("total_tokens", 0)
        p_in = gen_tokens.get("prompt_tokens", 0)
        c_in = gen_tokens.get("ref_material_tokens", 0)
        print(
            f"    - Input  : {gen_in:,} tokens [Prompt: {p_in:,} | Outline: {c_in:,}]"
        )
        print(f"    - Output : {gen_out:,} tokens")
        print(f"    - Total  : {gen_tot:,} tokens")

        total_pipeline = total_sc_tokens + total_merge + total_reduce + gen_tot
        print("\n  5) Overall Pipeline Summary:")
        print(f"    - Sub-chunk calls   : {total_sc_tokens:,} tokens")
        print(f"    - Merge calls       : {total_merge:,} tokens")
        print(f"    - Reduce calls      : {total_reduce:,} tokens")
        print(f"    - Generation call   : {gen_tot:,} tokens")
        print(f"    - TOTAL consumed    : {total_pipeline:,} tokens")
        print("═" * 70 + "\n")

    # ── Save outputs ──────────────────────────────────────────────────────────
    if not args.no_save:
        run_dir = save_results(results)
        print(f"\n{'═' * 70}")
        print(f"  Outputs saved → {run_dir}")
        print("    chunk_summaries/           per-page-chunk merged summaries")
        print("    subchunk_summaries/        individual sub-chunk summaries  [NEW]")
        print("    master_outline.md          single outline produced by reduce  [NEW]")
        print("    aggregated_summaries.md    alias for master_outline.md (compat)")
        print("    study_material.md          final generated content")
        print("    run_metadata.json          run config + full token metrics")
        print("═" * 70)


if __name__ == "__main__":
    asyncio.run(main())


# ══════════════════════════════════════════════════════════════════════════════
# FUTURE SPLIT GUIDE (for when this prototype matures into the real agent)
# ══════════════════════════════════════════════════════════════════════════════
#
# LIBRARY MODULE (src/api/control/study_agent/utils/hierarchical_summarizer.py):
#   - split_text_into_subchunks()
#   - batch_summaries_for_reduce()
#   - _summarize_subchunk()
#   - _merge_subchunk_summaries()
#   - _hierarchical_reduce()
#   - run_pipeline()   ← called by the Study Agent's LangGraph node
#   - All prompt templates (or import from chunk_summarizer_prompt.py)
#
# CLI / TEST HARNESS (test.py, kept as-is):
#   - parse_args() + main()
#   - save_results()
#   - _run_fresh_extraction_sync()
#   - inspect_json_structure()
#   - All logging / token reporting
#
# The library module has no argparse, no file I/O, no logging configuration —
# it just takes structured_data + config kwargs and returns a results dict.
# The test harness imports from it and handles all I/O + logging.
# ══════════════════════════════════════════════════════════════════════════════
