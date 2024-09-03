===============
Task Interrupts
===============

Task interruption handling is one of UPSTAGE's convenience features for wrapping SimPy. It allows you to use interruptions to modify the task network without having to write
exceptions over all the ``yield`` statements.

Motivation
==========

For reference, here is how you might handle interruptions in a process with two timeouts:

.. code-block:: python

    import simpy as SIM

    def env_print(env, message: str) -> None:
        msg = f"{env.now:.2f} :: {message}"
        print(msg)

    def get_and_work(env: SIM.Environment, store: SIM.Store):
        get_event = store.get()
        try:
            item = yield get_event
            env_print(env, f"got the item: '{item}'")
        except SIM.Interrupt as interrupt:
            # No matter what, cancel the get and leave
            get_event.cancel()
            env_print(env, f"Interrupted in the get wait. Cause: {interrupt.cause}")
            return

        time_to_work = 2.0 # This could be a function of your item
        end_time = env.now + time_to_work
        while True:
            try:
                yield env.timeout(time_to_work)
                env_print(env, "Finished work")
                break
            except SIM.Interrupt as interrupt:
                env_print(env, f"Interrupted in the work wait with cause: {interrupt.cause}")
                if interrupt.cause == "CANCEL GET":
                    # do nothing, the cancel is too late
                    # but get ready to loop again!
                    time_to_work = end_time - env.now
                elif interrupt.cause == "CANCEL WORK":
                    return
                
    def putter(env, store):
        yield env.timeout(1.0)
        yield store.put("THING")


The work in that process is very simple, but the cancelling and code required to handle interrupts that we may not care about complicates it greatly. In general, we prefer a task/process
to explain exactly what it's trying to do, and we can handle interrupts separately without clouding the business logic of the task.

In addition, if interrupts are sent by another process, we don't want the other process to have to know about introspecting the actor or the task network to know if it can/should do the
interrupt. It's preferable to let the interrupting process ask for an interrupt (with some data) and let the actor/task decide if it's a good idea or not. Finally, if the simulation builder
does not remember to always cancel events (especially get and put), then you may end up with a get request that takes from a store without going anywhere.

Here's how those interrupts would look in SimPy:

.. code-block:: python
    
    # Interrupt in the get wait
    env = SIM.Environment()
    store = SIM.Store(env)

    proc1 = env.process(putter(env, store))
    proc2 = env.process(get_and_work(env, store))

    env.run(until=0.5)
    proc2.interrupt(cause="outer stop")
    env.run()
    env_print(env, "DONE")
    env_print(env, f"Items in store: {store.items}")
    >>> 0.50 :: Interrupted in the get wait. Cause: outer stop
    >>> 1.00 :: DONE
    >>> 1.00 :: Items in store: ['THING']

    # Interrupt in the work wait with an ignorable cause
    env = SIM.Environment()
    store = SIM.Store(env)

    proc1 = env.process(putter(env, store))
    proc2 = env.process(get_and_work(env, store))

    env.run(until=1.5)
    proc2.interrupt(cause="CANCEL GET")
    env.run()
    env_print(env, "DONE")
    >>> 1.00 :: got the item: 'THING'
    >>> 1.50 :: Interrupted in the work wait with cause: CANCEL GET
    >>> 3.00 :: Finished work
    >>> 3.00 :: DONE

    # Interrupt in the work wait with a real cause
    env = SIM.Environment()
    store = SIM.Store(env)

    proc1 = env.process(putter(env, store))
    proc2 = env.process(get_and_work(env, store))

    env.run(until=1.5)
    proc2.interrupt(cause="CANCEL WORK")
    env.run()
    env_print(env, "DONE")
    >>> 1.00 :: got the item: 'THING'
    >>> 1.50 :: Interrupted in the work wait with cause: CANCEL WORK
    >>> 3.00 :: DONE


If you interrupt without an approved cause, and miss a final ``else`` (like in this example), you'd finish the work at time 3.5.

