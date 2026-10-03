"""Scheduling engine enforcing prerequisite ordering."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List, Optional

from tasks.base_task import Task, TaskStatus, DependencyError, TaskStateError
from engine.task_queue import TaskQueue


class CycleError(Exception):
    """Raised when the dependency graph contains a cycle."""
    pass


class Scheduler:
    """
    Executes a DAG of Tasks in priority order while strictly enforcing
    that every prerequisite is COMPLETED before a task runs.
    """

    def __init__(self, queue: TaskQueue):
        self._queue = queue
        self._event_log: List[Dict] = []

    # ---------------------------------------------------------------- helpers
    @property
    def queue(self) -> TaskQueue:
        return self._queue

    @property
    def event_log(self) -> List[Dict]:
        return list(self._event_log)

    def _log(self, event_type: str, task: Optional[Task], **extra) -> None:
        self._event_log.append({
            "timestamp": datetime.now(),
            "event": event_type,
            "task_id": task.task_id if task else None,
            "status": task.status.value if task else None,
            **extra,
        })

    # ---------------------------------------------------------------- validate
    def validate_graph(self) -> None:
        """
        Check that every prerequisite exists and the graph is acyclic.
        Uses Kahn's algorithm for cycle detection.
        """
        tasks = self._queue.all()
        ids = {t.task_id for t in tasks}

        # 1. All prerequisites must reference known tasks
        for t in tasks:
            for dep in t.prerequisites:
                if dep not in ids:
                    raise DependencyError(
                        f"Task {t.task_id} references unknown prerequisite '{dep}'."
                    )

        # 2. Kahn's algorithm for cycle detection
        indegree: Dict[str, int] = {t.task_id: 0 for t in tasks}
        for t in tasks:
            for _ in t.prerequisites:
                indegree[t.task_id] += 1

        # adjacency: dep -> dependents
        adjacency: Dict[str, List[str]] = {tid: [] for tid in ids}
        for t in tasks:
            for dep in t.prerequisites:
                adjacency[dep].append(t.task_id)

        frontier = [tid for tid, deg in indegree.items() if deg == 0]
        visited = 0
        while frontier:
            node = frontier.pop()
            visited += 1
            for child in adjacency[node]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    frontier.append(child)

        if visited != len(tasks):
            cycle_nodes = [tid for tid, deg in indegree.items() if deg > 0]
            raise CycleError(
                f"Cycle detected involving tasks: {sorted(cycle_nodes)}"
            )

    # ---------------------------------------------------------------- enforce
    def check_dependencies(self, task: Task) -> None:
        """
        Verify all prerequisites are COMPLETED.

        Raises:
            DependencyError: If any prerequisite is missing or not COMPLETED.
        """
        unmet: List[str] = []
        for dep_id in task.prerequisites:
            dep = self._queue.get(dep_id)
            if dep is None:
                raise DependencyError(
                    f"Task {task.task_id} depends on unknown task '{dep_id}'."
                )
            if not dep.is_completed():
                unmet.append(f"{dep_id}({dep.status.value})")
        if unmet:
            raise DependencyError(
                f"Task {task.task_id} has unmet prerequisites: {', '.join(unmet)}"
            )

    # ---------------------------------------------------------------- execute
    def execute_task(self, task: Task) -> bool:
        """
        Run a single task. Returns True on success, False on failure.
        Raises DependencyError or TaskStateError on invalid invocation.
        """
        # 1. Enforce prerequisites
        self.check_dependencies(task)

        # 2. Validate state transition
        if not task.is_pending():
            raise TaskStateError(
                f"Task {task.task_id} cannot run: status {task.status.value}."
            )

        # 3. START
        task.mark_running()
        self._log("TASK_STARTED", task)
        print(f"  ▶ START    [{task.task_id:<10}] prio={task.priority:<3} "
              f"({task.name})")

        # 4. RUN action (if any)
        try:
            if task.action is not None:
                task.action(task)
            task.mark_completed()
            self._log("TASK_COMPLETED", task)
            print(f"  ✔ COMPLETE [{task.task_id:<10}] "
                  f"({task.name}) in {task.duration_seconds:.4f}s")
            return True
        except Exception as exc:
            task.mark_failed(str(exc))
            self._log("TASK_FAILED", task, error=str(exc))
            print(f"  ✘ FAILED   [{task.task_id:<10}] "
                  f"({task.name}) → {exc}")
            return False

    def run_until_complete(self, max_iterations: int = 1000) -> Dict[str, int]:
        """
        Execute the entire graph, always picking the highest-priority ready task.

        Returns:
            A summary dict of final status counts.

        Raises:
            DependencyError / CycleError if the graph is invalid or deadlocked.
        """
        self.validate_graph()

        iterations = 0
        while iterations < max_iterations:
            iterations += 1

            ready = self._queue.ready_tasks()
            if not ready:
                break

            # Pick the highest priority ready task
            task = ready[0]
            self.execute_task(task)

        # After loop — did everything finish?
        summary = self._queue.summary()
        if summary["pending"] > 0 or summary["running"] > 0:
            # Determine whether the stall is due to failures or a true cycle
            failed = {t.task_id for t in self._queue.failed()}
            blocked = self._queue.blocked_tasks()
            if blocked and not failed:
                raise CycleError(
                    f"Deadlock: {len(blocked)} task(s) blocked without a cycle "
                    f"in the graph: {[t.task_id for t in blocked]}"
                )
        return summary

    # ---------------------------------------------------------------- reporting
    def print_status_table(self) -> None:
        print("\n" + "=" * 90)
        print(" TASK STATUS TABLE ".center(90, "="))
        print("=" * 90)
        print(f"{'TASK ID':<12} {'NAME':<24} {'PRIO':>5} {'STATUS':<11} "
              f"{'DURATION':>10}  PREREQS")
        print("-" * 90)
        for t in sorted(self._queue.all(), key=lambda x: (-x.priority, x.task_id)):
            dur = f"{t.duration_seconds:.4f}s" if t.duration_seconds is not None else "—"
            deps = ",".join(t.prerequisites) if t.prerequisites else "—"
            print(f"{t.task_id:<12} {t.name[:23]:<24} {t.priority:>5} "
                  f"{t.status.value:<11} {dur:>10}  {deps}")
        print("=" * 90)

    def print_transition_log(self) -> None:
        print("\n" + "=" * 90)
        print(" STATE TRANSITION LOG ".center(90, "="))
        print("=" * 90)
        for entry in self._event_log:
            ts = entry["timestamp"].strftime("%H:%M:%S.%f")[:-3]
            print(f"  [{ts}] {entry['event']:<16} "
                  f"task={str(entry['task_id']):<10} "
                  f"status={str(entry['status']):<10}"
                  + (f"  error={entry['error']}" if 'error' in entry else ""))
        print("=" * 90)