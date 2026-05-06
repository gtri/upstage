# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test task networks."""
import pytest

from upstage_des.api import (
    Actor,
    Any,
    DecisionTask,
    EnvironmentContext,
    Event,
    Get,
    InterruptStates,
    LinearChangingState,
    Put,
    ResourceHold,
    State,
    Task,
    TaskLinks,
    TaskNetworkFactory,
    Wait,
    WaitUntil,
    add_stage_variable,
    TASK_GEN,
    SIMPY_GEN,
    SimulationError,
    UpstageError,
    TaskTransition,
    TerminalTask,
    get_entities_by_class,
    get_stage,
    SimulationEnd,
)
from upstage_des.utils.task_net_viz import to_dot, to_mermaid


class Insect(Actor):
    hunger: float = LinearChangingState(default=1.0, recording=True).create()


class InsectInterrupt(Task):
    def on_interrupt(self, *, actor: Insect, cause: str) -> InterruptStates:
        if cause == "attack":
            self.clear_actor_task_queue(actor)
            self.set_actor_task_queue(actor, ["Defend"])
            return InterruptStates.END
        raise SimulationError(f"Unexpected cause: {cause}")


class Search(InsectInterrupt):
    def task(self, *, actor: Insect) -> TASK_GEN:
        # activate hunger to change over time
        actor.activate_linear_state(
            "hunger",
            rate=-0.01,
            task=self, # This has to be the task object
        )
        no_food_time = actor.get_time_for_state_goal("hunger", 0.0)
        assert no_food_time is not None
        no_food_event = WaitUntil(no_food_time)
        search_event = Wait.from_random_uniform(0.5, 2.0)
        yield Any(no_food_event, search_event)
        actor.deactivate_all_states(task=self)
        if no_food_event.is_complete():
            self.set_actor_task_queue(actor, ["End"])
        else:
            self.set_actor_task_queue(actor, ["Eat"])
        

class Eat(InsectInterrupt):
    def task(self, *, actor: Insect) -> TASK_GEN:
        actor.activate_linear_state(
            "hunger",
            rate=0.1,
            task=self,
        )
        satiated_time = actor.get_time_for_state_goal("hunger", 1.0)
        assert satiated_time is not None
        yield WaitUntil(satiated_time)
        actor.deactivate_linear_state("hunger", task=self)


class Sleep(InsectInterrupt):
    def task(self, *, actor: Insect) -> TASK_GEN:
        yield Wait(3.0)
        actor.hunger -= 0.3


class Defend(Task):
    def task(self, *, actor: Insect) -> TASK_GEN:
        yield Wait(0.2)
        if actor.hunger < 0.3:
            actor.hunger = 0.0
            self.set_actor_task_queue(actor, ["End"])
        else:
            # Lose hunger, but win
            actor.hunger -= 0.2


class Think(DecisionTask):
    def make_decision(self, *, actor: Insect) -> None:
        if actor.hunger > 0.7:
            # we can sleep!
            self.set_actor_task_queue(actor, ["Sleep"])
        else:
            self.set_actor_task_queue(actor, ["Search"])

class End(TerminalTask):...


class Swatter(Actor): ...


class SwatInsects(Task):
    def task(self, *, actor: Swatter) -> TASK_GEN:
        # Looping task for swatting insects
        yield Wait.from_random_uniform(2.1, 4.3)
        insects: list[Insect] = get_entities_by_class("Insect")
        insects = [x for x in insects if x.hunger > 0]
        if not insects:
            raise SimulationEnd("No more insects")
        choice = get_stage().random.choice(insects)
        choice.interrupt_network("InsectLife", cause="attack")