Very critically, if you missed putting the ``get_event.cancel()`` line, SimPy would still process the ``get_event`` and take the item from the store. This would effectively remove it from the simulation.


UPSTAGE Interrupts
==================

UPSTAGE's interrupt handling system mitigates these key sources of error or frustration:

#. Forgetting to cancel get and put events in an interrupt
#. Make the main task more readable about what it's doing.
#. Simplifies interrupt causes and conditions.
#. Forgetting to stop some calculation of a state

To access these features, do the following:

#. Implement ``on_interrupt`` in the :py:class:`~upstage.task.Task` class.

#. Optionally: use the ``marker`` features in the task and interrupt methods.

   * :py:meth:`~upstage.task.Task.set_marker`

   * :py:meth:`~upstage.task.Task.get_marker`

   * :py:meth:`~upstage.task.Task.clear_marker`

We'll start simple, then add complexity to the interrupt.

Here's what the above process would look like as an UPSTAGE Task:

.. code-block:: python
    :linenos:

    import upstage.api as UP
    import simpy as SIM
    from typing import Any

    def env_print(env, message: str) -> None:
        msg = f"{env.now:.2f} :: {message}"
        print(msg)


    def putter(env, store):
        yield env.timeout(1.0)
        yield store.put("THING")


    class DoWork(UP.Task):
        def task(self, *, actor: UP.Actor):
            self.set_marker("getting")
            item = yield UP.Get(actor.stage.store)
            env_print(self.env, f"got the item: '{item}'")

            self.set_marker("working")
            yield UP.Wait(2.0)
            env_print(env, "Finished work")

        def on_interrupt(self, *, actor: UP.Actor, cause: Any) -> UP.InterruptStates:
            marker = self.get_marker()
            env_print(self.env, f"INTERRUPT:\n\tGot cause: '{cause}'\n\tDuring marker: '{marker}'")
            return self.INTERRUPT.END


Then, when you run it:

.. code-block:: python

    with UP.EnvironmentContext() as env:
        actor = UP.Actor(name="worker")
        store = SIM.Store(env)
        UP.add_stage_variable("store", store)

        task = DoWork()
        proc = task.run(actor=actor)

        proc1 = env.process(putter(env, store))

        env.run(until=0.5)
        proc.interrupt(cause="because")
        env.run()
        env_print(env, f"Items in store: {store.items}")

    >>> 0.50 :: INTERRUPT:
	>>> Got cause: 'because'
	>>> During marker: 'getting'
    >>> 1.00 :: Items in store: ['THING']

Now the task is small and informative about what it's supposed to do when its not interrupted. The marker features let us set and get introspection data cleanly.

Notice also that the ``Get()`` call does not need to be cancelled by the user; UPSTAGE does that for us (for all :py:class:`~upstage.events.BaseEvent` subclasses that implement ``cancel``).

Some additional details:

* Line 25: The ``on_interrupt`` method will pass in the actor and the interrupt cause only.

* Line 21: If we didn't do: ``self.set_marker("working")`` here, the Task would still think it was marked as ``"getting"``. Yields do not clear marks.

  * You can use ``clear_marker`` to clear it, and return to a default behavior if you like.

* Line 26: If no marker is set, the ``get_marker`` method will return ``None``

* Line 28: More on ``INTERRUPT`` below.

INTERRUPT Types and Setting Markers
-----------------------------------

Interrupts allow 4 different outcomes to the task, which are signalled by the :py:class:`~upstage.task.InterruptStates` Enum (or :py:class:`~upstage.task.Task.INTERRUPT` as part of ``self``). The first
three can be returned from ``on_interrupt`` to define how to handle the interrupt.

#. ``END``: Ends the task right there (and moves on in the task network). This cancels the pending event(s).
#. ``IGNORE``: When returned, keeps the task moving along as if the interrupt didn't happen
#. ``RESTART``: Starts the task back over. This cancels the pending event(s).

