import time
from tasks import Task, DependencyError, TaskStateError
from engine import TaskQueue, Scheduler, CycleError

def banner(title: str) -> None:
    print("\n" + "=" * 90)
    print(f" {title}".ljust(90, "="))
    print("=" * 90)


def make_action(label: str, duration: float = 0.02, fail: bool = False):
    def _action(task: Task) -> None:
        time.sleep(duration)
        if fail:
            raise RuntimeError(f"simulated failure in {label}")
    return _action

def build_graph() -> TaskQueue:
    queue = TaskQueue()

    checkout = Task(
        task_id="checkout", name="Checkout source",
        priority=10, prerequisites=[],
        action=make_action("checkout", duration=0.03),
    )
    install = Task(
        task_id="install", name="Install dependencies",
        priority=8, prerequisites=["checkout"],
        action=make_action("install", duration=0.04),
    )
    lint = Task(
        task_id="lint", name="Static analysis / lint",
        priority=5, prerequisites=["checkout"],
        action=make_action("lint", duration=0.02),
    )
    build = Task(
        task_id="build", name="Compile artifacts",
        priority=9, prerequisites=["install"],
        action=make_action("build", duration=0.05),
    )
    test = Task(
        task_id="test", name="Run test suite",
        priority=7, prerequisites=["build"],
        action=make_action("test", duration=0.05),
    )
    package = Task(
        task_id="package", name="Package release",
        priority=6, prerequisites=["test", "lint"],
        action=make_action("package", duration=0.02),
    )
    deploy = Task(
        task_id="deploy", name="Deploy to staging",
        priority=4, prerequisites=["package"],
        action=make_action("deploy", duration=0.03),
    )
    notify = Task(
        task_id="notify", name="Notify stakeholders",
        priority=1, prerequisites=["deploy"],
        action=make_action("notify", duration=0.01),
    )

    queue.extend([checkout, install, lint, build, test, package, deploy, notify])
    return queue

def demo_dependency_enforcement(scheduler: Scheduler) -> None:
    banner("DEPENDENCY ENFORCEMENT DEMO")
    deferred = scheduler.queue.get("deploy")
    print(f"Attempting to execute '{deferred.task_id}' before its prerequisites...")
    try:
        scheduler.execute_task(deferred)
        print("  (unexpected) executed successfully")
    except DependencyError as exc:
        print(f"  ✗ DependencyError raised as expected:\n     {exc}")
    except TaskStateError as exc:
        print(f"  ✗ TaskStateError raised:\n     {exc}")


def demo_cycle_detection() -> None:
    banner("CYCLE DETECTION DEMO")

    bad_queue = TaskQueue()
    bad_queue.add(Task(task_id="A", name="A", priority=1, prerequisites=["C"]))
    bad_queue.add(Task(task_id="B", name="B", priority=1, prerequisites=["A"]))
    bad_queue.add(Task(task_id="C", name="C", priority=1, prerequisites=["B"]))

    sched = Scheduler(bad_queue)
    try:
        sched.validate_graph()
        print("  (unexpected) graph validated")
    except CycleError as exc:
        print(f"  ✗ CycleError raised as expected:\n     {exc}")


def demo_unknown_prereq() -> None:
    banner("UNKNOWN PREREQUISITE DEMO")

    bad_queue = TaskQueue()
    bad_queue.add(Task(task_id="X", name="X", priority=1, prerequisites=["ghost"]))

    sched = Scheduler(bad_queue)
    try:
        sched.validate_graph()
        print("  (unexpected) graph validated")
    except DependencyError as exc:
        print(f"  ✗ DependencyError raised as expected:\n     {exc}")

def demo_failure_propagation() -> None:
    banner("FAILURE PROPAGATION DEMO")

    q = TaskQueue()
    q.add(Task(task_id="A", name="A", priority=5, prerequisites=[],
               action=make_action("A", duration=0.01)))
    q.add(Task(task_id="B", name="B", priority=4, prerequisites=["A"],
               action=make_action("B", duration=0.01, fail=True)))
    q.add(Task(task_id="C", name="C", priority=3, prerequisites=["B"],
               action=make_action("C", duration=0.01)))
    q.add(Task(task_id="D", name="D", priority=2, prerequisites=["A"],
               action=make_action("D", duration=0.01)))

    sched = Scheduler(q)
    sched.run_until_complete()

    sched.print_status_table()
    print("\n  Note: 'C' is blocked because 'B' failed; 'D' still ran because"
          "\n        its only prerequisite ('A') completed.")

def main() -> None:
    banner("DIRECTED WORKFLOW SCHEDULER — PRIORITY DAG EXECUTION")
    queue = build_graph()
    print(f"Graph constructed with {len(queue)} tasks.\n")
    for t in queue.all():
        deps = ", ".join(t.prerequisites) or "—"
        print(f"  • [{t.task_id:<10}] prio={t.priority:<3} "
              f"deps=[{deps}]  ({t.name})")

    scheduler = Scheduler(queue)

    banner("READY TASKS AT t=0 (highest priority first)")
    for t in queue.ready_tasks():
        print(f"  ▶ {t.task_id:<10} prio={t.priority:<3} ({t.name})")

    demo_dependency_enforcement(scheduler)

    banner("EXECUTING WORKFLOW GRAPH")
    summary = scheduler.run_until_complete()
    scheduler.print_status_table()
    scheduler.print_transition_log()

    banner("EXECUTION SUMMARY")
    print(f"  Total tasks     : {summary['total']}")
    print(f"  Completed       : {summary['completed']}")
    print(f"  Failed          : {summary['failed']}")
    print(f"  Pending (stuck) : {summary['pending']}")

    total_sec = sum(
        t.duration_seconds or 0.0 for t in queue.all()
    )
    print(f"  Summed duration : {total_sec:.4f}s")
    demo_cycle_detection()
    demo_unknown_prereq()
    demo_failure_propagation()

    banner("END OF SIMULATION")


if __name__ == "__main__":
    try:
        main()
    except (DependencyError, CycleError, TaskStateError) as exc:
        print(f"\n❌ Fatal scheduling error: {exc}")
    except Exception as exc:
        print(f"\n❌ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()