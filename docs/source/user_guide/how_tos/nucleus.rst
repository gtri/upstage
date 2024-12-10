============
Task Nucleus
============

UPSTAGE provides a more advanced signal-passing interface between tasks and actors with the ``Nucleus``.

A Nucleus can be attached to an ``Actor``, and ``States`` linked to the Nucleus. When one of those states changes,
an interrupt will be sent to the relevant task networks.

The basic syntax is this:

.. code-block:: python

    # Create the nucleus object, attached to an actor
    nuc = UP.TaskNetworkNucleus(actor=actor)
    # From some task network:
    task_net = task_net_factory.make_network()
    # Add it to the actor
    actor.add_task_network(task_net)
    # Tell the nucleus object that this network changes if
    # the state names given change
    nuc.add_network(task_net, ["state name to watch", "other state"])

When any state given to the nucleus changes, nucleus pushes an interrupt to the task network. That interrupt is passed down
as a cause to ``on_interrupt`` as an instance of type :py:class:`~upstage.nucleus.NucleusInterrupt`.

.. code-block:: python

    class SomeTask(UP.Task):
        def task(...):
            ...

        def on_interrupt(self, *, actor, cause):
            if isinstance(cause, UP.NucleusInterrupt):
                state_that_changed: str = cause.state_name
                state_value: Any = cause.state_value

From there, you can decide how to handle the interrupt in the usual manner.

Here is a complete example showing the interaction. The actor has some number that defines the time it takes to
change the number. Once the number changes, the nucleus interrupts the other task network, and the restarting
task increments the results state.

.. code-block:: python
    :linenos:

    class NumberHolder(UP.Actor):
        number = UP.State()
        results = UP.State(default=0)


    class NumberChanger(UP.Task):
        def task(self, *, actor):
            yield UP.Wait(actor.number)
            print(f"{self.env.now:.2f}: About to change number")
            actor.number += 1


    class InterruptedByNucleus(UP.Task):
        def task(self, *, actor):
            # Yielding an event makes the task halt forever EXCEPT
            # when interrupted.
            yield UP.Event()

        def on_interrupt(self, *, actor, cause):
            print(f"{self.env.now:.2f}: Interrupted with cause: {cause}")
            actor.results += 1
            return self.INTERRUPT.RESTART


    fact = UP.TaskNetworkFactory(
        "changer",
        {"Runner": NumberChanger},
        {"Runner": {"default": "Runner", "allowed": ["Runner"]}},
    )

    fact2 = UP.TaskNetworkFactory(
        "interrupted",
        {"Side": InterruptedByNucleus},
        {"Side": {"default": "Side", "allowed": ["Side"]}},
    )


    with UP.EnvironmentContext() as env:
        actor = NumberHolder(
            name="example",
            number=3,
            results=0,
        )
        nuc = UP.TaskNetworkNucleus(actor=actor)

        task_net = fact.make_network()
        actor.add_task_network(task_net)

        task_net_2 = fact2.make_network()
        actor.add_task_network(task_net_2)
        nuc.add_network(task_net_2, ["number"])

        actor.start_network_loop("changer", init_task_name="Runner")
        actor.start_network_loop("interrupted", init_task_name="Side")

        env.run(until=25)
        print(f"Number of nucleus interrupts: {actor.results}")

    >>> 3.00: About to change number
    >>> 3.00: Interrupted with cause: NucleusInterrupt: number 4
    >>> 7.00: About to change number
    >>> 7.00: Interrupted with cause: NucleusInterrupt: number 5
    >>> 12.00: About to change number
    >>> 12.00: Interrupted with cause: NucleusInterrupt: number 6
    >>> 18.00: About to change number
    >>> 18.00: Interrupted with cause: NucleusInterrupt: number 7
    >>> Number of nucleus interrupts: 4


To note:

* Line 51: The nucelus is watching for ``number`` to change the task network that has the ``InterruptedByNucleus`` task.
* Line 57: Results will increment every time the interrupt runs. 


Nucleus and Rehearsal
=====================

Nucleus state watchers are not transferred when an Actor is cloned for rehearsal. When a rehearsing actor has a state change,
it does not affect any other networks or the original Actor. Rehearsal only works on a single task network anyway, and so a nucleus
rehearsal wouldn't make sense at this point in UPSTAGE's development.


State Sharing with Nucleus
==========================

A use case for Nucleus is when multiple task networks are sharing a single state and modifying their processing based on that state. This has one key difficulty, which is that
a task cannot interrept itself. If a TaskNetwork changes a state that it is watching, SimPy will fail. It 


What follows is an example that implements a nucleus allocation. This is not recommended, but is included to demonstrate how far you can stretch Nucleus and UPSTAGE. Ultimately,
it is just running on SimPy and you can do what you like. Here are some issues/caveats with the following example:

* None of the tasks are rehearsal-safe (this is OK if you're not going to rehearse)
* Adding nucleus variables/networks within the network that uses them buries the interaction and increases the risk of bugs.

  * It's preferable to define all Nucleus interactions near Actor instantiation for readability
  * In the future, it'd be better to have deeper conditions/information in the nucleus.

* Using a ``DecisionTask`` helps avoid an ``if`` statement in the ``CPUProcess`` task to add the network to the nucleus
* The business logic of the task is overpowered by assistance code, which UPSTAGE tries to avoid as much as possible.

.. literalinclude:: ../../../../src/upstage_des/test/test_docs_examples/test_nucleus_sharing.py
