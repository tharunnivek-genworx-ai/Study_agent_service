"""Lifecycle status constants for study material versions and quizzes."""

from typing import Literal

LifecycleStatus = Literal["draft", "active", "archived", "hidden", "discarded"]

LIFECYCLE_DRAFT: LifecycleStatus = "draft"
LIFECYCLE_ACTIVE: LifecycleStatus = "active"
LIFECYCLE_ARCHIVED: LifecycleStatus = "archived"
LIFECYCLE_HIDDEN: LifecycleStatus = "hidden"
LIFECYCLE_DISCARDED: LifecycleStatus = "discarded"