def _make_sim(n_insects: int) -> tuple[list[Insect], Swatter]:
    """Make a sim once inside a context."""
    tnf = TaskNetworkFactory(
        name="InsectLife",
        task_links={
            Think: TaskLinks(None, [Search, Sleep]),
            Eat: TaskLinks(Think, [Think, Defend]),
            Sleep: TaskLinks(Think, [Think]),
            End: TaskLinks(None, []),
            Search: TaskLinks(None, [Eat, Defend, End]),
            Defend: TaskLinks(Think, [Think, End]),
        }
    )

    tnfs = TaskNetworkFactory.from_single_looping(
        "SwatThatInsect", SwatInsects,
    )

    insects = [
        Insect(
            name=f"Ant {i}",            
        )
        for i in range(n_insects)
    ]
    for ins in insects:
        net = tnf.make_network()
        ins.add_task_network(net)
        ins.start_network_loop(net.name, "Think")
    
    swatter = Swatter(name="Swat")
    net = tnfs.make_network()
    swatter.add_task_network(net)
    swatter.start_network_loop(net.name, "SwatInsects")
    return insects, swatter


def test_building_network() -> None:
    with EnvironmentContext() as env:
        insects, swatter = _make_sim(2)
        try:
            env.run()
        except SimulationEnd:
            ...
        print(env.now)

test_building_network()

# def test_running_simple_network() -> None:
#     with EnvironmentContext() as env:
#         actor = _build_test(env)
#         task_fact = TaskNetworkFactory(
#             "plane_net",
#             task_classes,
#             task_links,
#         )
#         net = task_fact.make_network()

#         assert str(net) == "Task network: plane_net"

#         # build arguments for the task list
#         task_name_list = [
#             "LandingLocationSelection",
#             "LandingLocationPrep",
#             "Fly",
#             "LandingCheck",
#             "Land",
#             "MaintenanceWait",
#         ]

#         # tell the actor the queue its getting
#         actor.add_task_network(net)
#         actor.set_task_queue("plane_net", task_name_list)

#         # run the queue with the network
#         net.loop(actor=actor)
#         env.run()

#         base = actor.get_knowledge("base")
#         base2 = actor.stage.world.bases[0]
#         assert base is base2, "Wrong base selected"
#         assert len(actor._knowledge) == 1, "Too much knowledge left"
#         assert pytest.approx(actor.fuel, abs=0.01) == 86.199
#         assert actor.code == 0, "Wrong MX code"


# def test_interrupting_network() -> None:
#     with EnvironmentContext() as env:
#         actor = _build_test(env)
#         task_fact = TaskNetworkFactory(
#             "plane_net",
#             task_classes,
#             task_links,
#         )
#         net = task_fact.make_network()

#         # build arguments for the task list
#         task_name_list = [
#             "LandingLocationSelection",
#             "LandingLocationPrep",
#             "Fly",
#             "LandingCheck",
#             "Land",
#             "MaintenanceWait",
#         ]

#         # tell the actor the queue its getting
#         actor.add_task_network(net)
#         actor.set_task_queue("plane_net", task_name_list)

#         # create a process that interrupts the plane during different times
#         def interrupting_proc(
#             env: Environment, actor: Aircraft, interrupt_time: float
#         ) -> SIMPY_GEN:
#             yield env.timeout(interrupt_time)
#             # get the process
#             network = actor._task_networks["plane_net"]
#             assert network._current_task_proc is not None
#             network._current_task_proc.interrupt(cause="a reason")

#         # run the queue with the network
#         net.loop(actor=actor)
#         env.process(interrupting_proc(env, actor, 1.0))
#         env.run()

#         # the plane should land still
#         assert actor._task_queue["plane_net"] == [], "Actor had tasks left"
#         assert actor.code == 0, "Actor didn't get maintained"


# def test_interrupting_network_with_cause() -> None:
#     with EnvironmentContext() as env:
#         actor = _build_test(env)
#         task_fact = TaskNetworkFactory(
#             "plane_net",
#             task_classes,
#             task_links,
#         )
#         net = task_fact.make_network()

#         # build arguments for the task list
#         task_name_list = [
#             "LandingLocationSelection",
#             "LandingLocationPrep",
#             "Fly",
#             "LandingCheck",
#             "Land",
#             "MaintenanceWait",
#         ]

