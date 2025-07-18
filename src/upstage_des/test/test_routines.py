from typing import Any

import simpy as SIM

import upstage_des.api as UP
from upstage_des.type_help import ROUTINE_GEN, SIMPY_GEN, TASK_GEN


class TestActor(UP.Actor):
    value = UP.State[int](default=3)


class SimpleRoutine(UP.Routine):
    def __init__(self, time: float) -> None:
        self.time = time

    def run(self) -> ROUTINE_GEN:
        yield UP.Wait(self.time, rehearsal_time_to_complete=self.time * 2)


class SomeTask(UP.Task):
    def task(self, *, actor: TestActor) -> TASK_GEN:
        self.set_marker("Routine")
        yield SimpleRoutine(actor.value)
        self.set_marker("Wait")
        yield UP.Wait(2.0)

    def on_interrupt(self, *, actor: UP.Actor, cause: str) -> UP.InterruptStates:
        self._v = self.get_marker()
        return UP.InterruptStates.END


def test_simple_routine() -> None:
    # The simple routine is to wait with a different rehearsal time.
    # We run the task regularly and in rehearsal to check that the
    # routine is passing back the right things.

    # Regular running
    with UP.EnvironmentContext() as env:
        act = TestActor(name="Example", value=3)
        task = SomeTask()
        task.run(actor=act)
        env.run()
        assert env.now == 5
        assert task.get_marker() == "Wait"

    # Rehearsing should take twice as long (and a 2 unit wait)
    with UP.EnvironmentContext() as env:
        act = TestActor(name="Example", value=3)
        task = SomeTask()
        new = task.rehearse(actor=act)
        assert new.env.now == 8


class CancelRoutine(UP.Routine):
    def __init__(self, store: SIM.Store) -> None:
        self.evt: UP.Get | None = None
        self.store = store
        self.result: Any = None

    def run(self) -> ROUTINE_GEN:
        self.evt = UP.Get(self.store)
        yield self.evt
        self.result = [self.evt.get_value()]

        self.evt = UP.Get(self.store)
        yield self.evt
        self.result.append(self.evt.get_value())

    def cancel(self) -> ROUTINE_GEN:
        while self.result:
            yield UP.Put(self.store, self.result.pop())


class TestActor2(UP.Actor):
    value = UP.State[list[str]](default_factory=list)
    store = UP.ResourceState[SIM.Store](default=SIM.Store)


class CancelTask(UP.Task):
    def task(self, *, actor: TestActor2) -> TASK_GEN:
        routine = CancelRoutine(actor.store)
        yield routine
        assert routine.result is not None
        actor.value = routine.result

    def on_interrupt(self, *, actor: TestActor2, cause: Any) -> UP.InterruptStates:
        return UP.InterruptStates.END


def test_routine_cancel() -> None:
    # Routines that cancel need to be able to clean up.
    # First, check that the routine

    def _placer(store: SIM.Store, item: Any, t: float, env: SIM.Environment) -> SIMPY_GEN:
        yield env.timeout(t)
        yield store.put(item)

    # First check, does the routine do what we think?
    with UP.EnvironmentContext() as env:
        actor = TestActor2(name="example")

        task = CancelTask()
        proc = task.run(actor=actor)
        place = _placer(actor.store, "first", 2.0, env)
        env.process(place)
        place = _placer(actor.store, "second", 2.5, env)
        env.process(place)
        env.run(until=3)

        assert actor.store.items == []
        assert actor.value == ["first", "second"]

    # Check cancelling partway
    with UP.EnvironmentContext() as env:
        actor = TestActor2(name="example")

        task = CancelTask()
        proc = task.run(actor=actor)
        place = _placer(actor.store, "first", 2.0, env)
        env.process(place)
        env.run(until=3)

        proc.interrupt()
        env.run()
        # The item should get put back on cancel
        assert actor.store.items == ["first"]

    # Check cancelling before anything
    with UP.EnvironmentContext() as env:
        actor = TestActor2(name="example")

        task = CancelTask()
        proc = task.run(actor=actor)
        env.run(until=3)

        proc.interrupt()
        env.run()
        assert actor.value == []

    # For fun and enrichment, see what rehearsal does
    with UP.EnvironmentContext() as env:
        actor = TestActor2(name="example")

        task = CancelTask()
        actor_clone = task.rehearse(actor=actor)
        assert actor_clone.value == [UP.PLANNING_FACTOR_OBJECT] * 2


