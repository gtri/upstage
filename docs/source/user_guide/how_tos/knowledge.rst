=========
Knowledge
=========

Knowledge is a property of an :py:meth:`~upstage_des.actor.Actor` that is intended to be a
temporary space for storing information about the Actor's goals or perception. While many
actions that use knowledge could be accomplished with :doc:`States <states>`, knowledge is
created separately to include other checks and debug logging support.

Knowledge is also used to store events that are known only to an Actor to support some process
continuation patterns, described farther below.

Knowledge is accessed and updated through:

* :py:meth:`upstage_des.actor.Actor.get_knowledge`

  * ``name``: The name of the knowledge.

  * ``must_exist``: Boolean for raising an exception if the knowledge does not exist.

* :py:meth:`upstage_des.task.Task.get_actor_knowledge`

  * ``actor``: The actor that has the knowledge.

  * ``name`` and ``must_exist``, as above.

* :py:meth:`upstage_des.actor.Actor.set_knowledge`

  * ``name``: The name of the knowledge to set.

  * ``value``: Any object to set as the value.

  * ``overwrite``: Boolean for allowing an existing value to be changed. Defaults to False, and will raise an exception if not allowed to overwrite.

  * ``caller``: Optional information - through a string - of who is calling the knowledge set method. This records to the actor debug log, if enabled.

* :py:meth:`upstage_des.task.Task.set_actor_knowledge`

  * ``actor``: The actor that you want to set knowledge on.

  * All other inputs as above, except that ``caller`` is filled out for you.

* :py:meth:`upstage_des.actor.Actor.clear_knowledge`

  * ``name``: The name of the knowledge to delete.

  * ``caller``: Same as above.

* :py:meth:`upstage_des.task.Task.clear_actor_knowledge`

  * ``actor``: The actor to delete knowledge from.

  * All other inputs as above, except that ``caller`` is filled out for you.


The actor knowledge can be set and retrieved from the actor itself, and the ``Task`` convenience methods are there
to provide data to the actor debug log (if ``debug_logging=True`` is set on the Actor) to help trace where an actor's
information came from.


Knowledge Patterns
------------------

Knowledge is most useful for temporary information, such as waypoints for travel, goals to set, or similar data.



Bulk Knowledge
--------------


Knowledge Events
----------------

It is often times useful to hold an actor in a task until an event succeeds. UPSTAGE Actors
have a :py:meth:`~upstage_des.actor.Actor.create_knowledge_event` and :py:meth:`~upstage_des.actor.Actor.succeed_knowledge_event`
method to support this activity (also described in :doc:`Events </user_guide/how_tos/events>`)

.. code-block:: python

    HAIRCUT_DONE = "haircut is done"

    class Chair(UP.Actor):
        sitting = UP.ResourceState[UP.SelfMonitoringStore]()

    
    class Customer(UP.Actor):
        hair_length = UP.State[float](recording=True)

    
    class Haircut(UP.Task):
        def task(self, *, actor: Customer):
            assigned_chair = self.get_actor_knowledge(
                actor,
                name="chair",
                must_exist=True,
            )
            evt = actor.create_knowledge_event(name=HAIRCUT_DONE)
            yield UP.Put(assigned_chair.sitting, actor)
            yield evt
            print(evt.get_payload())

    
    class DoHaircut(UP.Task):
        def task(self, *, actor: Chair):
            customer = yield UP.Get(actor.sitting)
            yield UP.Wait(30.0)
            customer.hair_length *= 0.5
            customer.succeed_knowledge_event(name=HAIRCUT_DONE, data="Have a nice day!")


The above simplified example shows how UPSTAGE tasks can work with knowledge events to
support simple releases from other tasks without adding stores or other signaling mechanisms.

The succeed event method also clears the event from the knowledge.
