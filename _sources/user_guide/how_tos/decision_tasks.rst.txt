==============
Decision Tasks
==============

Decision tasks are :py:class:`~upstage_des.task.Task` s that take zero time and were briefly demonstrated in
:doc:`Rehearsal </user_guide/tutorials/rehearsal>`. The purpose of a Decision task is to allow decision making and
:py:class:`~upstage_des.task_networks.TaskNetwork` routing without moving the simulation clock and do so
inside of a Task Network.

A decision task must implement two methods:

* :py:class:`~upstage_des.task.DecisionTask.make_decision`
* :py:class:`~upstage_des.task.DecisionTask.rehearse_decision`

Neither method outputs anything. The expectation is that inside these methods you modify the task network using:

* :py:meth:`upstage_des.actor.Actor.clear_task_queue`: Empty a task queue
* :py:meth:`upstage_des.actor.Actor.set_task_queue`: Add tasks to an empty queue (by string name) - you must empty the queue first.
* :py:meth:`upstage_des.actor.Actor.set_knowledge`: Modify knowledge

The difference between making and rehearsing the decision is covered in the tutorial. The former method
is called during normal operations of UPSTAGE, and the latter is called during a
rehearsal of the task or network. It is up the user to ensure that no side-effects occur during the
rehearsal that would touch non-rehearsing state, actors, or other data.

There is one class variable that can be set on each subclass of the decision task, which is ``DO_NOT_HOLD``:

.. code-block:: python

    class Thinker(UP.DecisionTask):
        DO_NOT_HOLD = True # default is False
        def make_decision(): ...

This feature lets the user turn off zero time holding on decision tasks, which causes decision
tasks to move right into the next task without allowing anything else to run. For examples and
reasoning, see the following section.

This feature is most applicable for avoiding race conditions in decision making where a
follow-on task can alter the simulation with its first yield such that other decisions
make would become incorrect [#f1]_. This would only occur for equally-timed decision processes,
and only for the first yield in a Task that follows the decision. For example, deciding
which ``Store`` to queue on may result in an Actor waiting when no wait was expected.

Zero Time Considerations
------------------------

Decision tasks are meant to not advance the clock, but they do cause a zero-time timeout to be
created. This is done to provide other events in the queue the chance to complete at the same
time step before the task network proceeds for the current actor.

Here is a short example of the default behavior:

.. code-block:: python

    import upstage_des.api as UP

    class Waiter(UP.Task):
        def task(self, *, actor):
            print(f"{self.env.now:.1f} >> {actor.name} in Waiter")
            yield UP.Wait(1.0)

    class Runner(UP.Task):
        def task(self, *, actor):
            print(f"{self.env.now:.1f} >> {actor.name} in Runner")
            yield UP.Wait(2.0)

    class Thinker(UP.DecisionTask):
        def make_decision(self, *, actor):
            print(f"{self.env.now:.1f} >> {actor.name} in Thinker")
            if "one" in actor.name:
                self.set_actor_task_queue(actor, ["Waiter"])
            else:
                self.set_actor_task_queue(actor, ["Runner"])

    net = UP.TaskNetworkFactory(
        name="Example Net",
        task_classes={"Waiter": Waiter, "Runner":Runner, "Thinker":Thinker},
        task_links={
            "Waiter":UP.TaskLinks(default="Thinker", allowed=["Thinker"]),
            "Thinker":UP.TaskLinks(default="", allowed=["Waiter", "Runner"]),
            "Runner":UP.TaskLinks(default="Thinker", allowed=["Thinker"]),
        },
    )

    with UP.EnvironmentContext() as env:
        a = UP.Actor(name="Actor one", debug_log=True)
        b = UP.Actor(name="Actor two", debug_log=True)

        for actor in [a,b]:
            n = net.make_network()
            actor.add_task_network(n)
            actor.start_network_loop(n.name, "Waiter")

        env.run(until=2)

The result is:

.. code-block:: python

    >>> 0.0 >> Actor one in Waiter
    >>> 0.0 >> Actor two in Waiter
    >>> 1.0 >> Actor one in Thinker
    >>> 1.0 >> Actor two in Thinker
    >>> 1.0 >> Actor one in Waiter
    >>> 1.0 >> Actor two in Runner

Even though ``Actor one`` gets to the decision task first, the internal timeout
preserves ordering of the stops. This would happen even if there was no timeout,
because UPSTAGE yields on the decision task as a simpy process.

If we were to skip yielding on the process of a ``DecisionTask``, then this ordering
of output would result:

.. code-block:: python

    ...
    # The only modification is to add DO_NOT_HOLD = True
    class Thinker(UP.DecisionTask):
        DO_NOT_HOLD = True
        def make_decision(self, *, actor):
    ...

    >>> 0.0 >> Actor one in Waiter
    >>> 0.0 >> Actor two in Waiter
    >>> 1.0 >> Actor one in Thinker
    >>> 1.0 >> Actor one in Waiter
    >>> 1.0 >> Actor two in Thinker
    >>> 1.0 >> Actor two in Runner

Note that ``Actor one`` starts the ``Waiter`` task (and stops at the first yield inside)
before ``Actor two`` gets to its decision task.

Turning off the hold using ``DO_NOT_HOLD = True`` gives a guarantee to ``Actor two`` that
the simulation they see in ``Thinker`` is what they will encounter in the first yield in
``Runner``.


.. [#f1] Needing this feature may be a code smell, depending on the situation. Take care
   to check that other ways of deciding and queueing might be better suited.
