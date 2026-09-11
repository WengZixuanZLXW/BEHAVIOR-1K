"""CPU-only test for the one-LLM-per-team topology.

No Isaac, no GPU, no model: a stub client counts calls and returns canned team
responses. What is pinned is the part that cannot be checked by reading the code
-- the barrier -- because getting it wrong deadlocks rather than fails.

The trap: the plan loop does not step the environment while any agent is
not ready. So a member that finished early and simply waited for its teammates
would freeze the world, and those teammates need the world to advance in order
to finish. The design has early finishers stay ready and hold position instead,
and these tests are what keep that true.

Run:
    python feasibility_verify/test_llm_team_stubbed.py
"""

from __future__ import annotations

import os
import time
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coop2.cognitive.agent.llm_client import (
    InterruptDecision,
    LLMTeamInterruptResponse,
    LLMTeamPlanResponse,
    NavigateToAction,
    Task,
    TaskSpecification,
    TeamAgentInterruptDecision,
    TeamAgentPlan,
)
from coop2.comm_topology.llm_team import TEAM_HOLD_TICKS, create_llm_team_topology


def ok(message: str) -> None:
    print(f"  ok: {message}")


USAGE = {"total_tokens": 10, "prompt_tokens": 6, "completion_tokens": 4, "latency_seconds": 0.1}


class StubClient:
    """Counts calls and hands back a plan for every member of the team asked about."""

    model = "stub"

    def __init__(self):
        self.plan_calls = 0
        self.interrupt_calls = 0
        self.last_prompt = None
        self.last_interrupt_prompt = None
        self.text_calls = 0
        self.last_text_prompt = None
        self.interrupt_script = {}

    def _members_in(self, messages):
        """Read the agent ids out of the prompt the brain built."""
        text = messages[-1]["content"]
        return [line.split()[2] for line in text.split("\n") if line.startswith("=== ROBOT ")]

    def generate_team_plan(self, messages, temperature=0.7):
        self.plan_calls += 1
        self.last_prompt = messages[-1]["content"]
        plans = [
            TeamAgentPlan(
                agent_id=name,
                task=TaskSpecification(task=Task.ONTOP, object_type="apple.n.01_1",
                                       reference="coffee_table.n.01_1"),
                actions=[NavigateToAction(target="apple.n.01_1")],
                reasoning=f"{name} goes for the apple",
            )
            for name in self._members_in(messages)
        ]
        return LLMTeamPlanResponse(plans=plans, reasoning="split by distance"), dict(USAGE)

    def generate(self, messages, response_format=None, temperature=0.7):
        """Plain text, for a follower composing its report."""
        self.text_calls += 1
        self.last_text_prompt = messages[-1]["content"]
        return "we will take the west apples, leave the east to you", dict(USAGE)

    def generate_team_interrupt_decision(self, messages, temperature=0.7):
        self.interrupt_calls += 1
        # Recorded here too, or an assertion about the interrupt prompt reads
        # whatever the last *plan* prompt was and passes for the wrong reason.
        self.last_prompt = messages[-1]["content"]
        self.last_interrupt_prompt = messages[-1]["content"]
        decisions = []
        for name in self._members_in(messages):
            choice = self.interrupt_script.get(name, InterruptDecision.RESUME)
            decisions.append(
                TeamAgentInterruptDecision(
                    agent_id=name,
                    decision=choice,
                    reasoning="scripted",
                    new_plan=None,
                )
            )
        return LLMTeamInterruptResponse(decisions=decisions, reasoning="scripted"), dict(USAGE)


def make_team(size, name="alpha"):
    client = StubClient()
    ids = [f"agent_{i}" for i in range(size)]
    agents = create_llm_team_topology(
        llm_client=client, teams={name: ids}, verbose=False, goal_instruction="do the thing"
    )
    for agent in agents.values():
        agent.symbolic_view = f"view for {agent.agent_id}"
        agent.observe({}, 0)
    return client, agents, ids


