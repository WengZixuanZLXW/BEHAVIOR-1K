"""CPU-only test for the stall report."""
from __future__ import annotations
import io, os, sys, time
from contextlib import redirect_stdout

sys.path.insert(0, "/home/zixuanwe/Desktop/BEHAVIOR-1K")
from coop2.experiment.stall_watch import StallWatch


class FakePlan:
    def __init__(self, spec, status): self.specification, self.status = spec, FakeStatus(status)
class FakeStatus:
    def __init__(self, v): self.value = v
class FakeState:
    def __init__(self, v): self.value = v
class FakeAgent:
    def __init__(self, ready, state, plan=None, wants=False):
        self.ready, self.state, self.plan, self._wants = ready, FakeState(state), plan, wants
    def needs_new_plan(self): return self._wants


def main() -> int:
    print("test: a stall is reported, and names the agent and why")
    agents = {
        "agent_0": FakeAgent(True, "executing"),
        # The shape that hung a run: R, a live plan, needs_new_plan False.
        "agent_1": FakeAgent(False, "reasoning",
                             FakePlan("ontop(apple.n.01_1, coffee_table.n.01_1)", "executing"),
                             wants=False),
    }
    watch = StallWatch(agents, seconds=0.2)
    out = io.StringIO()
    with redirect_stdout(out):
        watch.check()                 # first sight: starts the clock
        assert out.getvalue() == "", "reported before the grace period"
        time.sleep(0.25)
        watch.check()
    text = out.getvalue()
    assert "[stall]" in text, "no report after the grace period"
    assert "agent_1" in text and "agent_0" not in text, "reported the wrong agent"
    assert "state=reasoning" in text and "needs_new_plan=False" in text
    assert "ontop(apple.n.01_1" in text, "did not say which plan is blocking it"
    print("  ok: names agent_1, its state, its live plan and needs_new_plan")

    print("\ntest: a changing not-ready set restarts the clock, it is not a stall")
    agents = {"a": FakeAgent(False, "reasoning", wants=True),
              "b": FakeAgent(True, "waiting")}
    watch = StallWatch(agents, seconds=0.2)
    out = io.StringIO()
    with redirect_stdout(out):
        watch.check()
        time.sleep(0.15)
        agents["a"].ready = True      # a went ready; now b is the one waiting
        agents["b"].ready = False
        watch.check()
        time.sleep(0.15)
        watch.check()
    assert out.getvalue() == "", f"a moving set was reported as a stall: {out.getvalue()}"
    print("  ok: progress resets the clock")

    print("\ntest: everyone ready is silent, and a real stall keeps reporting")
    agents = {"a": FakeAgent(True, "executing")}
    watch = StallWatch(agents, seconds=0.05)
    out = io.StringIO()
    with redirect_stdout(out):
        for _ in range(3):
            watch.check(); time.sleep(0.06)
    assert out.getvalue() == ""
    agents["a"].ready = False
    out = io.StringIO()
    with redirect_stdout(out):
        watch.check(); time.sleep(0.06); watch.check(); time.sleep(0.06); watch.check()
    assert out.getvalue().count("[stall]") >= 2, (
        "it latched after the first report instead of repeating"
    )
    print("  ok: silent when ready, repeats while genuinely stuck")

    print("\ntest: a diagnostic never raises")
    class Exploding(FakeAgent):
        def needs_new_plan(self): raise RuntimeError("boom")
    watch = StallWatch({"x": Exploding(False, "reasoning")}, seconds=0.01)
    out = io.StringIO()
    with redirect_stdout(out):
        watch.check(); time.sleep(0.02); watch.check()
    assert "needs_new_plan=?" in out.getvalue()
    assert StallWatch.describe(None) == "missing"
    print("  ok: an agent that throws is described, not propagated")

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