#         # tell the actor the queue its getting
#         actor.add_task_network(net)
#         actor.set_task_queue("plane_net", task_name_list)

#         # create a process that interrupts the plane during different times
#         def interrupting_proc(
#             env: Environment, actor: Aircraft, interrupt_time: float
#         ) -> SIMPY_GEN:
#             yield env.timeout(interrupt_time)
#             # get the process
#             # network = actor._task_networks["plane_net"]
#             # network._current_task_proc.interrupt(cause="Code 4")
#             actor.interrupt_network("plane_net", cause="Code 4")

#         # run the queue with the network
#         net.loop(actor=actor)
#         env.process(interrupting_proc(env, actor, 1.0))
#         env.run()


# def test_interrupting_network_with_restart() -> None:
#     with EnvironmentContext() as env:
#         actor = _build_test(env)
#         task_fact = TaskNetworkFactory(
#             "plane_net",
#             task_classes,
#             task_links,
#         )
#         net = task_fact.make_network()

#         # build arguments for the task list
#         task_name_list = [
#             "LandingLocationSelection",
#             "LandingLocationPrep",
#             "Fly",
#             "LandingCheck",
#             "Land",
#             "MaintenanceWait",
#         ]

#         # tell the actor the queue its getting
#         actor.add_task_network(net)
#         actor.set_task_queue("plane_net", task_name_list)

#         # create a process that interrupts the plane during different times
#         def interrupting_proc(
#             env: Environment, actor: Aircraft, interrupt_time: float
#         ) -> SIMPY_GEN:
#             yield env.timeout(interrupt_time)
#             # get the process
#             network = actor._task_networks["plane_net"]
#             assert network._current_task_name is not None and network._current_task_name == "Fly"
#             assert network._current_task_proc is not None
#             network._current_task_proc.interrupt(cause="restart")

#         # run the queue with the network
#         net.loop(actor=actor)
#         env.process(interrupting_proc(env, actor, 0.1))
#         env.run()
#         # the plane should land still
#         assert actor._task_queue["plane_net"] == [], "Actor had tasks left"
#         assert actor.code == 0, "Actor didn't get maintained"
#         # it should take longer than the cancelled version
#         assert pytest.approx(env.now, abs=0.0001) == 21.464767


