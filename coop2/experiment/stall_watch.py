"""Name the agent a stalled run is waiting for.

The plan loop waits for every agent to be ready, and several paths can leave one
that never will be -- most of them silently. ``create_agent_thread`` matches
``I`` and ``R and needs_new_plan()``; anything else falls through its ``else:
return`` without calling ``set_ready``, so the runner respawns a thread every
50 ms that dies at once and the episode stops advancing with no error, no
traceback, and a few per cent of a core of thread churn.

That has now cost three debugging sessions. The first two produced no evidence
beyond "no progress and no open socket"; the third was solved by a SIGUSR1 stack
dump showing the main thread in ``wait_for_state_change`` with no agent thread
alive -- which said where the loop was but not *who* it was waiting for. This
says who, and why.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Set

__all__ = ["StallWatch"]

#: Seconds the same agents may stay not-ready before the loop reports them.
#: Generous on purpose: a plan call is a model round trip, measured at about
#: 4 s, and a team's barrier can legitimately hold a member across several.
DEFAULT_STALL_SECONDS = 25.0


class StallWatch:
    """Report the not-ready set when it stops changing.

    Call :meth:`check` once per pass of the wait loop. Cheap enough for that:
    one clock read and one set comprehension.
    """

    def __init__(self, agents: Dict[str, Any], seconds: float = DEFAULT_STALL_SECONDS):
        self.agents = agents
        self.seconds = float(seconds)
        self._frozen: Optional[Set[str]] = None
        self._since = 0.0
        self._reports = 0

    def _not_ready(self) -> Set[str]:
        return {
            agent_id for agent_id, agent in self.agents.items()
            if agent is not None and not agent.ready
        }

    def check(self) -> None:
        pending = self._not_ready()
        if not pending:
            self._frozen = None
            return
        now = time.monotonic()
        if pending != self._frozen:
            # Progress, of a kind: a different agent is holding things up, so
            # the clock starts again.
            self._frozen = pending
            self._since = now
            return
        if now - self._since < self.seconds:
            return
        self._report(pending, now - self._since)
        # Reset rather than latch, so a genuinely slow round reports once and a
        # real stall keeps reporting instead of going quiet after the first.
        self._since = now
        self._reports += 1

    def _report(self, pending: Set[str], waited: float) -> None:
        print(f"\n[stall] {len(pending)} agent(s) not ready for {waited:.0f}s "
              f"-- the loop cannot advance until they are:")
        for agent_id in sorted(pending):
            print(f"    {agent_id}: {self.describe(self.agents.get(agent_id))}")
        print("[stall] an agent in R whose plan is not terminal is the usual "
              "cause: create_agent_thread matches neither branch and never "
              "calls set_ready. kill -USR1 for stacks.\n")

    @staticmethod
    def describe(agent: Any) -> str:
        """One line of why this agent is not ready."""
        if agent is None:
            return "missing"
        state = getattr(getattr(agent, "state", None), "value", "?")
        plan = getattr(agent, "plan", None)
        if plan is None:
            plan_text = "no plan"
        else:
            status = getattr(getattr(plan, "status", None), "value", plan and "?")
            plan_text = f"plan {getattr(plan, 'specification', '?')} [{status}]"
        try:
            wants = agent.needs_new_plan()
        except Exception:  # noqa: BLE001 - a diagnostic must not raise
            wants = "?"
        return f"state={state} ready={getattr(agent, 'ready', '?')} {plan_text} needs_new_plan={wants}"
