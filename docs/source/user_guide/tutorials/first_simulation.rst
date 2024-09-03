========================
First UPSTAGE Simulation
========================
.. include:: ../../class_refs.txt

This simulation will demonstrate the primary features of UPSTAGE in a very simple scenario. The goal is demonstrate not just the core UPSTAGE features, but the 
interaction of UPSTAGE with SimPy.

--------
Scenario
--------

A single cashier works at grocery store. They go to the checkout line, scan groceries, take breaks, and come back to the line. 

The code for the full example can be :doc:`found here <first_sim_full>`.

-------
Imports
-------

We prefer this syntax for importing UPSTAGE and SimPy:

.. code-block:: python

    import upstage.api as UP
    import simpy as SIM

    print("hello world")


--------------------------
Define an Actor with State
--------------------------

An UPSTAGE Actor is a container for State, along with methods for modifying the states, for changing tasks, and recording data.

Let's imagine our Cashier has the ability to scan items at a certain speed, and some time until they get a break. We begin by subclassing |Actor| and including two |State| class variables:

.. code-block:: python

    class Cashier(UP.Actor):
        # items per minute
        scan_speed = UP.State[float](
            valid_types=(float,),
            frozen=True,
        )
        # minutes until break
        time_until_break = UP.State[float](
            default=120.0,
            valid_types=(float,),
            frozen=True,
        ) 
    

Our Cashier is very simple, it contains two states that are primarily data containers for attributes of the cashier. This is typical for an UPSTAGE Actor.

The ``scan_speed`` state is defined to require a ``float`` type (UPSTAGE will throw an error otherwise), and is ``frozen``, meaning that it cannot be changed once defined. The ``time_until_break``
state is similar, except that a default value of 120 minutes is supplied.

.. note::
    There is no explicit time dimension in UPSTAGE. The clock units are up to the user, and the user must ensure that all times are properly defined. If you set a stage variable of ``time_unit``, 
    it will correct the time for debug logging strings (into hours) only.