def test_decision_task_hold() -> None:
    # Test the conditions found in https://github.com/gtri/upstage/issues/35
    # Looks at zero time holds vs pass-through decision tasks

    # Test for new behavior first.
    data = []

    class Waiter(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            data.append(f"{self.env.now:.1f} >> {actor.name} in Waiter")
            yield Wait(1.0)

    class Runner(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            data.append(f"{self.env.now:.1f} >> {actor.name} in Runner")
            yield Wait(2.0)

    class Thinker(DecisionTask):
        DO_NOT_HOLD = True

        def make_decision(self, *, actor: Actor) -> None:
            data.append(f"{self.env.now:.1f} >> {actor.name} in Thinker")
            if "one" in actor.name:
                self.set_actor_task_queue(actor, ["Waiter"])
            else:
                self.set_actor_task_queue(actor, ["Runner"])

    net = TaskNetworkFactory(
        name="Example Net",
        task_classes={"Waiter": Waiter, "Runner": Runner, "Thinker": Thinker},
        task_links={
            "Waiter": TaskLinks(default="Thinker", allowed=["Thinker"]),
            "Thinker": TaskLinks(default="", allowed=["Waiter", "Runner"]),
            "Runner": TaskLinks(default="Thinker", allowed=["Thinker"]),
        },
    )
    with EnvironmentContext() as env:
        a = Actor(name="Actor one", debug_logging=True)
        b = Actor(name="Actor two", debug_logging=True)

        for actor in [a, b]:
            n = net.make_network()
            actor.add_task_network(n)
            actor.start_network_loop(n.name, "Waiter")

        env.run(until=2)

    expected = [
        "0.0 >> Actor one in Waiter",
        "0.0 >> Actor two in Waiter",
        "1.0 >> Actor one in Thinker",
        "1.0 >> Actor one in Waiter",
        "1.0 >> Actor two in Thinker",
        "1.0 >> Actor two in Runner",
    ]
    assert data == expected

    # Reset data in place, test for default behavior
    data[:] = []

    Thinker.DO_NOT_HOLD = False
    with EnvironmentContext() as env:
        a = Actor(name="Actor one", debug_logging=True)
        b = Actor(name="Actor two", debug_logging=True)

        for actor in [a, b]:
            n = net.make_network()
            actor.add_task_network(n)
            actor.start_network_loop(n.name, "Waiter")

        env.run(until=2)
    expected = [
        "0.0 >> Actor one in Waiter",
        "0.0 >> Actor two in Waiter",
        "1.0 >> Actor one in Thinker",
        "1.0 >> Actor two in Thinker",
        "1.0 >> Actor one in Waiter",
        "1.0 >> Actor two in Runner",
    ]
    assert data == expected


# ---- class-reference API and validation tests ----


def test_class_keyed_factory() -> None:
    class Mover(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    class Planner(DecisionTask):
        def make_decision(self, *, actor: Actor) -> None:
            pass

    factory = TaskNetworkFactory(
        "ClassNet",
        task_links={
            Mover: TaskLinks(default=Planner, allowed=[Planner]),
            Planner: TaskLinks(default=Mover, allowed=[Mover]),
        },
    )
    assert "Mover" in factory.task_classes
    assert "Planner" in factory.task_classes
    assert factory.task_links["Mover"].default == "Planner"
    assert factory.task_links["Planner"].allowed == ["Mover"]

    with EnvironmentContext() as env:
        a = Actor(name="test")
        net = factory.make_network()
        a.add_task_network(net)
        a.start_network_loop(net.name, "Mover")
        env.run(until=3)


def test_class_keyed_single_arg() -> None:
    """Class-keyed map passed as the *first* positional arg (task_classes slot)."""

    class Ping(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    links: dict[type[Task], TaskLinks] = {Ping: TaskLinks(default=Ping, allowed=[Ping])}
    factory = TaskNetworkFactory(
        "PingNet",
        links,
    )
    assert "Ping" in factory.task_classes


def test_validation_catches_bad_reference() -> None:
    class Good(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    bad_links: dict[type[Task], TaskLinks] = {
        Good: TaskLinks(default="Nonexistent", allowed=["Nonexistent"]),
    }
    with pytest.raises(UpstageError, match="unknown task name"):
        TaskNetworkFactory("Bad", task_links=bad_links)


def test_validation_warns_unlinked_task() -> None:
    class A(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    class B(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    with pytest.warns(UserWarning, match="no entry in task_links"):
        TaskNetworkFactory(
            "Partial",
            task_classes={"A": A, "B": B},
            task_links={"A": TaskLinks(default="A", allowed=["A"])},
        )


def test_string_api_still_works() -> None:
    """Existing string-keyed API is unchanged."""

    class X(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    factory = TaskNetworkFactory(
        "Compat",
        task_classes={"X": X},
        task_links={"X": TaskLinks(default="X", allowed=["X"])},
    )
    assert factory.task_classes["X"] is X


# ---- guard-based transitions, on_enter/on_exit, and visualization tests ----


def test_guard_transitions() -> None:
    """Guards determine the next task when the current one finishes."""
    trace: list[str] = []

    class Bot(Actor):
        status: int = State().create()

    class StepA(Task):
        def task(self, *, actor: Bot) -> TASK_GEN:
            trace.append("A")
            yield Wait(1.0)
            actor.status += 1

    class StepB(Task):
        def task(self, *, actor: Bot) -> TASK_GEN:
            trace.append("B")
            yield Wait(1.0)

    class StepC(Task):
        def task(self, *, actor: Bot) -> TASK_GEN:
            trace.append("C")
            yield Wait(1.0)

    def go_to_c(actor: Bot) -> bool:
        return actor.status >= 2

    factory = TaskNetworkFactory(
        "GuardNet",
        task_links={
            StepA: TaskLinks(
                transitions=[
                    TaskTransition(StepC, go_to_c),
                    TaskTransition(StepB, None),  # fallback
                ]
            ),
            StepB: TaskLinks(transitions=[TaskTransition(StepA, None)]),
            StepC: TaskLinks(transitions=[TaskTransition(StepA, None)]),
        },
    )

    with EnvironmentContext() as env:
        bot = Bot(name="bot", status=0)
        net = factory.make_network()
        bot.add_task_network(net)
        bot.start_network_loop(net.name, "StepA")
        env.run(until=10)

    # status increments each time StepA runs (at the end of the task)
    # A(status 0→1): guard false → B, A(status 1→2): guard true → C, A(2→3) → C ...
    assert trace[:6] == ["A", "B", "A", "C", "A", "C"]


def test_on_enter_on_exit() -> None:
    """on_enter runs before task(), on_exit runs after."""
    trace: list[str] = []

    class Greeter(Task):
        def on_enter(self, *, actor: Actor) -> None:
            trace.append("enter")

        def task(self, *, actor: Actor) -> TASK_GEN:
            trace.append("task")
            yield Wait(1.0)

        def on_exit(self, *, actor: Actor) -> None:
            trace.append("exit")

    factory = TaskNetworkFactory.from_single_looping("Loop", Greeter)
    with EnvironmentContext() as env:
        a = Actor(name="a")
        net = factory.make_network()
        a.add_task_network(net)
        a.start_network_loop(net.name, "Greeter")
        env.run(until=2.5)

    # Two full cycles (enter/task/exit) + a third enter/task in-flight at t=2.5
    assert trace == ["enter", "task", "exit", "enter", "task", "exit", "enter", "task"]


def test_to_mermaid() -> None:
    class A(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    class B(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    factory = TaskNetworkFactory(
        "Viz",
        task_links={
            A: TaskLinks(
                transitions=[
                    TaskTransition(B, lambda actor: True),
                    TaskTransition(A, None),
                ]
            ),
            B: TaskLinks(transitions=[TaskTransition(A, None)]),
        },
    )
    net = factory.make_network()
    mermaid = to_mermaid(net)
    assert "graph TD" in mermaid
    assert "A" in mermaid
    assert "B" in mermaid
    # Factory passthrough also works
    assert to_mermaid(factory) == mermaid


def test_to_dot() -> None:
    class X(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    class Y(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    factory = TaskNetworkFactory(
        "DotViz",
        task_links={
            X: TaskLinks(default=Y, allowed=[Y]),
            Y: TaskLinks(default=X, allowed=[X]),
        },
    )
    net = factory.make_network()
    dot = to_dot(net)
    assert "digraph" in dot
    assert '"X"' in dot
    assert '"Y"' in dot
    # Factory passthrough also works
    assert to_dot(factory) == dot


# Snapshot tests for the diagram generators.  These are golden-file tests:
# they pin the exact string output so that format changes are caught and
# have to be updated explicitly.  If you are deliberately changing the
# Mermaid or DOT output, update the expected strings below to match.


def test_to_mermaid_snapshot_guards_and_labels() -> None:
    """Full Mermaid output with guard labels and uniform node declarations."""

    class A(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    class B(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    def needs_b(actor: Actor) -> bool:
        return True

    factory = TaskNetworkFactory(
        "Snap",
        task_links={
            A: TaskLinks(
                transitions=[
                    TaskTransition(B, needs_b, "go to B"),
                    TaskTransition(A, None),
                ]
            ),
            B: TaskLinks(transitions=[TaskTransition(A, None)]),
        },
    )
    expected = "\n".join(
        [
            "graph TD",
            '    A["A"]',
            '    B["B"]',
            "    A -->|go to B| B",
            "    A --> A",
            "    B --> A",
        ]
    )
    net = factory.make_network()
    assert to_mermaid(net) == expected


def test_to_mermaid_snapshot_allowed_edges_and_legend() -> None:
    """Allowed-only edges produce dashed lines and a legend."""

    class A(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    class B(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    factory = TaskNetworkFactory(
        "SnapAllowed",
        task_links={
            A: TaskLinks(default=A, allowed=[A, B]),
            B: TaskLinks(default=A, allowed=[A]),
        },
    )
    mermaid = to_mermaid(factory.make_network())
    # Uniform nodes
    assert '    A["A"]' in mermaid
    assert '    B["B"]' in mermaid
    # Default edges
    assert "    A --> A" in mermaid
    assert "    B --> A" in mermaid
    # Allowed-only (dashed) edge
    assert "    A -.-> B" in mermaid
    # Legend triggered by dashed edges
    assert "subgraph Legend" in mermaid
    assert "|transition|" in mermaid
    assert "|via queue|" in mermaid


def test_to_mermaid_snapshot_legend_off() -> None:
    """`legend=False` suppresses the legend even when dashed edges exist."""

    class A(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    class B(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    factory = TaskNetworkFactory(
        "SnapNoLegend",
        task_links={
            A: TaskLinks(default=A, allowed=[A, B]),
            B: TaskLinks(default=A, allowed=[A]),
        },
    )
    mermaid = to_mermaid(factory.make_network(), legend=False)
    assert "subgraph Legend" not in mermaid
    assert "    A -.-> B" in mermaid


def test_to_mermaid_snapshot_with_hooks() -> None:
    """Tasks defining on_enter/on_exit get annotated nodes."""

    class Hooked(Task):
        def on_enter(self, *, actor: Actor) -> None:
            pass

        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    factory = TaskNetworkFactory.from_single_looping("Hook", Hooked)
    mermaid = to_mermaid(factory.make_network())
    assert '    Hooked["Hooked<br/><sub><i>(on_enter)</i></sub>"]' in mermaid


def test_to_dot_snapshot_uniform_nodes() -> None:
    """DOT output declares every task node, hooked or not."""

    class X(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    class Y(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    factory = TaskNetworkFactory(
        "DotSnap",
        task_links={
            X: TaskLinks(default=Y, allowed=[Y]),
            Y: TaskLinks(default=X, allowed=[X]),
        },
    )
    expected = "\n".join(
        [
            "digraph DotSnap {",
            "    rankdir=TB;",
            '    node [shape=box, style=rounded, fontname="Helvetica"];',
            '    edge [fontname="Helvetica", fontsize=10];',
            "",
            '    "X";',
            '    "Y";',
            "",
            '    "X" -> "Y";',
            '    "Y" -> "X";',
            "}",
        ]
    )
    assert to_dot(factory.make_network()) == expected


def test_to_dot_snapshot_with_hooks_and_labels() -> None:
    """DOT output with hooks, guard labels, and dashed (allowed-only) edges."""

    class Enter(Task):
        def on_enter(self, *, actor: Actor) -> None:
            pass

        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    class Exit(Task):
        def on_exit(self, *, actor: Actor) -> None:
            pass

        def task(self, *, actor: Actor) -> TASK_GEN:
            yield Wait(1.0)

    def done(actor: Actor) -> bool:
        return True

    factory = TaskNetworkFactory(
        "DotFull",
        task_links={
            Enter: TaskLinks(
                transitions=[TaskTransition(Exit, done, "ready")],
                allowed=[Enter],
            ),
            Exit: TaskLinks(default=Enter, allowed=[Enter]),
        },
    )
    dot = to_dot(factory.make_network())
    assert (
        '    "Enter" [label=<Enter<br/><font point-size="10"><i>(on_enter)</i></font>>];'
        in dot
    )
    assert (
        '    "Exit" [label=<Exit<br/><font point-size="10"><i>(on_exit)</i></font>>];'
        in dot
    )
    assert '    "Enter" -> "Exit" [label="ready"];' in dot
    assert '    "Enter" -> "Enter" [style=dashed];' in dot
    assert '    "Exit" -> "Enter";' in dot
