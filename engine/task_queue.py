"""Priority queue managing pending task ordering."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from tasks.base_task import Task, TaskStatus


class TaskQueue:
    """
    Holds tasks and orders them by descending priority (then by insertion order
    for stable tie-breaking).
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}
        self._insertion_counter: int = 0

    # ---------------------------------------------------------------- mutation
    def add(self, task: Task) -> None:
        """Register a task. Idempotent on task_id collision → raises."""
        if task.task_id in self._tasks:
            raise ValueError(f"Task ID '{task.task_id}' already registered.")
        self._tasks[task.task_id] = task
        self._insertion_counter += 1

    def extend(self, tasks: Iterable[Task]) -> None:
        for t in tasks:
            self.add(t)

    def remove(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    # ---------------------------------------------------------------- queries
    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def all(self) -> List[Task]:
        return list(self._tasks.values())

    def by_status(self, status: TaskStatus) -> List[Task]:
        return [t for t in self._tasks.values() if t.status == status]

    def pending(self) -> List[Task]:
        return self.by_status(TaskStatus.PENDING)

    def completed(self) -> List[Task]:
        return self.by_status(TaskStatus.COMPLETED)

    def failed(self) -> List[Task]:
        return self.by_status(TaskStatus.FAILED)

    def __len__(self) -> int:
        return len(self._tasks)

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._tasks

    # ---------------------------------------------------------------- ordering
    @staticmethod
    def sort_by_priority(tasks: List[Task]) -> List[Task]:
        """
        Stable sort: higher priority first, then lexicographic task_id.
        Uses Python's Timsort → O(n log n).
        """
        return sorted(tasks, key=lambda t: (-t.priority, t.task_id))

    @staticmethod
    def insertion_sort_by_priority(tasks: List[Task]) -> List[Task]:
        """
        Stable insertion sort implemented manually (O(n^2) worst case).
        Provided for pedagogy / small batches.
        """
        result = list(tasks)
        for i in range(1, len(result)):
            key = result[i]
            j = i - 1
            while j >= 0 and (
                result[j].priority < key.priority
                or (result[j].priority == key.priority and result[j].task_id > key.task_id)
            ):
                result[j + 1] = result[j]
                j -= 1
            result[j + 1] = key
        return result

    def ready_tasks(self) -> List[Task]:
        """
        Return pending tasks whose every prerequisite is COMPLETED,
        sorted by priority (descending).
        """
        ready: List[Task] = []
        for task in self._tasks.values():
            if not task.is_pending():
                continue
            if all(
                self._tasks.get(dep) and self._tasks[dep].is_completed()
                for dep in task.prerequisites
            ):
                ready.append(task)
        return self.sort_by_priority(ready)

    def blocked_tasks(self) -> List[Task]:
        """Pending tasks with at least one unmet prerequisite."""
        return [
            t for t in self._tasks.values()
            if t.is_pending() and not all(
                self._tasks.get(d) and self._tasks[d].is_completed()
                for d in t.prerequisites
            )
        ]

    def summary(self) -> Dict[str, int]:
        return {
            "total": len(self._tasks),
            "pending": len(self.pending()),
            "running": len(self.by_status(TaskStatus.RUNNING)),
            "completed": len(self.completed()),
            "failed": len(self.failed()),
        }