from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode

InstructionPartType = Literal["inherited", "branch-default", "extra", "override"]


@dataclass(frozen=True)
class EffectiveInstructionPart:
    """One labeled part of the canonical teaching instruction resolution."""

    source_node_id: UUID
    source_node_title: str
    text: str
    type: InstructionPartType
    label: str


NO_INSTRUCTION_FALLBACK = (
    "No specific teaching instruction provided. Write clear, accurate introductory "
    "study material for a learner who is new to this topic."
)


def _nonempty(s: str | None) -> str | None:
    stripped = s.strip() if s else None
    return stripped if stripped else None


def format_effective_instruction(parts: list[EffectiveInstructionPart]) -> str:
    """Canonical, labeled rendering of resolved instruction parts.

    This is the single source of truth used both when generating study material
    (so the rendering is embedded in the version's prompt snapshot) and when
    later deciding whether the effective instruction has changed since
    generation. Both call sites MUST use this function so the two strings are
    byte-for-byte comparable; otherwise the "instruction changed" check produces
    false positives on every reload/navigation.
    """
    if not parts:
        return NO_INSTRUCTION_FALLBACK
    return "\n\n".join(f"{part.label}\n{part.text}" for part in parts)


def resolve_effective_instruction_parts(
    node: TopicNode,
    ancestors: list[TopicNode],
) -> list[EffectiveInstructionPart]:
    """Return labeled instruction parts for *node*.

    ancestors must be ordered root -> parent. Only tree_default_instruction is
    inherited from ancestors; node_additive_instruction applies to the current
    node only and must never be included in a descendant's ancestor chain.
    """

    nsi = _nonempty(node.node_specific_instruction)
    if nsi:
        return [
            EffectiveInstructionPart(
                source_node_id=node.node_id,
                source_node_title=node.title,
                text=nsi,
                type="override",
                label="Your custom instruction:",
            )
        ]

    parts: list[EffectiveInstructionPart] = []

    for ancestor in ancestors:
        val = _nonempty(ancestor.tree_default_instruction)
        if val:
            parts.append(
                EffectiveInstructionPart(
                    source_node_id=ancestor.node_id,
                    source_node_title=ancestor.title,
                    text=val,
                    type="inherited",
                    label=f"From parent section ({ancestor.title}):",
                )
            )

    current_tdi = _nonempty(node.tree_default_instruction)
    if current_tdi:
        parts.append(
            EffectiveInstructionPart(
                source_node_id=node.node_id,
                source_node_title=node.title,
                text=current_tdi,
                type="branch-default",
                label="Instruction for This Topic Branch:",
            )
        )

    current_nai = _nonempty(node.node_additive_instruction)
    if current_nai:
        parts.append(
            EffectiveInstructionPart(
                source_node_id=node.node_id,
                source_node_title=node.title,
                text=current_nai,
                type="extra",
                label="Prompt for this topic:",
            )
        )

    return parts
