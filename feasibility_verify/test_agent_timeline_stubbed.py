"""CPU-only test for the hold shading on the agent timeline.

A `wait_for_team` hold and a real primitive are both FSM state X, and
`_coalesce` routinely folds them into one bar, so the figure only tells the
truth if that bar is cut where the hold begins.
"""
from __future__ import annotations
import sys

sys.path.insert(0, "/home/zixuanwe/Desktop/BEHAVIOR-1K")
from coop2.experiment.agent_timeline import _merge_ranges, _split_on_holds


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

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
