"""
Message broker for inter-agent communication in MA-Crafter.

Routes messages between agents by adding to their message buffers.
"""

from typing import Dict, List, Optional, Any, Union, Set
import time

from .coop2_messages import is_coop2_repair_message


class MessageBroker:
    """
    Message broker for routing messages between agents.
    
    The broker routes messages by adding them to recipient agent buffers.
    It also maintains a global log of all messages.
    """
    
    def __init__(self, agents: Dict[str, Any]):
        """
        Initialize the message broker.
        
        Args:
            agents: Dict mapping agent_id to Agent instances
        """
        self.agents = agents

        #: Declared teams, ``{team name: [member ids]}``. A team is an address
        #: in its own right: one LLM drives all of a team's robots, so what is
        #: said is said by the team and to the team, and it is delivered to
        #: every member because they are all ears of the same listener.
        self.teams: Dict[str, List[str]] = {}

        # Track all messages for analysis
        self.message_log = []
        
        # Optional wrapper reference for state change notifications
        self.wrapper = None
    
    def _confirm_interrupts(self, recipient_ids: List[str],
                            actually_interrupted: List[str]) -> None:
        """Tell each addressed team which of its members really were stopped."""
        stopped = set(actually_interrupted)
        seen: List = []
        for recipient_id in recipient_ids:
            recipient = self.agents.get(recipient_id)
            if recipient is None:
                continue
            brain = getattr(recipient, "brain", None)
            if brain is None or not hasattr(brain, "confirm_interrupts"):
                continue
            for known_brain, names in seen:
                if known_brain is brain:
                    if recipient_id in stopped:
                        names.append(recipient_id)
                    break
            else:
                seen.append((brain, [recipient_id] if recipient_id in stopped else []))
        for brain, names in seen:
            brain.confirm_interrupts(names)

    def _will_interrupt(self, recipient, message_record: Dict) -> bool:
        """Would delivering @message_record stop @recipient?

        The same predicate ``_deliver`` applies, lifted out so the interrupt set
        can be announced before the delivery loop changes anybody's state.
        """
        from .agent import AgentState

        metadata = message_record.get('metadata') or {}
        message_type = metadata.get("type") or metadata.get("message_type")
        is_execution_interrupt = (
            bool(metadata.get("interrupts_execution")) or message_type == "leader_broadcast"
        )
        is_repair_message = is_coop2_repair_message(message_record)
        # Must stay identical to the test in `_deliver`'s loop, `expected_reply`
        # included. A prediction that is merely close over-counts, and the
        # barrier then waits for a member the loop went on to skip.
        is_expected_reply = bool(metadata.get("expected_reply"))
        return not is_expected_reply and (
            recipient.state == AgentState.W
            or (recipient.state == AgentState.X
                and (is_repair_message or is_execution_interrupt))
        )

    def _partly_interruptible(self, message_record: Dict,
                              recipient_ids: List[str]) -> Set[str]:
        """Members of addressed teams that this delivery must NOT interrupt.

        A team goes to I whole or stays as it is. Returns every member of every
        addressed team for which the per-agent rule would stop some members and
        skip others -- a team already reasoning being the usual case, since R is
        not interruptible.
        """
        blocked: Set[str] = set()
        seen: List = []               # [(brain, [members addressed])]
        for recipient_id in recipient_ids:
            recipient = self.agents.get(recipient_id)
            if recipient is None:
                continue
            brain = getattr(recipient, "brain", None)
            if brain is None or not hasattr(brain, "expect_interrupt"):
                continue              # not a team: the per-agent rule stands
            for known, members in seen:
                if known is brain:
                    members.append(recipient_id)
                    break
            else:
                seen.append((brain, [recipient_id]))
        for brain, addressed in seen:
            members = list(getattr(brain, "member_ids", addressed))
            stoppable = [
                name for name in members
                if self.agents.get(name) is not None
                and self._will_interrupt(self.agents[name], message_record)
            ]
            if stoppable and len(stoppable) != len(members):
                blocked.update(members)
        return blocked

    def _announce_interrupts(self, message_record: Dict, recipient_ids: List[str],
                             blocked: Optional[Set[str]] = None) -> None:
        """Tell each addressed team which of its members this delivery will stop."""
        blocked = blocked or set()
        expected: List = []          # [(brain, [names])], keyed by identity
        for recipient_id in recipient_ids:
            recipient = self.agents.get(recipient_id)
            if recipient is None or recipient_id in blocked:
                continue
            if not self._will_interrupt(recipient, message_record):
                continue
            brain = getattr(recipient, "brain", None)
            if brain is None or not hasattr(brain, "expect_interrupt"):
                continue
            for known_brain, names in expected:
                if known_brain is brain:
                    names.append(recipient_id)
                    break
            else:
                expected.append((brain, [recipient_id]))
        for brain, names in expected:
            brain.expect_interrupt(names)

    def _deliver(self, message_record: Dict, recipient_ids: List[str],
                 timestamp: float, env_step: Optional[int]) -> None:
        """Put @message_record in each recipient's buffer, interrupting if due.

        Shared by the agent-addressed and team-addressed paths: the address
        changes, the delivery does not. ``message_record['sender']`` is whoever
        spoke -- an agent id on one path, a team name on the other -- and that
        is what the recipient sees and what its ordering primitives match on.
        """
        sender = message_record['sender']
        content = message_record['content']
        metadata = message_record.get('metadata') or {}

        # Announce the interrupt set before interrupting anybody. A team's
        # interrupt barrier has to know how many members are coming, and this
        # loop interrupts them one at a time: the first member's thread can be
        # inside handle_interrupt before the last one is even in I, and a
        # barrier that inferred the set from "who is in I right now" then closed
        # early and decided alone. Seen as three interrupt calls, and three LLM
        # round trips, for one message. Announcing first is exact rather than
        # timing-dependent, and it names only the members this delivery will
        # actually interrupt -- a member in R is skipped here as it is below, so
        # the barrier does not wait for one that was never stopped.
        # A team is interrupted as a unit or not at all. The rule below is per
        # *agent* and knows nothing about teams: W and X are stopped, R is
        # skipped. So a team with some members in W and some still in R split
        # across I and R -- seen at t=0 of
        # centralized_agents8_..._034937, agent_5/6 in I while agent_4/7 were
        # in R -- which contradicts the one thing a team is supposed to be, and
        # leaves the interrupt barrier holding a partial set.
        #
        # Nothing is lost by declining: a team with a member in R is already
        # thinking, and the message is delivered either way -- it is read at the
        # team's planning barrier, folded into the decision it was already
        # about to make. Interrupting half of it adds no information and costs a
        # split.
        blocked = self._partly_interruptible(message_record, recipient_ids)
        self._announce_interrupts(message_record, recipient_ids, blocked)
        actually_interrupted: List[str] = []

        for recipient_id in recipient_ids:
            recipient = self.agents.get(recipient_id)
            if recipient is None:
                continue
            msg_copy = {
                'timestamp': message_record['timestamp'],
                'env_step': env_step,
                'sender': sender,
                'content': content,
                'metadata': metadata,
            }
            recipient.message_buffer.append(msg_copy)
            recipient.message_history.append(msg_copy)

            # Record incoming message to agent's memory
            recipient.memory.record_message_in(
                sender=sender,
                recipients=message_record['recipients'],
                content=content,
                timestamp=timestamp,
                env_step=env_step,
            )

            # Update buffer sender indicator
            recipient.buffer_senders[sender] = True

            # Interrupt waiting agents for ordinary communication so topology
            # protocols can still coordinate before execution. Once an agent
            # is executing, ordinary messages are buffered for the next
            # reasoning point unless the sender marks the message as an
            # execution interrupt, such as COOP2 repair or centralized
            # leader planning broadcasts.
            from .agent import AgentState
            is_repair_message = is_coop2_repair_message(msg_copy)
            message_type = metadata.get("type") or metadata.get("message_type")
            is_execution_interrupt = (
                bool(metadata.get("interrupts_execution")) or message_type == "leader_broadcast"
            )
            # A reply the recipient explicitly asked for and is already
            # blocked waiting on is not an interruption. Without this, a
            # follower team's answer reached a leader team that was mid-plan
            # and split it: members still in W were interrupted, members in R
            # (inside their own planning barrier) are never interruptible,
            # and the interrupted ones then sat in the team interrupt barrier
            # for its full timeout waiting for teammates that were never
            # going to arrive.
            is_expected_reply = bool(metadata.get("expected_reply"))
            should_interrupt = (
                recipient_id not in blocked
                and not is_expected_reply
                and (
                    recipient.state == AgentState.W
                    or (recipient.state == AgentState.X
                        and (is_repair_message or is_execution_interrupt))
                )
            )
            if should_interrupt:
                before = recipient.state
                # `time.time()`, not the message's timestamp. That argument is
                # when the message was composed, on the *sender's* clock, and a
                # caller may supply it outright; stamping a state transition
                # with it put the recipient's I entry before transitions that
                # had already been appended. agent_7 in
                # centralized_agents8_..._021551 records
                # [0.0 R] [6.21 W] [0.0022 I], out of order, which the timeline
                # then draws as interrupted from t=0 to the end of the run.
                recipient.interrupt(time.time(), env_step)
                if recipient.state is not before:
                    actually_interrupted.append(recipient_id)
                # Notify wrapper of state change if available
                if self.wrapper is not None:
                    self.wrapper.notify_state_change()

        # Narrow the announcement to what the loop actually did. The set before
        # it is a prediction from each recipient's state, and the state can
        # change in between: three members slipped from W back to R between the
        # prediction and their turn in the loop, `interrupt()` is a no-op from
        # R, and the one member that really was stopped then waited out the full
        # 30 s for three that were never coming. A blocked member's poll picks
        # the narrowing up and closes the barrier.
        self._confirm_interrupts(recipient_ids, actually_interrupted)

    def register_team(self, team_name: str, member_ids: List[str]) -> None:
        """Declare @team_name as an addressable unit made of @member_ids."""
        self.teams[team_name] = list(member_ids)

    def members_of(self, team_name: str) -> List[str]:
        """The robots @team_name speaks and listens through."""
        return list(self.teams.get(team_name, []))

    def team_of(self, agent_id: str) -> Optional[str]:
        """The team @agent_id belongs to, if any."""
        for name, members in self.teams.items():
            if agent_id in members:
                return name
        return None

    def send_team_message(self, sender_team: str, recipients: Union[str, List[str]],
                          content: Any, metadata: Optional[Dict] = None,
                          timestamp: Optional[float] = None,
                          env_step: Optional[int] = None):
        """Send from one team to whole teams.

        Addressed in team names throughout -- the sender is the team, and so is
        every recipient. Addressing the members instead ("team_0 -> agent_4,
        agent_5, agent_6, agent_7") made a four-robot conversation look like
        eight separate ones and left no record of who actually spoke, since the
        robot whose id carried the message had no part in composing it.

        Delivery still reaches every member, because a team's inbox is the union
        of its robots' inboxes and an interrupt has to stop all of it.
        """
        if timestamp is None:
            timestamp = time.time()
        if isinstance(recipients, str):
            recipient_teams = (
                [t for t in self.teams if t != sender_team] if recipients == "all"
                else [recipients]
            )
        else:
            recipient_teams = list(recipients)

        recipient_agents = [
            agent_id for team in recipient_teams for agent_id in self.members_of(team)
        ]
        if env_step is None:
            for agent_id in self.members_of(sender_team):
                agent = self.agents.get(agent_id)
                if agent is not None:
                    env_step = agent.env_step
                    break

        message_record = {
            'timestamp': self._relative(timestamp, self.members_of(sender_team)),
            'env_step': env_step,
            'sender': sender_team,
            'sender_type': 'team',
            'recipients': recipient_teams,
            # Which robots it actually reached. Kept for debugging delivery; the
            # conversation itself is the line above.
            'delivered_to': recipient_agents,
            'content': content,
            'metadata': metadata or {},
        }
        self._deliver(message_record, recipient_agents, timestamp, env_step)
        self.message_log.append(message_record)
        return message_record

    def _relative(self, timestamp: float, agent_ids: List[str]) -> float:
        """@timestamp on the clock the agent state logs use."""
        for agent_id in agent_ids:
            agent = self.agents.get(agent_id)
            if agent is not None:
                return timestamp - agent._start_time
        return timestamp

    def send_message(self, sender_id: str, recipients: Union[str, List[str]], 
                    content: Any, metadata: Optional[Dict] = None,
                    timestamp: Optional[float] = None, env_step: Optional[int] = None):
        """
        Send a message from one agent to one or more recipients.
        
        Args:
            sender_id: ID of the sending agent
            recipients: Single agent ID, list of agent IDs, or 'all' for broadcast
            content: Message content (any type)
            metadata: Optional metadata dict
            timestamp: Wall clock time. If None, uses current time.
            env_step: Environment step number. If None, uses sender's current step.
        
        Returns:
            dict: The message record
        """
        if timestamp is None:
            timestamp = time.time()
        if env_step is None and sender_id in self.agents and self.agents[sender_id] is not None:
            env_step = self.agents[sender_id].env_step
        
        # Normalize recipients to a list
        if recipients == 'all':
            recipient_list = [aid for aid in self.agents.keys() if aid != sender_id]
        elif isinstance(recipients, str):
            recipient_list = [recipients]
        else:
            recipient_list = recipients
        
        # Create message record with relative timestamp
        sender_agent = self.agents.get(sender_id)
        relative_timestamp = timestamp - sender_agent._start_time if sender_agent else timestamp
        
        message_record = {
            'timestamp': relative_timestamp,
            'env_step': env_step,
            'sender': sender_id,
            'recipients': recipient_list,
            'content': content,
            'metadata': metadata or {}
        }
        
        self._deliver(message_record, recipient_list, timestamp, env_step)
        
        # Log the message
        self.message_log.append(message_record)
        
        return message_record

    def get_interrupted_agents(self) -> List[str]:
        """
        Get list of agent IDs that are currently interrupted with pending messages.
        
        Returns:
            List of agent IDs in interrupted state with messages in buffer
        """
        from .agent import AgentState
        
        interrupted = []
        for agent_id, agent in self.agents.items():
            if agent is not None and agent.state == AgentState.I and agent.has_messages():
                interrupted.append(agent_id)
        return interrupted
    
    def get_message_log(self):
        """Get all messages sent through the broker."""
        return self.message_log.copy()
    
    def reset(self):
        """Clear message log. Agent buffers/history are reset by agents themselves."""
        self.message_log = []
