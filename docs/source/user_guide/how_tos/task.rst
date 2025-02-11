=====
Tasks
=====

The :py:class:`~upstage_des.task.Task` class is one of the fundamental blocks of an UPSTAGE
simulation. It controls the changes to ``Actor`` states and coordinates with the underlying
SimPy event queue.

Tasks are defined by subclassing from ``Task`` and creating the ``task`` method. In the 
example below, the task is properly typed. UPSTAGE provides a type hint for
the generator object that ``task()`` is. Not also that ``actor`` is a required named
argument.

.. code-block:: python

    import upstage_des.api as UP
    from upstage_des.type_help import TASK_GEN

    class Lathe(UP.Actor):
        outgoing_bin = UP.ResourceState[UP.SelfMonitoringStore]()


    class UseLathe(UP.Task):
        def task(self, *, actor: Lathe) -> TASK_GEN:
            """Run the lathe task."""
            piece = self.get_actor_knowledge("work_piece", must_exist=True)
            time = actor.estimate_work_time(piece)
            yield UP.Wait(time)
            piece.status = "Done"
            actor.number_worked += 1
            yield UP.Put(actor.outgoing_bin, piece)

In that example, the task yields out UPSTAGE :doc:`Events </user_guide/how_tos/events>` only, which is the
typical usage. UPSTAGE will also let you yield a simpy process, but this will raise a warning and is
discouraged as interrupt handling and other services won't work. If a process is yielded on, and your 
task is interrupted, the yielded process will receive an interrupt as well.

Tasks only allow one actor, so use :doc:`Knowledge </user_guide/how_tos/knowledge>` to help
manage interactions or other information. For more complex interactions, see :doc:`State Sharing </user_guide/how_tos/state_sharing>`.

Interrupts
----------

Task interruption, by default, will raise the usual SimPy exception. The user can add the ``on_interrupt`` method
to their task subclass to handle interruption. That method must accept an actor, a cause object, and must return
a enumerator that tells UPSTAGE how to handle the interruption.

See :doc:`Interrupts </user_guide/tutorials/interrupts>` for more.


Decision Tasks
--------------

Decision tasks are a special form of Task that does not touch the simulation queue, except for a zero time wait.
The zero-time wait exists so the user knows that other decision tasks may run before the Actor using the task
proceeds on to the next yield statement.

Subclass and implement ``make_decision`` to use the class. The ``rehearse_decision`` method can also be implemented
to provide rehearsal decision making. That is useful for separating planning and action code when the simpy clock
will not be advancing.

See :doc:`Decision Tasks </user_guide/how_tos/decision_tasks>` for more.

Rehearsal
---------

Rehearsal is a feature for estimating the results of a Task on a "cloned" Actor to examine actor state
for planning purposes. See :doc:`Rehearsal </user_guide/tutorials/rehearsal>` for more.
