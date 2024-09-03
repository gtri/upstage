=============
Active States
=============

Active States are an UPSTAGE feature where states are told how to update themselves when requested, while not having to modify or alter the timeout they are changing during.

For example, a fuel depot may dispense fuel at a given rate for some amount of time. An employee may monitor that level at certain times. UPSTAGE allows the state to hold its own
update logic, rather than the employee code needing to know when the fuel started changing, at what rate, etc.

Active states are stopped and started with :py:meth:`~upstage.actor.Actor.activate_state` and :py:meth:`~upstage.actor.Actor.deactivate_state`.

Active states are automatically stopped when a Task is interrupted.

Linear Changing State
=====================

The linear changing state is a floating-point state that accepts a rate parameter.

.. code-block:: python

    class DrinkDispenser(UP.Actor):
        vessel: float = UP.LinearChangingState()

    class Dispense(UP.Task):
        def task(self, *, actor: DrinkDispenser):
            time: float = self.get_actor_knowledge(actor, "drink time", must_exist=True)
            rate: float = self.get_actor_knowledge(actor, "flow rate", must_exist=True)

            actor.activate_state(
                state="vessel",
                rate=-rate,
                task=self, # this is for debug logging
            )
            # OR, to get argument hints
            # actor.activate_linear_state(...)
            yield UP.Wait(time)
            actor.deactivate_state(
                state="vessel",
                task=self,
            )
            # OR:
            # actor.deactivate_all_states(task=self)

If you set up the code to run like this:

.. code-block:: python

    with UP.EnvironmentContext() as env:
        fountain = DrinkDispenser(
            name="Fountain",
            vessel=100.0,
        )

        task = Dispense()
        fountain.set_knowledge("drink time", 10.0)
        # It dispenses 2 units per time unit
        fountain.set_knowledge("flow rate", 2.0)

        task.run(actor=fountain)

        env.run(until=5.0)
        print(fountain.vessel)
        >>> 90.0
        # Run until no more events are queued
        env.run()
        print(env.now)
        >>> 10.0
        print(fountain.vessel)
        >>> 80.0


Location Changing States
========================

There are two location changing states, one for Cartesian and one for Geodetic.

They accept a speed and list of waypoints in their activation.

.. code-block:: python

    from upstage.utils import waypoint_time_and_dist

    class FlatlandCar(UP.Actor):
        location: UP.CartesianLocation = UP.CartesianLocationChangingState()
        top_speed = UP.State[float](valid_types=float, frozen=True)


    class Move(UP.Task):
        def task(self, *, actor: FlatlandCar):
            waypoints = self.get_actor_knowledge(actor, "waypoints", must_exist=True)
            time, dist = waypoint_time_and_dist(
                start=actor.location,
                waypoints=waypoints,
                speed=actor.top_speed,
            )
            actor.activate_state(
                state="location",
                speed=actor.top_speed,
                waypoints=waypoints,
                task=self,
            )
            # OR, to get argument hints:
            # actor.activate_location_state(...)
            yield UP.Wait(time)
            actor.deactivate_state(
                state="location",
                task=self,
            )


Then run with:

.. code-block:: python

    with UP.EnvironmentContext() as env:
        car = FlatlandCar(
            name="GoDescarte",
            location=UP.CartesianLocation(0, 0),
            top_speed=5.0,
        )

        task = Move()
        waypoints = [
            UP.CartesianLocation(5, 0),
            UP.CartesianLocation(5, 5),
        ]
        car.set_knowledge("waypoints", waypoints)

        task.run(actor=car)

        env.run(until=0.5)
        print(car.location)
        >>> CartesianLocation(x=2.5, y=0.0, z=0.0)
        env.run(until=1.4)
        print(car.location)
        >>> CartesianLocation(x=5.0, y=1.9999999999999996, z=0.0)
        env.run()
        print(env.now)
        >>> 2.0
        print(car.location)
        >>> CartesianLocation(x=5.0, y=5.0, z=0.0)


The ``GeodeticLocationChangingState`` works the same way.


Creating your own
=================

To create you own Active State, subclass :py:class:`~upstage.states.ActiveState`.

The bare minimum is to implement the ``_active`` method. 

Here is an example of an ActiveState that changes according to an exponent.

.. code-block:: python
    :linenos:

    from upstage.states import ActiveState
    from upstage.actor import Actor

    class ExponentChangingState(ActiveState):
        """A state that changes according to: x_t = x_0 + at^(b)"""
        def _active(self, instance: Actor) -> float | None:
            """Given a geometric rate change, calculate a new value."""
            data = self.get_activity_data(instance)
            now: float = data["now"]
            current: float = data["value"]
            started: float = data.get("started_at")
            if started is None:
                return None
            starting_value = data.get("starting_value", current)
            
            a: float = data["a"]
            b: float = data["b"]

            t = now - started
            to_add = a * (t ** b)
            return_value = starting_value + to_add
            self.__set__(instance, return_value)
            instance._set_active_state_data(
                state_name=self.name,
                started_at=now if started is None else started,
                starting_value = starting_value,
                a=a,
                b=b,
            )
            return return_value


There are several particular steps and nuances, so let's go line by line.

* Line 8: This retrieves activity data stored by your method.
  * Part of the data comes from the key/values in ``activate_state``
  * The ``now``, ``value``, and ``started_at`` keys are given to you.
  * Everything else is created in this method.
* Line 12: If ``started_at`` is None, it means the state isn't activated
    * By returning None, we tell UPSTAGE to just use the last calculated value.
    * By default, when an active state is deactivated, it re-calculates its value.
* Line 14: Since this rule depends on initial value plus a time value, get that value as the one we told the state.
  * If it's none, it means the state has just been activated (it hasn't been set), so use the current value.
* Line 21: Get the value of the state
* Line 22: Set the value to the state, so if anyone asks for it they can get it.
* line 23-29: This is how we re-inject data back to the next time this method is called.

The admitted difficulty here is that there's not currently a good way to hint at how to call ``actor.activate_state``.

Best practice is to document in the docstrings how to call ``activate_state``. UPSTAGE will throw errors if you keyed the kwargs wrong,
but only if you don't use ``data.get()`` for every call. 

Another option is to make a subclass that hints for you:

.. code-block:: python

    class BetterActor(Actor):
        def activate_exponent_state(self, state: str, a: float, b:float, task) -> None:
            self.activate_state(
                state=state,
                a=a,
                b=b,
                task=task,
            )

    class Changing(BetterActor):
        changer: float = ExponentChangingState()

    with UP.EnvironmentContext() as env:
        x = Changing(name="example", changer=100)
        
        # Note that you get useful tab-complete now.
        x.activate_exponent_state("changer", 1.0, 2.0, None)
        env.run(until=5.0)
        # 100 + 1 * 5^2 = 125
        print(x.changer)
        >> 125.0
        env.run(until=10.0)
        # 100 + 1 * 10^2 = 200
        print(x.changer)
        >>> 200.0
        x.deactivate_all_states(task=None)
        print(x.changer)
        >>> 200.0
        # Now with the state deactivated, we'll re-start the exponential climb.
        x.activate_exponent_state("changer", 2.0, 1.0, None)
        env.run(until=20.0)
        # 200 + 2 * (20 - 10)^1 = 220
        print(x.changer)
        >>> 220.0


Note that state activation doesn't require a task. It's just the best place to do it, because task interrupts automatically deactivate all states.
