"""Core Task model for the workflow scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Set

from enum import Enum


class TaskStatus(str, Enum):
    """Lifecycle status of a task."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DependencyError(Exception):
    """Raised when a task is scheduled before its prerequisites complete."""
    pass


class TaskStateError(Exception):
    """Raised on illegal status transitions (e.g., running a completed task)."""
    pass


@dataclass
class Task:
    """
    A single unit of work within the workflow graph.

    Attributes:
        task_id: Unique string identifier.
        name: Human-readable label.
        priority: Larger values are scheduled first.
        prerequisites: List of task_ids that must be COMPLETED before this runs.
        action: Optional callable invoked on execution. May raise to fail the task.
    """

    task_id: str
    name: str
    priority: int = 0
    prerequisites: List[str] = field(default_factory=list)
    action: Optional[Callable[["Task"], None]] = None

    # Runtime-managed state (not constructor args)
    status: TaskStatus = field(default=TaskStatus.PENDING, init=False)
    _history: List[tuple] = field(default_factory=list, init=False)
    _started_at: Optional[datetime] = field(default=None, init=False)
    _finished_at: Optional[datetime] = field(default=None, init=False)
    _error: Optional[str] = field(default=None, init=False)

    # ------------------------------------------------------------------ init
    def __post_init__(self):
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string.")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise ValueError("priority must be an integer.")
        if not isinstance(self.prerequisites, list):
            raise ValueError("prerequisites must be a list of task_ids.")
        if len(set(self.prerequisites)) != len(self.prerequisites):
            raise ValueError(f"Duplicate prerequisites on task {self.task_id}.")
        if self.task_id in self.prerequisites:
            raise ValueError(f"Task {self.task_id} cannot depend on itself.")

        # Seed history
        self._history.append((datetime.now(), "CREATED", TaskStatus.PENDING))

    # ------------------------------------------------------------- properties
    @property
    def status_value(self) -> str:
        return self.status.value

    @property
    def history(self) -> List[tuple]:
        """Read-only snapshot of (timestamp, event, resulting_status) tuples."""
        return list(self._history)

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    @property
    def finished_at(self) -> Optional[datetime]:
        return self._finished_at

    @property
    def duration_seconds(self) -> Optional[float]:
        if self._started_at and self._finished_at:
            return (self._finished_at - self._started_at).total_seconds()
        return None

    # ------------------------------------------------------------- predicates
    def is_pending(self) -> bool:
        return self.status == TaskStatus.PENDING

    def is_running(self) -> bool:
        return self.status == TaskStatus.RUNNING

    def is_completed(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    def is_failed(self) -> bool:
        return self.status == TaskStatus.FAILED

    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    # ------------------------------------------------------- state transitions
    def _transition(self, new_status: TaskStatus, event: str) -> None:
        """Internal helper: record and apply a status change."""
        self.status = new_status
        self._history.append((datetime.now(), event, new_status))

    def mark_running(self) -> None:
        if self.status != TaskStatus.PENDING:
            raise TaskStateError(
                f"Task {self.task_id} cannot start: status is {self.status.value}, "
                f"expected PENDING."
            )
        self._started_at = datetime.now()
        self._transition(TaskStatus.RUNNING, "STARTED")

    def mark_completed(self) -> None:
        if self.status != TaskStatus.RUNNING:
            raise TaskStateError(
                f"Task {self.task_id} cannot complete: status is {self.status.value}, "
                f"expected RUNNING."
            )
        self._finished_at = datetime.now()
        self._transition(TaskStatus.COMPLETED, "COMPLETED")

    def mark_failed(self, reason: str) -> None:
        if self.status != TaskStatus.RUNNING:
            raise TaskStateError(
                f"Task {self.task_id} cannot fail: status is {self.status.value}, "
                f"expected RUNNING."
            )
        self._error = reason
        self._finished_at = datetime.now()
        self._transition(TaskStatus.FAILED, f"FAILED: {reason}")

    def reset(self) -> None:
        """Reset task to PENDING (history preserved)."""
        self.status = TaskStatus.PENDING
        self._started_at = None
        self._finished_at = None
        self._error = None
        self._history.append((datetime.now(), "RESET", TaskStatus.PENDING))

    # ----------------------------------------------------------------- display
    def __str__(self) -> str:
        return (
            f"Task({self.task_id}, '{self.name}', prio={self.priority}, "
            f"status={self.status.value}, deps={self.prerequisites})"
        )

    def __hash__(self) -> int:
        return hash(self.task_id)

    def __eq__(self, other) -> bool:
        return isinstance(other, Task) and other.task_id == self.task_id