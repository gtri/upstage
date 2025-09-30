==============
Motion Manager
==============

The Motion Manager is an UPSTAGE feature that coordinates Actors that are moving and regions of space that may want to be aware when an Actor enters that region (such as a sensor, or region of a forest fire, etc.).

There are two motion managers. One uses intersection calculations to maintain a discrete-event style of movement, while the other operates at defined time steps. The latter is required to have
motion detection for when the "sensor" and the viewed entities are both moving.

The built-in ``<>LocationChangingState`` states work with any of the motion managers in the background, by alerting them when those states are made activate. If you want to control which Actors are visible to the
motion manager, there is the :py:class:`~upstage_des.states.DetectabilityState` that can be given to an actor and set to ``False``.


Define the Motion Manager
-------------------------

.. code-block:: python
    :linenos:

    from upstage_des.motion.geodetic_model import subdivide_intersection
    from upstage_des.geography.intersections import get_intersection_locations

    with UP.EnvironmentContext():
        motion = UP.SensorMotionManager(
            intersection_model = subdivide_intersection,
            debug=True,
        )
        UP.add_stage_variable("motion_manager", motion)
        UP.add_stage_variable("intersection_model", get_intersection_locations)

* Line 1-2: Import one of the intersection models and a support function (more on this below)
* Line 5: Create the :py:class:`~upstage_des.motion.SensorMotionManager` and give it the intersection model
  * The other option is the :py:class:`~upstage_des.stepped_motion.SteppedMotionManager` class. (Does not need an intersection)
* Line 9: Add the motion manager to the stage so that the ``<>LocationChangingState`` s can find it.
* Line 10: Add the intersection helper function to the stage so the SensorMotionManager class can find it.

The ``SensorMotionManager`` does not need to be started or "run", because it only calculates intersection locations and times when something calls its ``_start_mover`` method - which the LocationChangingStates do
in the background.

Intersection Models
-------------------

There are two intersection models for ``Geodetic`` locations, and one model for ``Cartesian``. The Stepped motion manager does not require one, it uses :py:func:`~upstage_des.data_types.GeodeticLocation.straight_line_distance` at a given rate.

* :py:func:`~upstage_des.motion.geodetic_model.subdivide_intersection`: The approximate intersection method with subdivided search, good for WGS84 coordinates.

  * This requires the stage variable ``intersection_model`` to be set.
  * The only available intersection model is :py:func:`~upstage_des.geography.intersections.get_intersection_locations`

* :py:func:`~upstage_des.motion.geodetic_model.analytical_intersection`: An exact intersection using a Spherical earth model. Incompatible with the WGS84 stage model.
* :py:func:`~upstage_des.motion.cartesian_model.cartesian_linear_intersection`: An exact intersection using for XYZ cartesian space.


The :py:func:`~upstage_des.geography.intersections.get_intersection_locations` function, required by the subdividing intersection, is what actually finds the intersections. The ``subdivide_intersection`` is 
a passthrough function that handles the different earth models, stage variables, and conversion to the format UPSTAGE requires in the ``SensorMotionManager``. The intersection model itself does not have
to know about upstage_des. If you created a ``partial`` of a version of the ``subdivide_intersection`` that took the intersection model as an argument, you would get the same result without needing the stage variable.


Sensor Requirements and Example
-------------------------------

To add a sensor to the motion manager's awareness you must pass it an object that has an attribute for it's location and sensor range. It must also implement ``entity_entered_range`` and
``entity_exited_range`` that accept the entity that is entering/exiting, respectively.

It is up to the user to decide what to do with that information. They could store it in a queue (such as Store) and process that information later, for example.

All UPSTAGE does is call one of those methods according to the schedule. 