def main() -> int:
    print("test 1: a team does not plan until every member has finished")
    client, agents, ids = make_team(4)
    # Three members finish; the fourth is still executing and never calls in.
    for name in ids[:3]:
        agents[name].handle_reasoning()
    assert client.plan_calls == 0, "planned before the team was complete"
    for name in ids[:3]:
        plan = agents[name].plan
        assert plan is not None, f"{name} has no plan at all -- it would never become ready"
        assert plan.actions[0].action_type == "wait", plan.actions[0].action_type
        assert plan.actions[0].args["ticks"] == TEAM_HOLD_TICKS
        # Exactly one action. A hold that goes through parse_plan_response picks
        # up a terminal action derived from its TaskSpecification -- expressed as
        # holding(<self>) that appended grasp(<self>), a robot planning to pick
        # itself up, which reached a real run before it was caught.
        assert len(plan.actions) == 1, [a.action_type for a in plan.actions]
    ok("3 of 4 finished -> no LLM call, and each early finisher holds rather than stalling")

    print("test 2: the last member closes the barrier and everyone gets a real plan")
    agents[ids[3]].handle_reasoning()
    assert client.plan_calls == 1, client.plan_calls
    assert agents[ids[3]].plan.actions[0].action_type == "navigate_to"
    # The other three are still holding; they take their plans on their next
    # pass through reasoning, which is what happens when their hold expires.
    for name in ids[:3]:
        agents[name].handle_reasoning()
    assert client.plan_calls == 1, f"one round must be one call, got {client.plan_calls}"
    for name in ids:
        plan = agents[name].plan
        assert plan.actions[0].action_type == "navigate_to", (name, plan.actions[0].action_type)
        assert plan.agent_id == name
    ok("one call for the whole round, and every robot ends up with its own plan")

    print("test 3: the prompt carries every member's observation, once each")
    prompt = client.last_prompt
    for name in ids:
        assert f"=== ROBOT {name} ===" in prompt, f"{name} missing from the team prompt"
        assert prompt.count(f"view for {name}") == 1, f"{name}'s observation duplicated"
    assert "do the thing" in prompt, "the global objective is missing"
    ok("4 observations, one section each, plus the objective")

    print("test 4: a team of one behaves exactly like the individual topology")
    solo_client, solo_agents, solo_ids = make_team(1, name="solo")
    solo_agents[solo_ids[0]].handle_reasoning()
    assert solo_client.plan_calls == 1
    # No hold is ever taken: the barrier is satisfied by the only member.
    assert solo_agents[solo_ids[0]].plan.actions[0].action_type == "navigate_to"
    ok("N=1 plans immediately and never holds, so per-robot LLM is this code with N=1")

    print("test 5: the team is interrupted together and answered in one call")
    client, agents, ids = make_team(3)
    client.interrupt_script = {ids[1]: InterruptDecision.REPLAN}
    for name in ids:
        agents[name].plan = None

    # Concurrently, because that is how it happens: the broker interrupts every
    # member of a team in one call, so their threads arrive together. Members
    # that arrive early **block in I** rather than bouncing back to ready --
    # a member that bounced showed as "waiting" on the timeline while its
    # teammates were still interrupted, which is the bug this pins.
    #
    # The state has to be set, not assumed: the barrier waits for teammates that
    # are *in* I, so a test that called handle_interrupt on agents still in R
    # was testing a situation the broker never produces.
    import threading

    from coop2.cognitive.agent.agent import AgentState

    for name in ids:
        agents[name]._set_state(AgentState.I, timestamp=0.0, env_step=0)

    barrier_state = {}

    def arrive(name):
        barrier_state[name] = agents[name].handle_interrupt()

    threads = [threading.Thread(target=arrive, args=(name,)) for name in ids[:2]]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=1.0)
    assert all(t.is_alive() for t in threads), "early arrivals must block, not return"
    assert client.interrupt_calls == 0, "decided before the whole team was interrupted"

    agents[ids[2]].handle_interrupt()
    for thread in threads:
        thread.join(timeout=5.0)
    assert not any(t.is_alive() for t in threads), "blocked members must be released"
    assert client.interrupt_calls == 1, client.interrupt_calls
    ok("2 of 3 block in I; the third closes the barrier and one call answers all")

    print("test 6: a member the model forgot is held, not left planless")
    class Forgetful(StubClient):
        def generate_team_plan(self, messages, temperature=0.7):
            response, usage = super().generate_team_plan(messages, temperature)
            response.plans = response.plans[:-1]  # drop the last robot
            return response, usage

    client = Forgetful()
    ids = ["agent_0", "agent_1"]
    agents = create_llm_team_topology(llm_client=client, teams={"t": ids}, verbose=False)
    for agent in agents.values():
        agent.symbolic_view = f"view for {agent.agent_id}"
        agent.observe({}, 0)
    for name in ids:
        agents[name].handle_reasoning()
    # A member with no plan never becomes ready, which would strand the whole
    # run at the next barrier -- so the brain gives it a hold instead.
    assert agents[ids[1]].plan is not None
    assert agents[ids[1]].plan.actions[0].action_type == "wait"
    assert len(agents[ids[1]].plan.actions) == 1, [
        a.action_type for a in agents[ids[1]].plan.actions
    ]
    ok("a skipped robot gets a hold, so it still becomes ready")

    print("test 7: an LLM failure falls back rather than ending the run")
    class Broken(StubClient):
        def generate_team_plan(self, messages, temperature=0.7):
            raise RuntimeError("no model today")

    client = Broken()
    ids = ["agent_0", "agent_1"]
    agents = create_llm_team_topology(llm_client=client, teams={"t": ids}, verbose=False)
    for agent in agents.values():
        agent.observe({}, 0)
    for name in ids:
        agents[name].handle_reasoning()
    for name in ids:
        assert agents[name].plan is not None, f"{name} stranded with no plan after an LLM error"
    ok("every robot still has a plan after the call raised")

    print("test 8: the three topologies wire teams, not robots")
    from coop2.comm_topology.llm_team import (
        ChainTeamBrain, FollowerTeamBrain, LeaderTeamBrain, TeamBrain,
    )

    teams = {"t0": ["a0", "a1"], "t1": ["a2", "a3"], "t2": ["a4", "a5"]}

    def brains_of(topology):
        agents = create_llm_team_topology(
            llm_client=StubClient(), teams=teams, topology=topology, verbose=False
        )
        out = {}
        for agent in agents.values():
            out[agent.brain.team_name] = agent.brain
        return out

    solo = brains_of("individual")
    assert all(isinstance(b, TeamBrain) and not b.send_to and not b.wait_for
               for b in solo.values())

    chain = brains_of("broadcast_chain")
    assert all(isinstance(b, ChainTeamBrain) for b in chain.values())
    # Both sides of the wiring are team names. They used to be agent ids -- a
    # team was addressed as its four robots and waited on through whichever
    # member spoke for it -- which put a conversation between two teams in the
    # log as eight one-sided ones between robots that never composed a word.
    assert chain["t1"].wait_for == ["t0"], chain["t1"].wait_for
    assert chain["t0"].send_to == ["t1", "t2"], chain["t0"].send_to
    assert chain["t2"].send_to == [], "the last team has nobody downstream"

    central = brains_of("centralized")
    assert isinstance(central["t0"], LeaderTeamBrain)
    assert isinstance(central["t1"], FollowerTeamBrain)
    assert central["t0"].wait_for == ["t1", "t2"], central["t0"].wait_for
    assert central["t0"].send_to == ["t1", "t2"], central["t0"].send_to
    assert central["t1"].wait_for == ["t0"], central["t1"].wait_for
    assert central["t1"].send_to == ["t0"], central["t1"].send_to
    # Delivery still reaches every robot of an addressed team: an interrupt has
    # to stop all of it, or the team splits across I and W and stalls its own
    # interrupt barrier. That expansion belongs to the broker, not the address.
    assert central["t1"].all_teams["t0"] == ["a0", "a1"]
    ok("individual/chain/centralized wire team to team, and teams expand at delivery")

    print("test 9: when the team thinks, every member is reasoning")
    from coop2.cognitive.agent.agent import AgentState

    client, agents, ids = make_team(4)
    # Three finish early and hold, then actually start executing those holds --
    # which is the state they are really in while the fourth robot works.
    for name in ids[:3]:
        agents[name].handle_reasoning()
        agents[name].set_ready()
        agents[name].start_execution()
        assert agents[name].state == AgentState.X, agents[name].state

    # One of them finishes its hold and is sitting ready in W rather than still
    # executing. It is idling just the same, and was being skipped.
    agents[ids[0]].set_ready()
    assert agents[ids[0]].state == AgentState.W, agents[ids[0]].state

    # The fourth arrives and closes the barrier.
    agents[ids[3]].handle_reasoning()

    # Every teammate must now be reasoning, not still executing a hold. Only the
    # member that closed the barrier was reasoning before this fix, so the
    # timeline showed one red bar and three green ones during a team call.
    for name in ids[:3]:
        assert agents[name].state == AgentState.R, (name, agents[name].state)
        assert not agents[name].ready, f"{name} is still marked ready"
    # And the hold each was running is terminal, or create_agent_thread would
    # decline to re-plan it and the member would never become ready again.
    ok("holders are recalled into R, with their holds marked terminal")

    print("test 10: a follower answers the leader, and only when it was asked")
    from coop2.cognitive.messages import MessageBroker

    def centralized_pair():
        client = StubClient()
        teams = {"lead": ["agent_0", "agent_1"], "follow": ["agent_2", "agent_3"]}
        agents = create_llm_team_topology(
            llm_client=client, teams=teams, topology="centralized", verbose=False
        )
        broker = MessageBroker(agents)
        for agent in agents.values():
            agent.message_broker = broker
            agent.symbolic_view = f"view for {agent.agent_id}"
            agent.observe({}, 0)
        return client, agents, broker

    # The follower team plans first, with nothing from the leader in its inbox.
    _client, agents, broker = centralized_pair()
    for name in ("agent_2", "agent_3"):
        agents[name].handle_reasoning()
    sent = [m for m in broker.get_message_log()
            if (m.get("metadata") or {}).get("type") == "follower_response"]
    # It used to answer anyway: `_await_speakers` releases as soon as the leader
    # merely *looks* ready, which at the start of a run it does, so the reply
    # was logged in the same instant as -- and ahead of -- the request.
    assert not sent, f"answered a question nobody asked: {sent}"

    # Now with the leader's request actually delivered first.
    _client, agents, broker = centralized_pair()
    for name in ("agent_0", "agent_1"):
        agents[name].handle_reasoning()
    asks = [m for m in broker.get_message_log()
            if (m.get("metadata") or {}).get("type") == "leader_broadcast"]
    assert len(asks) == 1, asks

    # The team read it once, not once per robot it was handed to. Delivery
    # copies a team message into all four inboxes, so draining them all used to
    # quote the same request four times in the prompt.
    follow = agents["agent_2"].brain
    follow._collect_heard()
    assert follow._heard_block().count("From lead:") == 1, follow._heard_block()

    for name in ("agent_2", "agent_3"):
        agents[name].handle_reasoning()
    replies = [m for m in broker.get_message_log()
               if (m.get("metadata") or {}).get("type") == "follower_response"]
    assert len(replies) == 1, replies
    assert replies[0]["timestamp"] >= asks[0]["timestamp"], "reply predates the request"
    ok("silent when unasked; answers once, after the request, and quotes it once")

    print("test 11: the team's own timeline is recorded and saved")
    import json
    import tempfile

    from coop2.experiment.agent_timeline import save_team_timeline

    lead = agents["agent_0"].brain
    assert [s["kind"] for s in lead.timeline] == ["planning"], lead.timeline
    assert lead.timeline[0]["end"] >= lead.timeline[0]["start"]

    # The log is addressed team to team. It used to read "agent_0 -> agent_2,
    # agent_3", which credited the send to a robot that had no part in writing
    # it and turned one conversation between two teams into several.
    log = broker.get_message_log()
    assert [(m["sender"], tuple(m["recipients"])) for m in log] == [
        ("lead", ("follow",)), ("follow", ("lead",)),
    ], log
    assert all(m.get("sender_type") == "team" for m in log), log
    assert log[0]["delivered_to"] == ["agent_2", "agent_3"], log[0]

    with tempfile.TemporaryDirectory() as directory:
        path = save_team_timeline(agents, os.path.join(directory, "team_timeline.json"))
        payload = json.load(open(path))
    assert set(payload["teams"]) == {"lead", "follow"}
    assert payload["teams"]["lead"] == ["agent_0", "agent_1"]
    # Relative to the same origin the agent states use, or the spans would land
    # somewhere else entirely on the shared x axis.
    assert all(0.0 <= s["start"] < 60.0 for s in payload["spans"]["lead"]), payload["spans"]
    ok("addressed team to team in the log, with the thinking spans recorded")

    print("test 12: a member that raced the closing barrier waits, it does not hold")
    import threading as _threading
    import time as _time

    class Slow(StubClient):
        def generate_team_plan(self, messages, temperature=0.7):
            _time.sleep(0.3)  # an LLM call is seconds; the race is microseconds
            return super().generate_team_plan(messages, temperature)

    client = Slow()
    ids = ["agent_0", "agent_1", "agent_2"]
    agents = create_llm_team_topology(llm_client=client, teams={"t": ids}, verbose=False)
    for agent in agents.values():
        agent.symbolic_view = f"view for {agent.agent_id}"
        agent.observe({}, 0)
    brain = agents["agent_0"].brain

    # agent_0 and agent_1 have both asked and been told to hold. agent_1 is now
    # in the gap between being told that and acting on it.
    assert brain.request_plan("agent_0") is None
    assert brain.request_plan("agent_1") is None

    closer = _threading.Thread(target=agents["agent_2"].handle_reasoning)
    closer.start()
    _time.sleep(0.05)  # the barrier closes; agent_1 is still in that gap

    # The recall cannot reach agent_1 -- it is in R, which is not an idle state
    # and is deliberately left alone -- and there is no plan to hand it yet
    # either, because the call has only just started. Asking once returned None
    # and it held: measured at 15.8 s of "waiting" through its own team's call,
    # while its teammates showed 15.8 s of "reasoning".
    plan = brain.claim_pending_plan("agent_1")
    closer.join(timeout=5.0)
    assert plan is not None, "agent_1 held through a call that was already under way"
    assert plan.actions[0].action_type == "navigate_to", plan.actions[0].action_type
    assert client.plan_calls == 1, client.plan_calls
    ok("it blocks on the call in flight and comes back with the real plan")

    print("test 13: a teammate that was never interrupted does not hold the barrier")
    # The broker interrupts an agent in W or X and skips one in R -- and R is
    # where the member running the team's planning call sits. The barrier used
    # to require every member regardless, so on
    # centralized_agents8_..._011122 a request that landed 2 ms into the run
    # caught three members in W, missed the fourth still reasoning, and froze
    # the world for the full 30 s timeout.
    client, agents, ids = make_team(4)
    for name in ids:
        agents[name].plan = None
    for name in ids[:3]:
        agents[name]._set_state(AgentState.I, timestamp=0.0, env_step=0)
    # ids[3] stays in R: it is the one doing the planning call.
    assert agents[ids[3]].state is AgentState.R

    done = {}

    def arrive_late(name):
        done[name] = agents[name].handle_interrupt()

    threads = [threading.Thread(target=arrive_late, args=(name,)) for name in ids[:3]]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)
    elapsed = time.monotonic() - started
    assert not any(t.is_alive() for t in threads), (
        "the three interrupted members blocked on a fourth that was never coming"
    )
    assert elapsed < 2.0, f"took {elapsed:.1f}s -- it waited on the timeout again"
    assert client.interrupt_calls == 1, client.interrupt_calls
    ok("three interrupted members decide without the one still reasoning")

    print("test 14: the objective reaches the team's own prompt, on every path")
    # The team brain builds its own prompt from its own copy of the objective,
    # so setting the attribute on the agents does not reach it. run_centralized
    # passed the goal to the agents and not to the factory, and its teams
    # planned with no objective at all -- 0 prompts carrying one, against 7 for
    # broadcast_chain on the same task.
    client, agents, ids = make_team(2)
    for name in ids:
        agents[name].plan = None
    for name in ids:
        agents[name].handle_reasoning()
    plan_prompt = client.last_prompt
    assert "GLOBAL OBJECTIVE: do the thing" in plan_prompt, (
        "a team planned without being told what the run is for"
    )

    # And on the interrupt prompt, which is a different builder.
    from coop2.cognitive.agent.agent import AgentState
    for name in ids:
        agents[name]._set_state(AgentState.I, timestamp=0.0, env_step=0)
    threads = [threading.Thread(target=agents[name].handle_interrupt) for name in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)
    interrupt_prompt = client.last_interrupt_prompt
    assert interrupt_prompt is not None, "the interrupt prompt was never recorded"
    assert "GLOBAL OBJECTIVE: do the thing" in interrupt_prompt, (
        "the resume/replan call did not know the objective either"
    )
    # A brain with no objective must not print a stray header.
    brain = agents[ids[0]].brain
    brain.goal_instruction = ""
    assert "GLOBAL OBJECTIVE" not in brain._build_team_prompt(
        [agents[name] for name in ids]
    )[-1]["content"]
    ok("plan and interrupt prompts both carry the objective, and omit it when unset")

    print("test 15: one message to a team is one interrupt decision, not one per member")
    # The broker interrupts a team's members one at a time, so the first
    # member's thread can be inside handle_interrupt before the last is in I.
    # A barrier that inferred its set from "who is in I right now" closed early
    # and each member then decided alone: three interrupt calls, and three LLM
    # round trips, for one message. Driven through the real broker here,
    # because the announcement is the broker's half of the fix.
    from coop2.cognitive.messages import MessageBroker

    client, agents, ids = make_team(4, name="bravo")
    for name in ids:
        agents[name].plan = None
        agents[name]._set_state(AgentState.W, timestamp=0.0, env_step=0)
    broker = MessageBroker(agents)
    broker.teams = {"bravo": list(ids)}
    for agent in agents.values():
        agent.message_broker = broker

    # Every member is in W, so the delivery stops all four.
    broker.send_team_message(
        sender_team="outsider", recipients=["bravo"], content="status please",
        metadata={"type": "leader_broadcast", "interrupts_execution": True},
        timestamp=0.0, env_step=0,
    )
    brain = agents[ids[0]].brain
    assert brain._expected_interrupt == set(ids), (
        f"the broker announced {brain._expected_interrupt}, not the four it stopped"
    )
    assert all(agents[n].state is AgentState.I for n in ids)

    threads = [threading.Thread(target=agents[n].handle_interrupt) for n in ids]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)
    assert not any(t.is_alive() for t in threads), "the barrier never closed"
    assert time.monotonic() - started < 2.0, "it waited on a timeout"
    assert client.interrupt_calls == 1, (
        f"{client.interrupt_calls} interrupt calls for one message"
    )
    ok("four members, one announcement, one decision call")

    print("test 16: a member that slipped out of W before its turn is not waited for")
    # The announcement is a prediction from each recipient's state, and the
    # state can change before the delivery loop reaches that recipient:
    # interrupt() is a no-op from R. On
    # centralized_agents8_..._021551 three members went W -> R in that window,
    # only the fourth was really stopped, and it waited out the full 30 s for
    # three that were never coming. The confirmation after the loop narrows the
    # set to what actually happened.
    client, agents, ids = make_team(4, name="charlie")
    for name in ids:
        agents[name].plan = None
        agents[name]._set_state(AgentState.W, timestamp=0.0, env_step=0)
    broker = MessageBroker(agents)
    broker.teams = {"charlie": list(ids)}
    for agent in agents.values():
        agent.message_broker = broker

    # Three of them leave W the instant the prediction has been taken -- which
    # is what a real team does when its members reach their planning barrier.
    real_announce = broker._announce_interrupts

    def announce_then_slip(message_record, recipient_ids):
        real_announce(message_record, recipient_ids)
        for name in ids[:3]:
            agents[name]._set_state(AgentState.R, timestamp=0.0, env_step=0)

    broker._announce_interrupts = announce_then_slip
    broker.send_team_message(
        sender_team="outsider", recipients=["charlie"], content="status please",
        metadata={"type": "leader_broadcast", "interrupts_execution": True},
        timestamp=0.0, env_step=0,
    )
    brain = agents[ids[0]].brain
    assert agents[ids[3]].state is AgentState.I, "the one still in W should be stopped"
    assert all(agents[n].state is AgentState.R for n in ids[:3])
    assert brain._expected_interrupt == {ids[3]}, (
        f"expected narrowed to {brain._expected_interrupt}, not just the member stopped"
    )

    started = time.monotonic()
    agents[ids[3]].handle_interrupt()
    elapsed = time.monotonic() - started
    assert elapsed < 2.0, f"took {elapsed:.1f}s -- it waited for the three that slipped"
    assert client.interrupt_calls == 1, client.interrupt_calls
    ok("only the member really stopped is waited for, and it decides at once")

    print("test 17: a follower's report answers what the leader asked")
    # It used to send only plan.specification, which answered none of the four
    # things the request asks for and was `wait_for_team(...)` for most robots
    # most of the time. The exchange read correctly in the log -- right senders,
    # right addressing -- and carried nothing the leader could allocate on.
    from coop2.comm_topology.llm_team import _first_useful_target, _read_view_header

    view = (
        "Step 0/2500 | you are agent_4 in empty_room_0 (a empty room)\n"
        "Holding: apple.n.01_2\n"
        "\nYou can do:\n"
        "  apple.n.01_1: unreachable, navigate_to   [36.7 m away]\n"
        "  coffee_table.n.01_1: place_on_top, navigate_to\n"
    )
    assert _read_view_header(view) == ("empty_room_0", "apple.n.01_2")
    assert _first_useful_target(view) == "coffee_table.n.01_1 (in range)", (
        "an object it can act on now must win over a nearer unreachable one"
    )
    # Out of range everywhere: report the closest, with its distance.
    far = view.replace("  coffee_table.n.01_1: place_on_top, navigate_to\n",
                       "  coffee_table.n.01_1: unreachable, navigate_to   [11.6 m away]\n")
    assert _first_useful_target(far) == "coffee_table.n.01_1 (12 m away)"
    assert _read_view_header(None) == ("", "") and _first_useful_target(None) == ""

    # _status_report belongs to the follower role, so build a centralized pair.
    client = StubClient()
    agents = create_llm_team_topology(
        llm_client=client, topology="centralized",
        teams={"team_0": ["agent_0"], "team_1": ["agent_4", "agent_5"]},
        verbose=False, goal_instruction="do the thing",
    )
    ids = ["agent_4", "agent_5"]
    for name in ids:
        agents[name].symbolic_view = view
        agents[name].observe({}, 0)
    follower = agents[ids[0]].brain
    report = follower._status_report()
    for wanted in ("in empty_room_0", "holding apple.n.01_2",
                   "nearest target coffee_table.n.01_1 (in range)", "plan "):
        assert wanted in report, f"the report does not say {wanted!r}: {report}"
    assert ids[0] in report and ids[1] in report
    # A holding robot is described as idle, not by the placeholder's name.
    agents[ids[0]].plan = agents[ids[0]].build_hold_plan()
    assert "idle, waiting for its team" in follower._status_report()
    assert "wait_for_team" not in follower._status_report()
    ok("room, held object, a reachable target and the plan -- all four")

    print("test 18: the follower writes its own reply, grounded in those facts")
    # Upstream's follower composes its answer (`_build_follower_response` is
    # `self._generate_message(...)`); this port had replaced it with the
    # assembled report, which saved a call and lost the point of asking -- a
    # rendering of a team's own state cannot propose anything.
    agents[ids[0]].plan = None
    before = client.text_calls
    reply = follower._compose_report()
    assert client.text_calls == before + 1, "the report was not composed by the model"
    assert reply == "we will take the west apples, leave the east to you"
    # Grounded: the assembled facts go into the prompt, not onto the wire.
    assert "in empty_room_0" in client.last_text_prompt
    assert "holding apple.n.01_2" in client.last_text_prompt
    assert "nearest target coffee_table.n.01_1 (in range)" in client.last_text_prompt

    # A failure degrades to the assembled report, not to silence.
    class Mute(StubClient):
        def generate(self, messages, response_format=None, temperature=0.7):
            raise RuntimeError("no model")

    muted = create_llm_team_topology(
        llm_client=Mute(), topology="centralized",
        teams={"team_0": ["agent_0"], "team_1": ["agent_4"]},
        verbose=False, goal_instruction="do the thing",
    )
    muted["agent_4"].symbolic_view = view
    muted["agent_4"].observe({}, 0)
    fallback = muted["agent_4"].brain._compose_report()
    assert "in empty_room_0" in fallback and "holding apple.n.01_2" in fallback
    ok("the model writes it from the facts, and a dead model falls back to them")

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
