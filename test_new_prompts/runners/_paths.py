"""Path constants for prompt test runners."""

from __future__ import annotations

from pathlib import Path

RUNNERS_DIR = Path(__file__).resolve().parent
TEST_PROMPTS_ROOT = RUNNERS_DIR.parent
PROMPTS_DIR = TEST_PROMPTS_ROOT / "prompts"
RUN_OUTPUT_DIR = TEST_PROMPTS_ROOT / "run_output"
SERVICE_ROOT = TEST_PROMPTS_ROOT.parent
