"""CPU-only test for the hold shading on the agent timeline.

A `wait_for_team` hold and a real primitive are both FSM state X, and
`_coalesce` routinely folds them into one bar, so the figure only tells the
truth if that bar is cut where the hold begins.
"""
from __future__ import annotations
import sys

sys.path.insert(0, "/home/zixuanwe/Desktop/BEHAVIOR-1K")
import json, os, tempfile
from coop2.experiment.agent_timeline import (
    _holds, _merge_ranges, _split_on_holds, _team_waiting,
)


def main() -> int:
    print("test: a span that straddles a hold boundary is cut, not classified")
    # 100 s of X covering env_step 0-1000; the team hold starts halfway.
    pieces = _split_on_holds((0.0, 100.0, "executing", 0, 1000), [(500, 1000)])
    assert [p[2] for p in pieces] == ["executing", "holding"], pieces
    assert pieces[0][:2] == (0.0, 50.0), pieces[0]
    assert pieces[1][:2] == (50.0, 100.0), pieces[1]
    assert (pieces[0][3], pieces[0][4]) == (0, 500)
    assert (pieces[1][3], pieces[1][4]) == (500, 1000)
    print("  ok: the split point is interpolated from the env_step range")

    print("\ntest: work on both sides of a hold survives as work")
    pieces = _split_on_holds((0.0, 10.0, "executing", 0, 100), [(20, 40)])
    assert [p[2] for p in pieces] == ["executing", "holding", "executing"]
    assert [round(p[0], 6) for p in pieces] == [0.0, 2.0, 4.0]
    print("  ok: a hold inside a span leaves the remainder dark")

    print("\ntest: a fully-held span is one holding piece")
    pieces = _split_on_holds((0.0, 10.0, "executing", 500, 600), [(400, 700)])
    assert len(pieces) == 1 and pieces[0][2] == "holding", pieces
    print("  ok: total containment still shades the whole bar")

    print("\ntest: nothing else is touched")
    for state in ("reasoning", "waiting", "interrupted"):
        span = (0.0, 10.0, state, 0, 0)
        assert _split_on_holds(span, [(0, 10)]) == [span]
    span = (0.0, 10.0, "executing", 0, 1000)
    assert _split_on_holds(span, []) == [span]
    assert _split_on_holds(span, [(2000, 3000)]) == [span]
    print("  ok: non-executing, no holds, disjoint holds all pass through")

    print("\ntest: a span the env did not move is asked, not interpolated")
    held = _split_on_holds((0.0, 5.0, "executing", 600, 600), [(500, 700)])
    assert held[0][2] == "holding", held
    free = _split_on_holds((0.0, 5.0, "executing", 600, 600), [(800, 900)])
    assert free[0][2] == "executing", free
    print("  ok: a degenerate step range falls back to containment")

    print("\ntest: the churny 61-step holds merge into one range")
    churn = [(474 + 61 * i, 535 + 61 * i) for i in range(8)]
    assert _merge_ranges(churn, 0, 10_000) == [(474, 962)]
    # And clipped to the span that carries them.
    assert _merge_ranges(churn, 600, 700) == [(600, 700)]
    pieces = _split_on_holds((0.0, 100.0, "executing", 400, 1000), churn)
    assert [p[2] for p in pieces] == ["executing", "holding", "executing"]
    print("  ok: consecutive holds draw as one block, not eight")

    print("\ntest: a step-gap with no plan on record counts as idling")
    # agent_1 of centralized_agents12_..._045959: the team recall ended its
    # holds by assigning the status, so only the last one was ever filed.
    with tempfile.TemporaryDirectory() as run_dir:
        with open(os.path.join(run_dir, "plan_logs.json"), "w") as handle:
            json.dump({"plan_history": [
                {"agent_id": "agent_1", "specification": "ontop(a, t)",
                 "start_step": 0, "end_step": 986},
                {"agent_id": "agent_1", "specification": "ontop(b, t)",
                 "start_step": 2636, "end_step": 2840},
                {"agent_id": "agent_1", "specification": "wait_for_team(team_0)",
                 "start_step": 3492, "end_step": 4000},
                # A teammate that worked to the end has no gap of its own.
                {"agent_id": "agent_0", "specification": "ontop(c, t)",
                 "start_step": 0, "end_step": 4000},
            ]}, handle)
        found = _holds(run_dir, end_step=4000)
    # The trailing gap subsumes the one hold that was filed; merging is the
    # plotter's job and it is what the split sees.
    assert _merge_ranges(found["agent_1"], 0, 4000) == [(986, 2636), (2840, 4000)], found
    assert "agent_0" not in found, found
    print("  ok: unfiled holds are recovered from the gaps between plans")

    print("\ntest: a team's W is read off its robots, since the brain cannot record it")
    # The brain writes its own R and I -- it is the thing doing them -- but by
    # the time the team is in W the plan is handed out and nothing calls it.
    states = {
        # (timestamp, env_step, state); W from 10 to 12, then executing.
        "agent_0": [(0.0, 0, "reasoning"), (10.0, 0, "waiting"), (12.0, 0, "executing")],
        # Overlapping, and longer: the union is what the lane shows.
        "agent_1": [(0.0, 0, "reasoning"), (11.0, 0, "waiting"), (14.0, 0, "executing")],
        # A robot of another team, which must not leak into this one.
        "agent_9": [(0.0, 0, "waiting")],
    }
    spans = _team_waiting(states, ["agent_0", "agent_1"], end_time=20.0,
                          end_step=100, min_width=0.01)
    assert spans == [(10.0, 14.0)], spans
    print("  ok: the union of its members' W spans, merged")

    print("\ntest: a sub-pixel pass through W is not drawn")
    quick = {"agent_0": [(0.0, 0, "reasoning"), (10.0, 0, "waiting"),
                         (10.0001, 0, "executing")]}
    assert _team_waiting(quick, ["agent_0"], 20.0, 100, min_width=0.01) == []
    # And a team with no members on the figure contributes nothing.
    assert _team_waiting(states, [], 20.0, 100, 0.01) == []
    assert _team_waiting(states, ["missing"], 20.0, 100, 0.01) == []
    print("  ok: slivers, empty teams and unknown members all yield nothing")

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
