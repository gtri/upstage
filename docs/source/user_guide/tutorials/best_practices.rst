==============
Best Practices
==============

Actors
======

Use knowledge when you want to add built-in enforcement/overwrite checking. States don't have that by default, so you'd have to write more validation rules in tasks
rather than mostly business logic.

There's built-in signature building for Actors based on the states, but it only works in the interpreter.


Tasks
=====

Keep tasks as small as possible. This makes handling interrupts much easier. Use the Task Networks to compose smaller tasks, and use decision tasks to navigate the network.

When doing interrupts, don't be afraid to throw exceptions everywhere. It's hard to predict what might cause an interrupt (depending), so always give yourself as much information
as you can.

Mixing nucleus and ``set_knowledge_event`` for task running might get confusing. Choose nucleus features for task networks that have multiple sources of interrupts. For simpler
holding events (waiting for a job to do, e.g.) that single entity will command to start, knowledge events are better.


Testing
=======

Write tests for your individual tasks to make sure you see the expected changes. Use ``Task().run(actor=actor)`` in an EnvironmentContext to do that.

The more clearly defined your stores/interfaces are, the easier it is to test. 

Actor Interactions
==================

Interaction between different actors is sometimes easier to accomplish with a Task operated by a higher-level actor that waits for enough actors to say they are ready
(usually via a store). Then the higher-level actor can add knowledge, modify task queues, and send the actors on their way. 

Even if the behavior being modeled would be decided mutually by the actors (no strict command hierarchy, e.g.), it can be much easier in DES to run that as a separate
process.

Yielding on a Get is nice for comms and commands, but that usually needs to be a separate task network with tasks that:

1. Wait for the message
2. Get the message, decide what to do
3. Analyze the actor's current state
4. Interrupt and recommand as needed

There are edge cases when you re-command a Task Network, but the re-command/interrupt is sorted later in the event queue (even with zero-time waits). To mitigate this
problem, put very small (but non-zero) waits after a message is received to give some time for the new task networks to change, so they are ready for new interrupts if 
a message immediately follows another.


Geography
=========

The ``GeodeticLocationChangingState`` isn't perfectly accurate when it reaches its destination. Floating point errors and the like will make it be slightly off the destination.

THe amount of difference will be very small, and practically shouldn't matter in most cases. Be aware of this, and set locations explicitly after deactivating them if you need the
precision.


Simulation Determinism
======================

While Python 3.10+ generally guarantee that all dictionaries act in an insertion-ordered manner, that order might change from run to run, even if the random seed is the same.
If your simulations are not deterministic even with a controlled random seed, it is likely due to lack of determinism in dictionary access or sorting.

To mitigate this, you'll need to implement some kind of sorting or hashing that is dependent on something that isn't based on ``id``.

This issue arises frequently in management logic, where actors are selected from lists or dictionaries to perform some task.

Rehearsal
=========

When testing for ``PLANNING_FACTOR_OBJECT``, do so in a method on the task that streamlines the business logic of the main task. For example:

.. code-block:: python

    class DoThing(UP.Task):
        @staticmethod
        def _get_time(item: UP.PLANNING_FACTOR_OBJECT | dict[str, float]) -> float:
            """Return a processing time from an item."""
            if item is PLANNING_FACTOR_OBJECT:
                return 3.0
            return item["process_time"]

        def task(self, *, actor: UP.Actor) -> upstage.type_help.TASK_GEN:
            item = yield UP.Get(actor.some_store, planning_time_to_complete=1.23)
            time = self._get_time(item)
            yield UP.Wait(time)

Rehearsals can get very complicated, and tasks that have lots of process interaction expectations may not rehearse well. Rehearsal is best done for 
simpler, streamlined tasks. Make sure there is a clear code path for rehearsing, and following the advice in the Tasks section of this page will go
a long way to making rehearsals better.

Rehearsal currently only works for one Actor at a time, and while the Actor is clone-able without affecting the rest of the sim, the ``stage`` is not cloned.
If a task references ``stage``, or looks to other actors, events, stores, etc. the rehearsal may cause side-effects in the actual sim.
