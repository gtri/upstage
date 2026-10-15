# These tests demonstate why context managers for SimPy resources aren't
# advised in UPSTAGE when dealing with interrupts.
from typing import Any

import pytest
import simpy as SIM
import upstage_des.api as UP


class AnActor(UP.Actor):
    res_state: SIM.Resource = UP.State().create()
    get_time: float = UP.State(default=-1.0, recording=True).create()


class AnActor2(UP.Actor):
    res_state: SIM.Container | SIM.Store = UP.State().create()
    get_time: float = UP.State(default=-1.0, recording=True).create()


class ResourceTask(UP.Task):
    def task(self, *, actor: AnActor) -> UP.TASK_GEN:
        with actor.res_state.request() as req:
            yield req
            actor.get_time = self.env.now
            yield UP.Timeout(1.0)

    def on_interrupt(self, *, actor: AnActor, cause: Any | None) -> UP.InterruptStates:
        return UP.InterruptStates.RESTART


class CorrectResourceTask(UP.Task):
    def task(self, *, actor: AnActor) -> UP.TASK_GEN:
        req = actor.res_state.request()
        yield req
        actor.get_time = self.env.now
        yield UP.Timeout(1.0)
        actor.res_state.release(req)

    def on_interrupt(self, *, actor: AnActor, cause: Any | None) -> UP.InterruptStates:
        return UP.InterruptStates.RESTART



class ContainerTask(UP.Task):
    def task(self, *, actor: AnActor2) -> UP.TASK_GEN:
        with actor.res_state.get(5) as req: # type: ignore [call-arg]
            yield req
            actor.get_time = self.env.now
            yield UP.Timeout(1.0)

    def on_interrupt(self, *, actor: AnActor, cause: Any | None) -> UP.InterruptStates:
        return UP.InterruptStates.RESTART


class StoreTask(UP.Task):
    def task(self, *, actor: AnActor2) -> UP.TASK_GEN:
        with actor.res_state.get() as req:  # type: ignore [call-arg]
            yield req
            actor.get_time = self.env.now
            yield UP.Timeout(1.0)

    def on_interrupt(self, *, actor: AnActor, cause: Any | None) -> UP.InterruptStates:
        return UP.InterruptStates.RESTART



def test_container_end() -> None:
    """This demonstrates how context managers don't work in UPSTAGE tasks."""
    with UP.EnvironmentContext() as env:
        container = SIM.Container(env, capacity=8, init=4)
        a1 = AnActor2(name="First", res_state=container)
        a2 = AnActor2(name="Second", res_state=container)
        
        t1 = ContainerTask()
        t2 = ContainerTask()

        g1 = t1.run(actor=a1)
        t2.run(actor=a2)
        env.run(until=0.5)
        # interrupt, then add
        with pytest.raises(ValueError, match=r"list\.remove\(x\): x not in list"):
            g1.interrupt()
            env.run()


def test_store_end() -> None:
    """This demonstrates how context managers don't work in UPSTAGE tasks."""
    with UP.EnvironmentContext() as env:
        store = SIM.Store(env)
        a1 = AnActor2(name="First", res_state=store)
        a2 = AnActor2(name="Second", res_state=store)
        
        t1 = StoreTask()
        t2 = StoreTask()

        g1 = t1.run(actor=a1)
        t2.run(actor=a2)
        env.run(until=0.5)
        # interrupt, then add
        with pytest.raises(ValueError, match=r"list\.remove\(x\): x not in list"):
            g1.interrupt()
            env.run()



def test_resource_normal_ops() -> None:
    """This demonstrates how context managers work in UPSTAGE tasks.
    
    They work with no interrupts!
    """
    with UP.EnvironmentContext() as env:
        resource = SIM.Resource(env, capacity=1)
        a1 = AnActor(name="First", res_state=resource)
        a2 = AnActor(name="Second", res_state=resource)

        t1 = ResourceTask()
        t2 = ResourceTask()

        t1.run(actor=a1)
        t2.run(actor=a2)
        env.run(until=0.5)
        assert resource.count == 1
        env.run()
        assert env.now == 2
        assert a1.get_time == 0.0
        assert a2.get_time == 1.0
        assert resource.count == 0

    # repeat, without the context manager
    with UP.EnvironmentContext() as env:
        resource = SIM.Resource(env, capacity=1)
        a1 = AnActor(name="First", res_state=resource)
        a2 = AnActor(name="Second", res_state=resource)

        ct1 = CorrectResourceTask()
        ct2 = CorrectResourceTask()

        ct1.run(actor=a1)
        ct2.run(actor=a2)
        env.run(until=0.5)
        assert resource.count == 1
        env.run()
        assert env.now == 2
        assert a1.get_time == 0.0
        assert a2.get_time == 1.0
        assert resource.count == 0


def test_resource_interrupted() -> None:
    """This demonstrates how context managers don't work in UPSTAGE tasks.
    
    However, we do handle watching for Resource.request() because that feature
    holds a reference to an object beyond the task after the request is done.

    The solution to that accidentally allows resources to use their context
    manager, but this is not explicitly supported by UPSTAGE.
    """
    with UP.EnvironmentContext() as env:
        resource = SIM.Resource(env, capacity=1)
        a1 = AnActor(name="First", res_state=resource, debug_logging=True)
        a2 = AnActor(name="Second", res_state=resource)

        t1 = ResourceTask()
        t2 = ResourceTask()

        g1 = t1.run(actor=a1)
        t2.run(actor=a2)

        env.run(until=0.5)
        assert resource.count == 1
        assert a1.get_time == 0
        assert a2.get_time == -1
        g1.interrupt()
        env.run()
        assert a2.get_time == 0.5
        assert a1.get_time == 1.5
        assert resource.count == 0

    # Repeat, but with the non-context manager way
    with UP.EnvironmentContext() as env:
        resource = SIM.Resource(env, capacity=1)
        a1 = AnActor(name="First", res_state=resource, debug_logging=True)
        a2 = AnActor(name="Second", res_state=resource)

        ct1 = CorrectResourceTask()
        ct2 = CorrectResourceTask()

        g1 = ct1.run(actor=a1)
        ct2.run(actor=a2)

        env.run(until=0.5)
        assert resource.count == 1
        assert a1.get_time == 0
        assert a2.get_time == -1
        g1.interrupt()
        env.run()
        assert a2.get_time == 0.5
        assert a1.get_time == 1.5
        assert resource.count == 0
