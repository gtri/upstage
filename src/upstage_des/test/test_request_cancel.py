from typing import Any
import pytest
from simpy import Store, Timeout
from simpy.resources.store import StoreGet, StorePut
import upstage_des.api as UP
from upstage_des.type_help import SIMPY_GEN, TASK_GEN



class Storing(UP.Actor):
    the_store = UP.ResourceState[Store](default=Store)
    result = UP.State[Any](default="First")


class Getting(UP.Task):
    def task(self, *, actor: Storing) -> TASK_GEN:
        """Get"""
        getter = UP.Get(actor.the_store)
        ans = yield getter
        actor.result = getter.get_value()
    
    def on_interrupt(self, *, actor: Storing, cause: Any) -> UP.InterruptStates:
        return UP.InterruptStates.END


class Putting(UP.Task):
    def task(self, *, actor: Storing) -> TASK_GEN:
        """Put"""
        yield UP.Wait(1.0)
        yield UP.Put(actor.the_store, "Second")


f1 = UP.TaskNetworkFactory.from_single_looping("GET", Getting)
f2 = UP.TaskNetworkFactory.from_single_terminating("PUT", Putting)


def _build_actor() -> Storing:
    storing = Storing(name="example")
    net = f1.make_network()
    storing.add_task_network(net)
    storing.start_network_loop(net.name, "Getting")
    net = f2.make_network()
    storing.add_task_network(net)
    storing.start_network_loop(net.name, "Putting")
    return storing


def test_cancel_return() -> None:
    """For issue 110: https://github.com/gtri/upstage/issues/110
    
    Demonstrate that a cancelled get request can return the item,
    and that it does so with a Put, so other getters can have it.
    """
    # Standard behavior should work.
    with UP.EnvironmentContext() as env:
        storing = _build_actor()
        env.run()
        assert env.now == 1
        assert storing.result == "Second"

    # Run until 0.5, then make an interrupt that happens at time 1
    # The Put request should have placed the item in the store, but
    # the next processes shouldn't have gotten it.
    with UP.EnvironmentContext() as env:
        storing = _build_actor()
        env.run(until=0.5)

        def _proc() -> SIMPY_GEN:
            yield env.timeout(1.0 - env.now)
            # One more zero time timeout to force putting the interrupt
            # after the get request
            yield env.timeout(0.0)
            tasks = storing.get_running_tasks()
            task_data = tasks["GET"]
            task_data.process.interrupt(cause="Interrupted you")
        
        env.process(_proc())
        # Run until the timeouts are supposed to act.
        env.run(until=1.0)
        # The queue should have two items, both timeouts, and the shorter one is
        # second.
        assert len(env._queue) == 2
        assert env._queue[0][0] == 1.0
        assert env._queue[1][0] == 1.0
        assert env._queue[0][-1]._delay == 1.0
        assert env._queue[1][-1]._delay == 0.5

        assert env.now == 1
        assert storing.result == "First"
        # Now step through, making sure our expectation of ordering is true
        assert len(storing.the_store.items) == 0
        env.step()
        assert len(env._queue) == 2
        assert isinstance(env._queue[0][-1], Timeout)
        assert isinstance(env._queue[1][-1], StorePut)
        # The item has been put in the store, but the StorePut is waiting
        # to signal the gets.
        assert len(storing.the_store.items) == 1
        env.step()
        assert len(env._queue) == 2
        assert isinstance(env._queue[0][-1], StorePut)
        assert isinstance(env._queue[1][-1], Timeout)
        # One step to get the StorePut done
        env.step()
        # Next step runs the timeout, which will queue the interrupt
        # before StoreGet
        env.step()
        assert len(env._queue) == 4
        # The actor's store no longer has the item
        assert len(storing.the_store.items) == 0
        # but the item isn't out yet.
        assert storing.result == "First"

        # finish out the interrupts
        env.run()

        # We need the store to have the item at the end of this
        assert storing.the_store.items == ["Second"]


if __name__ == "__main__":
    test_cancel_return()