UPSTAGE Tasks work by being the process that SimPy sees and managing the internal ``task()`` loop as its own generator, passing SimPy events to the event handler as needed. By default, it assumes
you want to ``END`` the task on an interrupt. This is assumed when no ``on_interrupt`` is defined.

Markers allow some flexibility in handling interrupts. If you do not define an ``on_interrupt``, then you can use ``self.set_marker(marker, self.INTERRUPT.IGNORE)`` to ignore interrupts while that marker is active.

If you implement ``on_interrupt``, then the marker's interrupt value is ignored.


Advanced Interrupts and Marking
===============================

Let's return to our example, and add more complicated interrupt handling, including with an active state on the actor.

.. code-block:: python
    :linenos:

    class Worker(UP.Actor):
        time_worked: float = UP.LinearChangingState(default=0.0)

    class DoWork(UP.Task):
        def task(self, *, actor: Worker):
            self.set_marker("getting")
            actor.activate_linear_state(state="time_worked", rate=1.0, task=self)
            item = yield UP.Get(actor.stage.store)
            env_print(self.env, f"got the item: '{item}'")

            self.set_marker("working")
            yield UP.Wait(2.0)
            actor.deactivate_all_states(task=self)
            env_print(env, "Finished work")

        def on_interrupt(self, *, actor: Worker, cause: Any) -> UP.InterruptStates:
            marker = self.get_marker()
            marker_time = self.get_marker_time()
            env_print(self.env, f"INTERRUPT:\n\tGot cause: '{cause}'\n\tDuring marker: '{marker}'\nWhich started at: {marker_time}")
            
            if marker == "getting":
                if cause == "CANCEL GET":
                    time_passed = self.env.now - marker_time
                    # Allow some leeway that we won't cancel the wait if it's been long enough
                    if time_passed > 0.9:
                        return self.INTERRUPT.IGNORE
                    else:
                        return self.INTERRUPT.END
                else:
                    return self.INTERRUPT.IGNORE
            elif marker == "working":
                if cause == "CANCEL WORK":
                    return self.INTERRUPT.END
                else:
                    return self.INTERRUPT.IGNORE
            # A return of None will cause an error, which might be what we want to know.
    
The new features are:

* Line 13: Get the time we set the marker
* Line 18: Use the marker time to determine how we want to interrupt
* Line 31: Remind ourselves that returning ``None`` throws an exception

With these features we now have separated the logic of a successful task from one that is interrupted. It also allows more structure and streamlining of interrupt actions.

Here's an example where the automatic cancelling of an active state is also shown:

.. code-block:: python

    with UP.EnvironmentContext() as env:
        actor = Worker(name="worker")
        store = SIM.Store(env)
        UP.add_stage_variable("store", store)

        task = DoWork()
        proc = task.run(actor=actor)

        proc1 = env.process(putter(env, store))

        env.run(until=1.75)
        proc.interrupt(cause="CANCEL WORK")
        env.run()
        env_print(env, f"Time worked: {actor.time_worked}")
    
    >>> 1.00 :: got the item: 'THING'
    >>> 1.75 :: INTERRUPT:
    >>>     Got cause: 'CANCEL WORK'
    >>>     During marker: 'working'
    >>>     Which started at: 1.0
    >>> 3.00 :: Items in store: []
    >>> 3.00 :: Time worked: 1.75

The interrupt automatically deactivates all states, keeping your Actors safe from runaway state values.

Getting the Process
===================

If an actor is running a task network, you will need to get the current Task process to send an interrupt. Do that with the :py:meth:`upstage.actor.Actor.get_running_tasks` method.

.. code-block:: python

    network_processes = actor.get_running_tasks()
    task_name, task_process = network_processes[task_network_name]
    task_process.interrupt(cause="Stop running")

    # OR:
    task_data = actor.get_running_task(task_network_name)
    task_data.process.interrupt(cause="Stop running")

    # OR:
    actor.interrupt_network(task_network_name, cause="Stop running")

The first two methods are better to use if you need to check that the task name is the right one for interrupt. A well-defined task network should handle the interrupt anywhere, though.