class TestActor3(UP.Actor):
    reset = UP.State[bool](default=True)
    timeout = UP.State[float]()
    store = UP.ResourceState[SIM.Store](default=SIM.Store)


class WindowedTask(UP.Task):
    def task(self, *, actor: TestActor3) -> TASK_GEN:
        routine = UP.WindowedGet(
            store=actor.store,
            timeout=actor.timeout,
            reset_window=actor.reset,
            get_kwargs=dict(rehearsal_time_to_complete=2.2),
        )
        answer = yield routine
        self.set_actor_knowledge(actor, "result", answer)

    def on_interrupt(self, *, actor: TestActor3, cause: str) -> UP.InterruptStates:
        if cause == "end":
            return UP.InterruptStates.END
        elif cause == "ignore":
            return UP.InterruptStates.IGNORE
        elif cause == "restart":
            return UP.InterruptStates.RESTART
        else:
            raise UP.SimulationError("Bad cause")


def _placer(env: SIM.Environment, act: TestActor3) -> SIMPY_GEN:
    yield env.timeout(1.0)
    yield act.store.put("1")
    yield env.timeout(3.0)
    yield act.store.put("2")
    yield env.timeout(4.0)
    yield act.store.put("3")


def test_windowed_get() -> None:
    # Test the windowed get w/ window reset on
    with UP.EnvironmentContext() as env:
        act = TestActor3(
            name="example",
            reset=True,
            timeout=5.0,
        )

        task = WindowedTask()
        task.run(actor=act)

        env.process(_placer(env, act))
        env.run()

        assert act._knowledge["result"] == ["1", "2", "3"]

    # Same test, but no reset. We shouldn't get the 3rd item.
    with UP.EnvironmentContext() as env:
        act = TestActor3(
            name="example",
            reset=False,
            timeout=5.0,
        )

        task = WindowedTask()
        task.run(actor=act)

        env.process(_placer(env, act))
        env.run()

        assert act._knowledge["result"] == ["1", "2"]

    # An interrupt in the task process will cancel the routine
    # and everything will be back in the store.
    with UP.EnvironmentContext() as env:
        act = TestActor3(
            name="example",
            reset=True,
            timeout=5.0,
        )

        task = WindowedTask()
        proc = task.run(actor=act)

        env.process(_placer(env, act))
        env.run(until=5.0)
        proc.interrupt(cause="end")
        env.run()

        assert "result" not in act._knowledge
        assert act.store.items == ["1", "2", "3"]

    # Interrupt with IGNORE and see the result as before.
    with UP.EnvironmentContext() as env:
        act = TestActor3(
            name="example",
            reset=True,
            timeout=5.0,
        )

        task = WindowedTask()
        proc = task.run(actor=act)

        env.process(_placer(env, act))
        env.run(until=5.0)
        proc.interrupt(cause="ignore")
        env.run()

        assert act._knowledge["result"] == ["1", "2", "3"]

    # Interrupt with RESTART and modify the timeout. The request will be redone
    # but won't last long enough to get the 3rd item.
    with UP.EnvironmentContext() as env:
        act = TestActor3(
            name="example",
            reset=False,
            timeout=5.0,
        )

        task = WindowedTask()
        proc = task.run(actor=act)

        env.process(_placer(env, act))
        env.run(until=5.0)
        act.timeout = 1
        proc.interrupt(cause="restart")
        env.run()

        assert act._knowledge["result"] == ["1", "2"]
        assert act.store.items == ["3"]

    # Rehearsal
    with UP.EnvironmentContext() as env:
        act = TestActor3(
            name="example",
            reset=False,
            timeout=5.0,
        )

        task = WindowedTask()
        new = task.rehearse(actor=act)
        assert new._knowledge["result"] == [UP.PLANNING_FACTOR_OBJECT]
        assert new.env.now == 2.2


if __name__ == "__main__":
    test_windowed_get()
