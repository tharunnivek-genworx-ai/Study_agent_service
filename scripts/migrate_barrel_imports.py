#!/usr/bin/env python3
"""Rewrite deep src.api imports to use package barrels (Phase 4 migration)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Deep import path -> barrel path. Longest paths first when applying.
BARREL_RULES: list[tuple[str, str]] = [
    # Schemas — subpackages
    ("src.api.schemas.common.generation_diagnostics_schema", "src.api.schemas.common"),
    ("src.api.schemas.common.generation_enums", "src.api.schemas.common"),
    (
        "src.api.schemas.identity_schemas.auth_schema",
        "src.api.schemas.identity_schemas",
    ),
    (
        "src.api.schemas.progress_schemas.mentor_progress_schema",
        "src.api.schemas.progress_schemas",
    ),
    (
        "src.api.schemas.progress_schemas.trainee_progress_schema",
        "src.api.schemas.progress_schemas",
    ),
    ("src.api.schemas.quiz_schemas.hint_schema", "src.api.schemas.quiz_schemas"),
    ("src.api.schemas.quiz_schemas.quiz_schema", "src.api.schemas.quiz_schemas"),
    (
        "src.api.schemas.study_material_schemas.concept_checklist_schema",
        "src.api.schemas.study_material_schemas",
    ),
    (
        "src.api.schemas.study_material_schemas.generation_document_schema",
        "src.api.schemas.study_material_schemas",
    ),
    (
        "src.api.schemas.study_material_schemas.node_media_schema",
        "src.api.schemas.study_material_schemas",
    ),
    (
        "src.api.schemas.study_material_schemas.reference_material_schema",
        "src.api.schemas.study_material_schemas",
    ),
    (
        "src.api.schemas.study_material_schemas.study_material_schema",
        "src.api.schemas.study_material_schemas",
    ),
    (
        "src.api.schemas.study_material_schemas.trainee_node_panel_schema",
        "src.api.schemas.study_material_schemas",
    ),
    (
        "src.api.schemas.study_material_schemas.trainee_topic_resource_schema",
        "src.api.schemas.study_material_schemas",
    ),
    ("src.api.schemas.qc_schemas.qc_check_schema", "src.api.schemas.qc_schemas"),
    (
        "src.api.schemas.qc_schemas.qc_retry_routing_schema",
        "src.api.schemas.qc_schemas",
    ),
    (
        "src.api.schemas.qc_schemas.quiz_retry_routing_schema",
        "src.api.schemas.qc_schemas",
    ),
    ("src.api.schemas.generation_run_schema", "src.api.schemas"),
    ("src.api.schemas.generation_progress_schema", "src.api.schemas"),
    # Services
    ("src.api.core.services.generation_run_service", "src.api.core.services"),
    (
        "src.api.core.services.study_agent_services.study_material_service",
        "src.api.core.services",
    ),
    (
        "src.api.core.services.study_agent_services.reference_material_service",
        "src.api.core.services",
    ),
    ("src.api.core.services.quiz_services.quiz_service", "src.api.core.services"),
    ("src.api.core.services.quiz_services.hint_service", "src.api.core.services"),
    (
        "src.api.core.services.progress_services.mentor_progress_service",
        "src.api.core.services",
    ),
    (
        "src.api.core.services.progress_services.trainee_progress_service",
        "src.api.core.services",
    ),
    (
        "src.api.core.services.progress_services.trainee_space_progress_service",
        "src.api.core.services",
    ),
    (
        "src.api.core.services.trainee_study_services.trainee_study_service",
        "src.api.core.services",
    ),
    (
        "src.api.core.services.trainee_study_services.trainee_node_panel_service",
        "src.api.core.services",
    ),
    (
        "src.api.core.services.trainee_quiz_services.trainee_quiz_service",
        "src.api.core.services",
    ),
    # Exceptions
    (
        "src.api.core.exceptions.generation_run_exceptions",
        "src.api.core.exceptions",
    ),
    (
        "src.api.core.exceptions.identity_exceptions.auth_exceptions",
        "src.api.core.exceptions",
    ),
    (
        "src.api.core.exceptions.progress_exceptions.progress_exceptions",
        "src.api.core.exceptions",
    ),
    (
        "src.api.core.exceptions.quiz_exceptions.hint_generation_exceptions",
        "src.api.core.exceptions",
    ),
    (
        "src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions",
        "src.api.core.exceptions",
    ),
    (
        "src.api.core.exceptions.quiz_exceptions.trainee_quiz_exceptions",
        "src.api.core.exceptions",
    ),
    (
        "src.api.core.exceptions.space_node_exceptions.node_exceptions",
        "src.api.core.exceptions",
    ),
    (
        "src.api.core.exceptions.space_node_exceptions.space_exceptions",
        "src.api.core.exceptions",
    ),
    (
        "src.api.core.exceptions.study_material_exceptions.reference_material_exceptions",
        "src.api.core.exceptions",
    ),
    (
        "src.api.core.exceptions.study_material_exceptions.study_material_exceptions",
        "src.api.core.exceptions",
    ),
    # Repositories
    (
        "src.api.data.repositories.generation_run_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.progress_repositories.mentor_progress_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.progress_repositories.trainee_node_progress_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.progress_repositories.trainee_space_progress_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.quiz_repositories.hint_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.quiz_repositories.quiz_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.space_node_repository.node_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.space_node_repository.space_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.study_agent_repositories.reference_llamaparse_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.study_agent_repositories.reference_material_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.study_agent_repositories.study_material_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.trainee_quiz_repositories.trainee_quiz_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.trainee_study_repositories.trainee_node_panel_repository",
        "src.api.data.repositories",
    ),
    (
        "src.api.data.repositories.trainee_study_repositories.trainee_study_repository",
        "src.api.data.repositories",
    ),
    # Postgres client
    ("src.api.data.clients.postgres.database", "src.api.data.clients.postgres"),
    # Config
    ("src.api.config.llm_config", "src.api.config"),
    ("src.api.config.dbconfig", "src.api.config"),
    # Utils
    ("src.api.utils.artifacts.common", "src.api.utils.artifacts"),
    ("src.api.utils.common_utils.time", "src.api.utils.common_utils"),
    ("src.api.utils.common_utils.tokens", "src.api.utils.common_utils"),
    (
        "src.api.control.quiz_agent.prompts.quiz_qc_check_definitions",
        "src.api.control.quiz_agent.prompts",
    ),
    (
        "src.api.control.quiz_agent.prompts.quiz_qc_prompt",
        "src.api.control.quiz_agent.prompts",
    ),
    (
        "src.api.control.quiz_agent.prompts.quiz_prompt",
        "src.api.control.quiz_agent.prompts",
    ),
    (
        "src.api.control.quiz_agent.prompts.question_rework_prompt",
        "src.api.control.quiz_agent.prompts",
    ),
    (
        "src.api.control.quiz_agent.prompts.question_insert_prompt",
        "src.api.control.quiz_agent.prompts",
    ),
    (
        "src.api.control.quiz_agent.prompts.quiz_qc_retry_verification_prompt",
        "src.api.control.quiz_agent.prompts",
    ),
]

BARREL_RULES.sort(key=lambda pair: len(pair[0]), reverse=True)

IMPORT_FROM_RE = re.compile(r"^(\s*)from\s+([\w.]+)\s+import\s+", re.MULTILINE)


def _path_to_pkg_prefix(file_path: Path) -> str:
    return file_path.relative_to(ROOT).as_posix()


def _allows_deep_import(file_rel: str, deep_module: str) -> bool:
    """Allow deep imports when the importing file lives inside the implementation package."""
    file_rel = file_rel.replace("\\", "/")
    if not file_rel.startswith("src/api/"):
        return False
    suffix = deep_module.removeprefix("src.api.").replace(".", "/")
    if file_rel.startswith(f"src/api/{suffix}"):
        return True
    if file_rel.startswith(f"src/api/{suffix}/"):
        return True
    barrel = next((b for d, b in BARREL_RULES if d == deep_module), None)
    if barrel is None:
        return False
    barrel_suffix = barrel.removeprefix("src.api.").replace(".", "/")
    if file_rel == f"src/api/{barrel_suffix}/__init__.py":
        return True
    if deep_module.startswith("src.api.schemas.") and file_rel.startswith(
        "src/api/schemas/"
    ):
        deep_parts = deep_module.removeprefix("src.api.schemas.").split(".")
        if len(deep_parts) >= 2:
            subpkg = deep_parts[0]
            if file_rel.startswith(f"src/api/schemas/{subpkg}/"):
                return True
    if deep_module.startswith("src.api.core.services.") and file_rel.startswith(
        "src/api/core/services/"
    ):
        parts = deep_module.removeprefix("src.api.core.services.").split(".")
        if len(parts) >= 2 and file_rel.startswith(
            f"src/api/core/services/{parts[0]}/"
        ):
            return True
    if deep_module.startswith("src.api.data.repositories.") and file_rel.startswith(
        "src/api/data/repositories/"
    ):
        parts = deep_module.removeprefix("src.api.data.repositories.").split(".")
        if not parts:
            return file_rel.startswith("src/api/data/repositories/")
        if len(parts) == 1 and file_rel.startswith(
            f"src/api/data/repositories/{parts[0]}.py"
        ):
            return True
        if len(parts) >= 2 and file_rel.startswith(
            f"src/api/data/repositories/{parts[0]}/"
        ):
            return True
    if deep_module.startswith("src.api.core.exceptions.") and file_rel.startswith(
        "src/api/core/exceptions/"
    ):
        return True
    if deep_module == "src.api.data.clients.postgres.database" and file_rel.startswith(
        "src/api/data/clients/postgres/"
    ):
        return True
    if deep_module.startswith("src.api.config.") and file_rel.startswith(
        "src/api/config/"
    ):
        return file_rel.endswith("__init__.py") or deep_module.endswith(
            file_rel.removeprefix("src/api/").removesuffix(".py").replace("/", ".")
        )
    if deep_module.startswith("src.api.utils.artifacts.") and file_rel.startswith(
        "src/api/utils/artifacts/"
    ):
        return True
    if deep_module.startswith("src.api.utils.common_utils.") and file_rel.startswith(
        "src/api/utils/common_utils/"
    ):
        return True
    if deep_module.startswith(
        "src.api.control.quiz_agent.prompts."
    ) and file_rel.startswith("src/api/control/quiz_agent/prompts/"):
        return file_rel != "src/api/control/quiz_agent/prompts/__init__.py"
    return False


def rewrite_file(path: Path) -> bool:
    rel = _path_to_pkg_prefix(path)
    barrel_inits = {
        "src/api/schemas/common/__init__.py",
        "src/api/schemas/identity_schemas/__init__.py",
        "src/api/schemas/progress_schemas/__init__.py",
        "src/api/schemas/quiz_schemas/__init__.py",
        "src/api/schemas/study_material_schemas/__init__.py",
        "src/api/schemas/qc_schemas/__init__.py",
        "src/api/schemas/__init__.py",
        "src/api/core/services/__init__.py",
        "src/api/core/exceptions/__init__.py",
        "src/api/data/repositories/__init__.py",
        "src/api/data/clients/postgres/__init__.py",
        "src/api/config/__init__.py",
        "src/api/utils/artifacts/__init__.py",
        "src/api/utils/common_utils/__init__.py",
        "src/api/control/quiz_agent/prompts/__init__.py",
    }
    if rel.replace("\\", "/") in barrel_inits:
        return False
    original = path.read_text(encoding="utf-8")
    updated = original

    def replacer(match: re.Match[str]) -> str:
        indent, module = match.group(1), match.group(2)
        for deep, barrel in BARREL_RULES:
            if module == deep or module.startswith(deep + "."):
                if _allows_deep_import(rel, deep):
                    return match.group(0)
                return f"{indent}from {barrel} import "
        return match.group(0)

    updated = IMPORT_FROM_RE.sub(replacer, updated)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> int:
    targets = [
        ROOT / "src",
        ROOT / "tests",
        ROOT / "scripts",
    ]
    changed = 0
    for base in targets:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if rewrite_file(path):
                changed += 1
                print(path.relative_to(ROOT))
    print(f"\nRewrote imports in {changed} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
