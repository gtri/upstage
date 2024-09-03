===============
Task Rehearsal
===============

Task Rehearsal is a powerful feature of UPSTAGE, but one that requires some care to implement. The problem that Rehearsal is trying to solve is
to reduce the amount of excess code needed to plan the usage of Actors.

For example, you may have an Actor that is an Airplane, and you'd like to estimate how long it can fly for. In UPSTAGE, it is possible to rehearse that actor through its 
flight path, using planning factors, and see if the final state is feasible.


Rehearsing a Single Task
========================

Define an actor and a task where some states change:

.. code-block:: python

    from upstage.utils import waypoint_time_and_dist

    class Plane(UP.Actor):
        speed = UP.State[float]()
        location: UP.CartesianLocation = UP.CartesianLocationChangingState()
        fuel: float = UP.LinearChangingState()
        fuel_burn = UP.State[float]()


    class Fly(UP.Task):
        def task(self, *, actor: Plane):
            fly_to: list[UP.CartesianLocation] = self.get_actor_knowledge(actor, "destination", must_exist=True)
            time, dist = waypoint_time_and_dist(actor.location, fly_to, actor.speed)
            print(f"Rehearsing the task: {self._rehearsing}")
            print(f"\tFlying {dist:.2f} units over {time:.2f} hrs")
            actor.activate_linear_state(
                state="fuel",
                rate=-actor.fuel_burn, 
                task=self,
            )
            actor.activate_location_state(
                state="location",
                speed=actor.speed,
                waypoints=fly_to,
                task=self,
            )
            yield UP.Wait(time)
            actor.deactivate_all_states(task=self)

Then rehearse a version of it to get a "cloned" actor with new state:

.. code-block:: python

    with UP.EnvironmentContext() as env:
        plane = Plane(
            name="Plane",
            speed=2.0,
            location=UP.CartesianLocation(0, 0),
            fuel=120,
            fuel_burn=1.5,
        )
        
        point_1 = UP.CartesianLocation(100, 50)
        point_2_options = [
            UP.CartesianLocation(50, 50),
            UP.CartesianLocation(100, 75),
        ]
        
        task = Fly()
        for point_2 in point_2_options:
            fake_plane = task.rehearse(
                actor=plane,
                knowledge={"destination": [point_1, point_2]},
            )
            print(f"Final fuel: {fake_plane.fuel:.2f}\n")
        
        print(f"The original plane's fuel: {plane.fuel}")

    >>>  Rehearsing the task: True
    >>>      Flying 161.80 units over 80.90 hrs
    >>>  Final fuel: -1.35
    >>>   
    >>>  Rehearsing the task: True
    >>>      Flying 136.80 units over 68.40 hrs
    >>>  Final fuel: 17.40
    >>>
    >>> The original plane's fuel: 120


The key feature is that you call ``rehearse`` on an instance of the task, provide it the actor, and optionally provide any knowledge to give to the actor. Then UPSTAGE runs the task
on a fake environment.

Limits of Rehearsal
===================

Rehearsal currently only works for one Actor at a time, and while the Actor is clone-able without affecting the rest of the sim, the ``stage`` is not cloned.
If a task references ``stage``, or looks to other actors, events, stores, etc. the rehearsal may cause side-effects in the actual sim.

The actor states and knowledge are shallow copies during rehearsal, which is one part of the risk of side effects. Since UPSTAGE only knows what you tell it to do
through the ``yield``, any effects not going through the ``yield`` will likely cause problems for rehearsal.

Rehearsing is best for helping planning code determine which actors are capable of doing a series of tasks that have easily separable side-effects.


Rehearsing Events, Gets, and Puts
=================================

When rehearsing UPSTAGE events, we need to tell UPSTAGE how long to run the fake clock for all non-``Wait`` events. We do this by setting ``planning_time_to_complete`` in the event initialization.

.. code-block:: python

    class ExampleTask(UP.Task):
        def task(self, *, actor: UP.Actor):
            # Wait for a timeout or an event to succeed
            # Pretend 'event' is saved and another process can succeed it
            # This is what actor.create_knowledge_event() does (more later)
            event = UP.Event(planning_time_to_complete=3.0)
            wait = UP.Wait(3.5)
            yield UP.Any(event, wait)
            # When planning, UP.Any will use the earliest planning time


If the planning time for the event were larger than 3.5, then 3.5 would be the time that passes during rehearsal of the ``Any`` event.

``Get`` events generally provide a value or object from the container or store. For rehearsal purposes, UPSTAGE sends a special object to the task:

