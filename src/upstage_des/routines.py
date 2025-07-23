"""A routine is something small done by an Actor in a Task."""

from collections.abc import Generator
from typing import Any

import simpy as SIM

from upstage_des.base import SIMPY_GEN, SettableEnv, SimulationError
from upstage_des.events import Any as AnyEvent
from upstage_des.events import BaseEvent, Get, Put, Wait

ROUTINE_GEN = Generator[BaseEvent, Any, Any]


class Routine(SettableEnv):
    """A base class for creating simple routines from.

    Routines are meant to be subclassed, and if you want actor or other data,
    do that at instantiation.

    .. code-block:: python

       class SomeTask(Task):
           def task(self, *, actor):
              result = yield Routine(...)
              do_something_with(result)
    """

    def __init__(self) -> None:
        """Create the routine."""
        super().__init__()

    def run(self) -> ROUTINE_GEN:
        """Define the routine."""
        raise NotImplementedError(
            "User must define the actions performed when executing this routine"
        )

    def cancel(self) -> ROUTINE_GEN:
        """Define how to clean up if the routine is interrupted."""
        raise NotImplementedError(
            "User must define the actions performed when executing this routine"
        )

    def _run(self) -> ROUTINE_GEN:
        try:
            gen = self.run()
            while True:
                evt = next(gen)
                if not isinstance(evt, BaseEvent):
                    raise SimulationError("Routines only support BaseEvent subclasses.")
                yield evt
        except StopIteration as e:
            return e.value
        except GeneratorExit:
            # The parent task will close this generator and handle everything
            # else.
            ...

    def _run_cancel(self) -> SIMPY_GEN:
        # Cancel can yield upstage events, so this pushes those through.
        # This can be very unsafe - if a store/container can't handle a put
        # or a get of some kind, it will hold forever.
        for evt in self.cancel():
            yield evt.as_event()

    def rehearse(self) -> tuple[float, Any | None]:
        """Rehearse the Routine.

        By default, this just rehearses the events in run() and returns the time
        and no returned value. Routines do not expect to have a return value
        anyway, but they may attach a value to themselves.

        Subclasses can call this and add a value, or do their own.

        Returns:
            TASK_GEN: _description_

        Yields:
            tuple[float, Any | None]: Time and value of rehearsal.
        """
        time = 0.0
        for evt in self._run():
            t, _ = evt.rehearse()
            time += t
        return time, None


class WindowedGet(Routine):
    """A routine for repeating a Get request in a time window.

    If you're a waiting room, you might want to wait 5 minutes until
    the first patient arrives to see if there are any others before you act, for
    example. This routine will help do that in a compact way.

    It assumes that, on an interrupt or cancellation, you would put everything
    back in the store.
    """

    def __init__(
        self,
        store: SIM.Store,
        timeout: float,
        timeout_unit: str | None = None,
        reset_window: bool = False,
        get_args: tuple[Any, ...] | None = None,
        get_kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Create a windowed Get request.

        The request will repeat within a time window until the time is done.

        If you opt to reset the window, instead of getting all possible gets
        within 5 minutes, every new get resets the clock to 5 minutes. This may
        cause infinite waiting in an edge case.

        Args:
            store (SIM.Store): The store to get from.
            get_args (tuple[Any, ...]): Arguments for the get request
            get_kwargs (dict[str, Any]): Keyword arguments for the get request.
            timeout (float): Time to wait from a successful get to end
            timeout_unit (str | None, optional): Units of the timeout.
                Defaults to None.
            reset_window (bool, optional): If we restart the window on later successes.
                Defaults to False.
        """
        super().__init__()
        self.store = store
        self.timeout = timeout
        self.timeout_unit = timeout_unit
        self.reset_window = reset_window
        self.get_args = [] if get_args is None else get_args
        self.get_kwargs = {} if get_kwargs is None else get_kwargs
        self.result: list[Any] = []
        self._evt: None | Get = None

    def run(self) -> ROUTINE_GEN:
        """Run the windowed get."""
        need_wait = False
        wait: Wait | None = None
        while True:
            incoming = Get(self.store, *self.get_args, **self.get_kwargs)
            self._evt = incoming

            evts: list[BaseEvent] = [incoming]
            if need_wait:
                if wait is None or self.reset_window:
                    wait = Wait(self.timeout, timeout_unit=self.timeout_unit)
                evts.append(wait)

            yield AnyEvent(*evts)

            if not incoming.is_complete():
                incoming.cancel()
                break

            need_wait = True
            obj = incoming.get_value()
            self.result.append(obj)
        return self.result

    def cancel(self) -> ROUTINE_GEN:
        """Return all the items to the store and cancel the get."""
        while self.result:
            yield Put(self.store, self.result.pop(0))

    def rehearse(self) -> tuple[float, Any]:
        """Rehearse the windowed get.

        This just expects one return value at the expected time of the get.

        Returns:
            tuple[float, Any | None]: _description_
        """
        get = Get(self.store, *self.get_args, **self.get_kwargs)
        t, v = get.rehearse()
        self.result = [v]
        return t, self.result