Then you will later instantiate a cashier with [#f1]_:

.. code-block:: python

    cashier = Cashier(
        name="Theoden",
        scan_speed=10.0,
        time_until_break=100.0,
        debug_log=True,
    )

Note that the `name` attribute is required for all UPSTAGE Actors. Also, all inputs are keyword-argument only for an Actor. The ``debug_log`` input is ``False`` by default,
and when ``True``, you can call ``cashier.log()`` to retrieve an UPSTAGE-generated log of what the actor has been doing.

States are just Python descriptors, so you may access them the same as you would any instance attribute: ``cashier.scan_speed```, e.g.

We want to keep track of the number of items scanned, so let's add a state that records the time at which items are scanned.


.. code-block:: python

    class Cashier(UP.Actor):
        # items per minute
        scan_speed = UP.State[float](
            valid_types=(float,),
            frozen=True,
        )
        # minutes until break
        time_until_break = UP.State[float](
            default=120.0,
            valid_types=(float,),
            frozen=True,
        )
        items_scanned = UP.State[int](
            default=0,
            valid_types=(int,),
            recording=True,
        )
        time_scanning: float = UP.LinearChangingState(
            default=0.0,
            valid_types=(float,),
        )


Note that the keyword-argument ``recording`` has been set to ``True``. Now, whenever that state is modified, the time and value will be recorded.


.. code-block:: python

    with UP.EnvironmentContext() as env:
        c = Cashier(name="bob", scan_speed=12.0)
        
        c.items_scanned += 1
        env.run(until=1.2)
        c.items_scanned += 3
        print(c._items_scanned_history)
    >>> [(0.0, 1), (1.2, 4)]


UPSTAGE creates the recording attribute on the instance with ``_<state_name>_history`` to store the tuples of ``(time, value)`` for the state on all recorded states. This is compatible with
all states, including Locations, Resources, and states that are lists, tuples, or dicts (UPSTAGE makes deep copies).

Note that now we have created a SimPy ``Environment`` in ``env`` using the |EnvironmentContext| context manager. This gives Actor instances access to the simulation clock (``env.now``). The
environment context and features will be covered more in depth later.

When we run the environment forward and change the ``items_scanned`` state, the value is recorded at the current simulation time.

Let's also make an Actor for the checkout lane, so we have a simple location to store customer queueing:

.. code-block:: python

    class CheckoutLane(UP.Actor):
        customer_queue = UP.ResourceState[SIM.Store]()

    with UP.EnvironmentContext() as env:
        lane = CheckoutLane(
            name="FirstLane",
            customer_queue={
                "kind": UP.SelfMonitoringStore,
                "capacity":10,
            }
        )

Here we use the built-in |ResourceState| to use a |SelfMonitoringStore| as an Actor state. The self-monitoring store is a subclass of the SimPy ``Store`` that records the number of items
in the store whenever there is a get or put. The ``ResourceState`` could accept a default and not require a definition in the instantiation, but here we are demonstrating how to instantiate 
a ``ResourceState`` in a way that lets you parameterize the store's values (in this case, the kind and the capacity). Other resources, such as containers, will have capacities and initial values.

Actors also have ``knowledge``, which is a simple dictionary attached to the actor that has an interface through the actor and tasks. This allows actors to hold runtime-dependent information
that isn't tied to a state. Knowledge can be set and accessed with error-throwing checks for its existence, or for checks that it doesn't already have a value. An example is given later.

----------------------------
Define Tasks for the Cashier
----------------------------
We want the cashier to do a series of tasks:

#. Show up to work
#. Go to the checkout lane the "store manager" tells them.
#. Wait for a customer OR break time
#. If customer: Scan items and receive payment
#. If break: take a break, then return to wait.
#. On store closing, leave.

Let's define the tasks that wait for a customer and check the customer out. 

.. code-block:: python
    :linenos:

    from typing import Generator
    from upstage.type_help import TASK_GEN


    class WaitInLane(UP.Task):
        def task(self, *, actor: Cashier) -> TASK_GEN:
            """Wait until break time, or a customer."""
            lane: CheckoutLane = self.get_actor_knowledge(
                actor,
                "checkout_lane",
                must_exist=True,
            )
            customer_arrival = UP.Get(lane.customer_queue)
            
            start_time = self.get_actor_knowledge(
                actor,
                "start_time",
                must_exist=True,
            )
            break_start = start_time + actor.time_until_break
            wait_until_break = break_start - self.env.now
            break_event = UP.Wait(wait_until_event)
            
            yield UP.Any(customer_arrival, break_event)
            
            if customer_arrival.is_complete():
                customer: int = customer_arrival.get_value()
                self.set_actor_knowledge(actor, "customer", customer, overwrite=True)
            else:
                customer_arrival.cancel()
                self.set_actor_task_queue(actor, ["Break"])


    class DoCheckout(UP.Task):
        def task(self, *, actor: Cashier) -> TASK_GEN:
            """Do the checkout"""
            items: int = self.get_actor_knowledge(
                actor,
                "customer",
                must_exist=True,
            )
            per_item_time = actor.scan_speed / items
            actor.activate_linear_state(
                state="time_scanning",
                rate=1.0,
                task=self,
            )
            for _ in range(items):
                yield UP.Wait(per_item_time)
                actor.items_scanned += 1
            actor.deactivate_all_states(task=self)
            # assume 2 minutes to take payment
            yield UP.Wait(2.0)


Let's step through the task definitions line-by-line.

* Line 1-2: Typing help. Tasks create generators that yield UPSTAGE Events.

* Line 4: Create a subclass of a ``Task``.

* Line 5: Task subclasses must implement ``task`` that takes a single keyword argument: ``actor``.

* Line 7-11: Assume the cashier has some "knowledge" about the checkout lane they are going to (the store manager will give this to them).

  * The knowledge has the name "checkout_lane", and we assume it must exist, or else throw an error.

* Line 12: Create a ``Get`` event that waits to get a customer from the lane's ResourceState. Note that we aren't yielding on this event yet.

* Line 14-18: Get information about the actor's break time.

  * We could use ``actor.get_knowledge``, but using the task's method puts extra information into the actor's log, if you have it enabled.

* Line 19-21: Get the time left in the sim until it's a break, and create a simple ``Wait`` event to succeed at that time.

* Line 23: Yield an ``Any`` event, which succeeds when the first of its sub-events succeeds.

* Line 25: Test if the customer event succeeded first with the ``Event`` method ``is_complete``.

* Line 26-27: If it did succeed, call ``get_value`` on the ``Get`` event to get customer information and add it to our knowledge.

  * Here we just treat the customer information as an integer number of items. It could be anything.

* Line 29: Cancel the ``Get`` event. Otherwise, it will still exist and take a customer away if one shows up.

  * Later, when discussing interrupting, we'll see how UPSTAGE does this automatically in some instances.

* Line 30: We haven't covered ``TaskNetworks`` yet, but the ``set_actor_task_queue`` method controls what task happens next.

  * Here we are saying that if we've reached our break time, ignore customers and move on to the ``Break`` task.

  * We didn't define the task to go to if we see a customer, because we'll make that implicit in a few steps.

* Line 34: Create a task to check the customers out.

* Line 37-41: Retrieve the knowledge we set in the previous task. 

  * Notice how knowledge lets us be flexible about what our Actors can do, and how ``must_exist`` will help us ensure our tasks are doing the right thing.

* Line 43-47: Activate a linear changing state, which increases its value according to ``rate`` as the simulation runs.

  * We haven't talked about these yet, but check out the How To's for more: :doc:`/user_guide/how_tos/active_states`.

* Line 48-50: Scan each item at the specified rate, and increment the cashier's data.

* Line 51: Stop the ``time_scanning`` linear changing state from accumulating value.

* Line 53: Assume some follow-on wait for customer payment.

This is the foundation of how UPSTAGE manages behaviors. The simulation designer creates ``Tasks`` that can be chained together to perform actions, modify data, and make decisions.

There is one other kind of Task, a |DecisionTask|, which does not consume the environment clock, and will not yield any events [#f2]_.

.. code-block:: python
    
    class Break(UP.DecisionTask):
        def make_decision(self, *, actor: Cashier) -> None:
            """Decide what kind of break we are taking."""
            actor.breaks_taken += 1
            if actor.breaks_taken == actor.breaks_until_done:
                self.set_actor_task_queue(actor, ["NightBreak"])
            elif actor.breaks_taken > actor.breaks_until_done:
                raise UP.SimulationError("Too many breaks taken")
            else:
                self.set_actor_task_queue(actor, ["ShortBreak"])


That task has the ``make_decision`` method that needs to be sublcassed. The purpose of a `DecisionTask` is to set and clear actor knowledge, and modify the task queue without consuming the clock. 
It has additional benefits for rehearsal, which will be covered later.


A note on UPSTAGE Events
------------------------

UPSTAGE Events are custom wrappers around SimPy events that allow for accessing data about that event, handling the ``Task`` internal event loop, and for rehearsal.

All ``Task`` s should yield UPSTAGE events, with one exception. A SimPy ``Process`` can be yielded out as well, but this will warn the user, and is generally not recommended.

The event types are:

#. :py:class:`~upstage.events.Event`: Mimics SimPy's raw ``Event``, useful for marking pauses until a success.

   * See :py:meth:`~upstage.actor.Actor.create_knowledge_event` for a use case.

#. :py:class:`~upstage.events.All`: Succeed when all passed events succeed

#. :py:class:`~upstage.events.Any`: Succeed when any passed events succeed

#. :py:class:`~upstage.events.Get`: Get from a store or container

#. :py:class:`~upstage.events.FilterGet`: A get with a filter function

#. :py:class:`~upstage.events.Put`: Put something into a store or container

#. :py:class:`~upstage.events.ResourceHold`: Put and release holds on limited resources

#. :py:class:`~upstage.events.Wait`: A standard SimPy timeout


------------------------------------
Define a TaskNetwork for the Cashier
------------------------------------

The flow of Tasks is controlled by a TaskNetwork, and the setting of the queue within tasks. A Task Network is defined by the nodes and the links:

.. code-block:: python

    task_classes = {
        "GoToWork": GoToWork,
        "TalkToBoss": TalkToBoss,
        "WaitInLane": WaitInLane,
        "DoCheckout": DoCheckout,
        "Break": Break,
        "ShortBreak": ShortBreak,
        "NightBreak": NightBreak,
    }

    task_links = {
        "GoToWork": UP.TaskLinks(default="TalkToBoss",allowed=["TalkToBoss"]),
        "TalkToBoss": UP.TaskLinks(default="WaitInLane",allowed=["WaitInLane"]),
        "WaitInLane": UP.TaskLinks(default="DoCheckout",allowed=["DoCheckout", "Break"]),
        "DoCheckout": UP.TaskLinks(default="WaitInLane",allowed=["WaitInLane"]),
        "Break": UP.TaskLinks(default="ShortBreak",allowed=["ShortBreak", "NightBreak"]),
        "ShortBreak": UP.TaskLinks(default="WaitInLane",allowed=["WaitInLane"]),
        "NightBreak": UP.TaskLinks(default="GoToWork",allowed=["GoToWork"]),
    }

    cashier_task_network = UP.TaskNetworkFactory(
        name="CashierJob",
        task_classes=task_classes,
        task_links=task_links,
    )

The task classes are given names, and those strings are used to define the default and allowable task ordering. The task ordering need to know the default task (can be None) and the allowed tasks.
Allowed tasks must be supplied. If no default is given, an error will be thrown if no task ordering is given when a new task is selected. If the default or the set task queue violates the 
allowed rule, an error will be thrown.

The task network forms the backbone of flexible behavior definitions, while a ``DecisionTask`` helps control the path through the network.

The ``cashier_task_network`` is a factory that creates network instances from the definition that actors can use (one per actor/per network).

To start a task network on an actor with the factory:

.. code-block:: python

    net = cashier_task_network.make_network()
    cashier.add_task_network(net)
    cashier.start_network_loop(net.name, "GoToWork")

You can either start a loop on a single task, or define an initial queue through the network if desired:

.. code-block:: python

    net = cashier_task_network.make_network()
    cashier.add_task_network(net)
    cashier.set_task_queue(net.name, ["GoToWork", "TalkToBoss"])
    cashier.start_network_loop(net.name)


A note on TaskNetworkFactory
----------------------------

The :py:class:`~upstage.task_network.TaskNetworkFactory` class has some convience methods for creating factories from typical use cases:

#. :py:meth:`~upstage.task_network.TaskNetworkFactory.from_single_looping`: From a single task, make a network that loops itself.

   * Useful for a Singleton task that, for example, receives communications and farms them out or manages other task networks.

#. :py:meth:`~upstage.task_network.TaskNetworkFactory.from_single_terminating`: A network that does one task, then freezes for the rest of the simulation.

#. :py:meth:`~upstage.task_network.TaskNetworkFactory.from_ordered_looping`: A series of tasks with no branching that loops.

#. :py:meth:`~upstage.task_network.TaskNetworkFactory.from_single_looping`: A series of tasks with no branching that terminates at the end.


--------------------
Setting up Customers
--------------------

To complete the simulation, we need to make customers arrive at the checkout lanes. This can be done using a standard SimPy process:

.. code-block:: python

    def customer_spawner(
        env: SIM.Environment,
        lanes: list[CheckoutLane],
    ) -> SIMPY_GEN:
        # We store the RNG on the stage, and this is a quick way to get the stage (steal it from an actor)
        stage = lanes[0].stage
        while True:
            hrs = env.now / 60
            time_of_day = hrs // 24
            if time_of_day <= 8 or time_of_day >= 15.5:
                time_until_open = (24 - time_of_day) + 8
                yield env.timeout(time_until_open)

            lane_pick = stage.random.choice(lanes)
            number_pick = stage.random.randint(3, 17)
            yield lane_pick.customer_queue.put(number_pick)
            yield UP.Wait.from_random_uniform(5.0, 30.0).as_event()


Customers arrive every 5 to 30 minutes, and only show up from the hours of 8 AM to 3:30 PM.

---------------
Running the Sim
---------------

The sim is created with:

.. code-block:: python
    :linenos:

    with UP.EnvironmentContext(initial_time=8 * 60) as env:
        UP.add_stage_variable("time_unit", "min")
        cashier = Cashier(
            name="Bob",
            scan_speed=1.0,
            time_until_break=120.0,
            breaks_until_done=4,
            debug_log=True,
        )
        lane_1 = CheckoutLane(name="Lane 1")
        lane_2 = CheckoutLane(name="Lane 2")
        boss = StoreBoss(lanes=[lane_1, lane_2])

        UP.add_stage_variable("boss", boss)

        net = cashier_task_network.make_network()
        cashier.add_task_network(net)
        cashier.start_network_loop(net.name, "GoToWork")

        customer_proc = customer_spawner(env, [lane_1, lane_2])
        _ = env.process(customer_proc)

        env.run(until=20 * 60)


Going through the lines:

* Line 1: The simulation starts at 8 AM (in minutes).

* Line 2: We set a stage variable (accessible through globals) that we are doing time in minutes (just for logging).

* Line 3-9: Create a cashier that needs breaks every 2 hours, the 4th of which means they can go home.

* Line 10-12: Create two checkout lanes, and a ``StoreBoss`` that the cashier uses to get a lane assigned.

* Line 14: Add the ``StoreBoss`` to the global stage.

  * In the ``TalkToBoss`` task, the task calls: ``boss: StoreBoss = self.stage.boss``

* Line 16-18: Create and start the task network on the cashier.

* Lines 20-21: Use SimPy to run the customer event.

* Line 23: Run for 20 simulation hours.


Since only one cashier is assigned, you can examine the backlog on the lanes (and the cashiers progress) with:

.. code-block:: python

    print(lane_1.customer_queue._quantities)
    >>> [(495.0, 0),
    >>> (512.0, 1),
    >>> (512.0, 0),
    >>> (682.913493237309, 1),
    >>> (682.913493237309, 0),
    >>> (729.4798348277678, 1),
    >>> (729.4798348277678, 0),
    >>> (783.0901071872663, 1),
    >>> (783.0901071872663, 0),
    >>> (1087.3217585080076, 1)]

    print(lane_2.customer_queue._quantities)
    >>> [(566.5416040656762, 0),
    >>> (566.5416040656762, 1),
    >>> (622.3573572404293, 2),
    >>> (836.9173054961495, 3),
    >>> (876.4624776047534, 4),
    >>> (926.2323723216172, 5),
    >>> (971.9681436809026, 6),
    >>> (1033.381298927381, 7),
    >>> (1136.5736387094469, 8),
    >>> (1188.3694502822516, 9)]

    print(cashier._items_scanned_history)
    >>> ...
    >>> (683.5134932373091, 15),
    >>> (683.6134932373092, 16),
    >>> (683.7134932373092, 17),
    >>> (683.8134932373092, 18),
    >>> (683.9134932373092, 19),
    >>> (729.6048348277678, 20),
    >>> (729.7298348277678, 21),
    >>> (729.8548348277678, 22),
    >>> (729.9798348277678, 23),
    >>> ...


Your run may be different, due to the calls to ``stage.random`` (a passthrough for ``random.Random()``). See :doc:`Random Numbers </user_guide/how_tos/random_numbers>` for more.

Notice how lane 1 takes customers right away, but lane 2 stacks up. Also notice how the ``SelfMonitoringStore`` creates the ``._quantities`` datatype that shows the time history of number of 
items in the store. If it was a Container, instead of a Store, it would record the level.

.. [#f1] You can run this now and ignore the warning about an environment.
.. [#f2] This is not strictly true, it does yield a zero time timeout under the hood.