.. code-block:: python
    :linenos:

    import simpy as SIM

    class OtherTask(UP.Task):
        def task(self, *, actor: UP.Actor):
            shelf: SIM.FilterStore = self.stage.a_shelf
            # Find an item, which is an object that has a `value` attribute
            item = yield UP.FilterGet(
                get_location=shelf,
                filter=lambda x: x.value >= 10, 
                rehearsal_time_to_complete=1.0,
            )
            time_to_work: float
            if item is UP.PLANNING_FACTOR_OBJECT:
                time_to_work = 3.0
            else:
                time_to_work = item.value / 3.14
            yield UP.Wait(time_to_work)

    class Item:
        def __init__(self, value:float):
            self.value = value
            
    class Worker(UP.Actor):
        ...

    with UP.EnvironmentContext() as env:
        store = SIM.FilterStore(env)
        UP.add_stage_variable("a_shelf", store)
        
        actor = Worker(name="example")
        
        task = OtherTask()
        new_actor = task.rehearse(actor=actor)
        print(f"Time of completion: {new_actor.env.now}")
        
        def proc():
            yield env.timeout(1.0)
            yield store.put(Item(value=8))
            yield env.timeout(1.0)
            yield store.put(Item(value=314))
            
        env.process(proc())
        task.run(actor=actor)
        env.run()
        print(f"Actual runtime: {env.now}")

    >>> Time of completion: 4.0
    >>> Actual runtime: 102.0

Testing if a returned item is a ``PLANNING_FACTOR_OBJECT`` is the only approved way to know if the task is being rehearsed. If there are no
``Get`` events (everything is time-based) 

``Put`` events have a planning time to complete as well, and do not touch the actual stores/containers given to those events.


Rehearsing a Task Network
=========================

You can rehearse paths through a task network as well, to allow more complicated decision making tests. 

In this example, the plane is part of a search and rescue team for natural disaster aid. The plane will fly to as many locations as it
can, perform a search, and then fly somewhere else. At the end, it needs to contingency plan for a landing spot that is as far away as possible. Here
we'll use :doc:`/user_guide/how_tos/decision_tasks` as a way to do task network planning for both running and rehearsing.

The full example can be found :doc:`here <rehearsal_sim>`.

Here is the planning portion of the TaskNetwork that lets us plan a long route to rehearse on, using ``rehearse_decision`` from ``DecisionTask``. The ``some_preference_function`` is
just a stub for example purposes, showing how to separate the runtime decision logic from the planning logic.

.. code-block:: python

    class Planner(UP.DecisionTask):
        def make_decision(self, *, actor:Plane):
            go_to_loc = some_preference_function(self.stage.search_spots)
            if go_to_loc is None: # implies we are done with searching
                self.set_actor_task_queue(actor, ["Fly", "Land"])
            else:
                self.set_actor_knowledge(actor, "destination", go_to_loc, overwrite=True)       
                self.set_actor_task_queue(actor, ["Fly", "Search"])
            
        def rehearse_decision(self, *, actor:Plane):
            # Pop off a destination from the queue, or go "home"
            next_dests:list[list[UP.CartesianLocation]] | None= self.get_actor_knowledge(actor, "destination_plan", must_exist=False)
            dests: list[UP.CartesianLocation]
            task_queue: list[str]
            if not next_dests: # fly home
                dests = [UP.CartesianLocation(0, 0)]
                task_queue = ["Fly", "Land"]
            else: # pop a location from the plan
                dests = next_dests.pop(0)
                self.set_actor_knowledge(actor, "destination_plan", next_dests, overwrite=True)
                task_queue = ["Fly", "Search"]
            
            self.set_actor_knowledge(actor, "destination", dests, overwrite=True)
            self.set_actor_task_queue(actor, task_queue)

When we run the rehearsal, we make sure to set ``end_task`` to be ``Land``, so that the network looping takes over from the initial task queue we gave it. If 
we hadn't given ``end_task``, the rehearsal would have stopped after the 3 tasks in the ``task_name_list``.

.. code-block:: python

    with UP.EnvironmentContext() as env:
        search_locs = [
            [UP.CartesianLocation(x, y)]
            for x, y in [
                (10, 20),
                (30, 10),
                (15, 15),
            ]
        ]
        
        plane = Plane(
            name="searcher",
            speed=2,
            fuel=200,
            fuel_burn=5.0,
            location=UP.CartesianLocation(20, 10),
            debug_log=True,
        )

        net = search_network.make_network()
        plane.add_task_network(net)
        
        new_plane = plane.rehearse_network(
            net.name,
            task_name_list=["Planner", "Fly", "Search"],
            knowledge={"destination_plan": search_locs},
            end_task="Land",
        )
        print(f"Fuel left: {new_plane.fuel}")
        print(f"Time passed: {new_plane.env.now}")
        print(f"Actual time passed: {env.now}")
    
    >>> Rehearsing the task: True
    >>>         Flying 14.14 units over 7.07 hrs
    >>> Rehearsing the task: True
    >>>         Flying 0.00 units over 0.00 hrs
    >>> Rehearsing the task: True
    >>>         Flying 22.36 units over 11.18 hrs
    >>> Rehearsing the task: True
    >>>         Flying 15.81 units over 7.91 hrs
    >>> Rehearsing the task: True
    >>>         Flying 21.21 units over 10.61 hrs
    >>> Fuel left: 6.181482162082084
    >>> Time passed: 38.76370356758358
    >>> Actual time passed: 0.0
