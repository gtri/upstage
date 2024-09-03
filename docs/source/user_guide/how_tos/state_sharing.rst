=============
State Sharing
=============

State sharing is a way to share a state on an actor between multiple task networks.

The only currently implemented feature that shares state is the :py:class:`~upstage.state_sharing.SharedLinearChangingState`.

This is an advanced feature that will require a user to subclass and create their own sharing state for their specific use case.


Shared Linear Changing State
----------------------------

The :py:class:`~upstage.state_sharing.SharedLinearChangingState` allows multiple networks to draw from a linear changing state. See the ``test_nucleus_state_share`` test for a complete example.

In that example, a mothership refuels a flyer, both of which draw from the same ``SharedLinearChangingState`` fuel level. In that example, the flyer actor doesn't directly draw from the mothership.
Instead, the flyer tells the mothership that a draw will happen, and the mothership creates a new task network that draws that fuel from itself. That fuel is in addition to fuel burned while flying.

The way the state manages this is by (see :doc:`Active States <active_states>` for information about active states) holding a list of tasks that are drawing from the state:

.. code-block:: python

    # grab data from `get_activity_data`
    if "task" in data:
        rate_to_add: float = data["rate"]
        task: Task = data["task"]
        if task in rate_tasks:
            raise UpstageError(
                f"Duplicate task setting a rate {task}"
                f"setting {self.name} on {instance}."
                "You may have forgotten to deactivate."
            )
        rate_tasks[task] = rate_to_add

and then removing those rates when the state is deactivated from a particular task/task network.


Creating Your Own
-----------------

There's no explicit API for defining your own sharing state, other than to subclass from State or ActiveState and go from there.

This is because, while UPSTAGE wants to enforce many good practices, it's difficult to enforce a particular workflow from state changes back to the task network. This is why the Nucleus must
be explicitly defined and why it also uses interrupts, rather than another concept, to manage state changes. 

In some cases, you may be able to get away with pure decrements:

.. code-block:: python

    class Thinker(UP.Actor):
        cognition = UP.State[float](valid_types=float, default=1.0)

    class DoThinking(UP.Task):
        def task(self, *, actor: Thinker):
            task_cognition_needs = self.get_actor_knowledge(actor, "brain power")
            if actor.cognition < task_cognition_needs:
                raise UP.SimulationError("Not enough brain power!")
            actor.cognition -= task_cognition_needs
            yield UP.Wait(some_time_for_task)
            actor.cognition += task_cognition_needs

If you do that mechanism, you'll need to handle interrupts that remember how much decrement you applied, then put it back.

A more difficult use case is a shared state that follows a "allocate full, but someone can use some and you get less" pattern. There's an example of that in :doc:`nucleus`. That concept won't
work directly with an ActiveState because you would need to restart the task to modify time to complete - which would de-allocate and cause some looping problems in the nucleus.

In general, a shared state is best for when each task just uses or changes part of the state without concern for the other tasks. Nucleus is probably the better way to handle everything else.
