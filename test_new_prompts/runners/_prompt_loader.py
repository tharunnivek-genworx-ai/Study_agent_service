"""Load prompt modules from test_new_prompts/prompts without modifying them."""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

from test_new_prompts.runners._paths import PROMPTS_DIR, SERVICE_ROOT


def _ensure_import_paths() -> None:
    service_root = str(SERVICE_ROOT)
    if service_root not in sys.path:
        sys.path.insert(0, service_root)


def load_prompt_module(module_name: str) -> ModuleType:
    """Import a prompt module by filename stem (e.g. generation_prompt)."""
    _ensure_import_paths()
    module_path = PROMPTS_DIR / f"{module_name}.py"
    if not module_path.is_file():
        raise FileNotFoundError(f"Prompt module not found: {module_path}")

    qualified_name = f"test_new_prompts.prompts.{module_name}"
    spec = importlib.util.spec_from_file_location(qualified_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load prompt module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module