.. code-block:: python

    from upstage_des.utils import waypoint_time_and_dist
    from upstage_des.motion.cartesian_model import cartesian_linear_intersection

    class Bird(UP.Actor):
        location = UP.CartesianLocationChangingState()
        detectable = UP.DetectabilityState(default=True)
        speed = UP.State()

    class Fly(UP.Task):
        def task(self, *, actor: Bird):
            waypoints = self.get_actor_knowledge(actor, "waypoints")
            time, dist = waypoint_time_and_dist(actor.location, waypoints, actor.speed)
            actor.activate_location_state(
                state="location",
                speed = actor.speed,
                waypoints = waypoints,
                task=self,
            )
            yield UP.Wait(time)
            actor.deactivate_all_states(task=self)

    class Sensor(UP.Actor):
        spot = UP.State(valid_types=(UP.GeodeticLocation, UP.CartesianLocation))
        dist = UP.State(default=100.0, valid_types=float)

        def entity_entered_range(self, entity):
            xy = f"({entity.location.x:.2f}, {entity.location.y:.2f})"
            print(f"Oh look, A '{entity}' - time: {self.env.now:.2f} - pos: {xy}")

        def entity_exited_range(self, entity):
            xy = f"({entity.location.x:.2f}, {entity.location.y:.2f})"
            print(f"The {entity} left :( - time: {self.env.now:.2f} - pos: {xy}")

    with UP.EnvironmentContext() as env:
        motion = UP.SensorMotionManager(
            intersection_model=cartesian_linear_intersection,
        )
        UP.add_stage_variable("motion_manager", motion)

        viewer = Sensor(
            name="Birdwatcher",
            spot=UP.CartesianLocation(0, 3),
            dist=30.0,
        )
        motion.add_sensor(viewer, location_attr_name="spot", radius_attr_name="dist")
        
        eagle = Bird(name="Eagle", location=UP.CartesianLocation(40, 40), speed=3.0)
        path = [
            UP.CartesianLocation(1, 4),
            UP.CartesianLocation(0, 40),
        ]
        eagle.set_knowledge("waypoints", path)
        Fly().run(actor=eagle)
        # Note that we can run without an end time since the sim is very simple
        env.run()
        >>> Oh look, A 'Bird: Eagle' - time: 8.16 - pos: (22.01, 23.39)
        >>> The Bird: Eagle left :( - time: 27.36 - pos: (0.19, 33.00)



Mover Requirements
------------------

There are no special requirements for the mover other than they must implement motion by activating a LocationChangingState of some kind. That calls into the motion managers ``_start_mover``
method that does all the work.


Stepped Motion
--------------

The time-stepping motion manager works by holding a list of sensing entities and detectable entities, and at each time step, it calculates the ``straight_line_distance`` between each pair.

If the distance is in range, it fires off the ``entity_entered_range`` and marks the entity as in view. If it's out of range and was in view, it calls ``entity_exited_range``. As long as the
location attribute implements ``straight_line_distance``, this manager will work.

The stepped motion manager might need to start a process to do the time stepping:

.. code-block:: python

    with UP.EnvironmentContext():
        motion = UP.SteppedMotionManager(
            timestep=3/60.,
            max_empty_events=3,
        )
        UP.add_stage_variable("motion_manager", motion)
        motion.run()

In this case, we do need to ``run`` the motion manager. We also give it a timestep to operate at (here in 3 minute steps, if the sim clock runs on "hours").

The ``max_empty_events`` is a special parameter to use if you're going to do ``env.run()`` with no ``until``. The stepped motion will run an event every timestep, so your sim will run forever. This
parameter controls how many timesteps with no events queued in the entire sim to consider the simulation to be over and to stop. In general you should always run your sim until a known end point unless
you can be certain it has a guaranteed terminal state.

The run is optional *only* if the things that will be detected are moving using a LocationChangingState. The stepped manager allows anything with a location attribute to be detectable, and in that
case you need to run the motion manager (and add the entity as a detectable, see below).

You can try the same bird example with a SteppedMotionManger:

.. code-block:: python
    
    with UP.EnvironmentContext() as env:
        motion = UP.SteppedMotionManager(
            timestep= 3 / 60.,
        )
        UP.add_stage_variable("motion_manager", motion)
        # This part is optional if you're _only_ moving using a LocationChangingState
        motion.run()

        viewer = Sensor(
            name="Birdwatcher",
            spot=UP.CartesianLocation(0, 3),
            dist=30.0,
        )
        motion.add_sensor(viewer, location_attr_name="spot", radius_attr_name="dist")
        
        eagle = Bird(
            name="Eagle",
            location=UP.CartesianLocation(40, 40),
            speed=3.0,
        )
        path = [
            UP.CartesianLocation(1, 4),
            UP.CartesianLocation(0, 40),
        ]
        eagle.set_knowledge("waypoints", path)
        Fly().run(actor=eagle)
        # Note that we can run without an end time since the sim is very simple
        env.run()
        >>> Oh look, A 'Bird: Eagle' - time: 8.20 - pos: (21.92, 23.31)
        >>> The Bird: Eagle left :( - time: 27.40 - pos: (0.19, 33.11)

Notice the slight inaccuracy in the position due to the time stepping.

.. note::

    The stepped manager is more flexible to the kinds of things that can be detected. You can use
    :py:meth:`~upstage_des.motion.stepped_motion.SteppedMotionManager.add_detectable` to add anything with a
    position. 
