# 15 Minute UPSTAGE Introduction

The core functionality of UPSTAGE is in the actor - state - task system. This page will introduce you to that system through a simple example of modeling a cashier checking out customers.

The recommended development flow for an UPSTAGE simulation is:

1. Determine the actors and their properties
2. Create the actor classes
3. Determine the tasks and the networks of tasks
4. Create the task classes
5. Create simulation startup and running
6. Gather outputs
7. Test and Iterate

## Scenario Planning: Actors

A single cashier works at grocery store. They go to the checkout line, scan groceries, take breaks, and come back to the line. When thinking about modeling this in UPSTAGE, the three components (cashier, checkout lane, and customers) can be actors. The latter two do not have to be, but creating them as actors allows some data tracking to occur more directly.

When planning an UPSTAGE simulation, you must decide on the attributes of your actors, and the data you want to keep track of about them and their activities. Do this before creating any tasks or interactions.

* Cashier
  * Attributes:
    * Time to scan one item
    * Time needed for a break
    * Time spent working between breaks
    * Time to accept purchase from a customer
  * Data to record:
    * Number of items scanned
    * Number of customers helped
* Checkout Lane:
  * Attributes:
    * Customer queue
  * Data to record:
    * Size of the queue over time
* Customer:
  * Attributes:
    * Number of items being purchased
    * Cash or card for purchase
  * Data to record:
    * Time waiting in line until completed checkout

## Actor Creation

To create anything in UPSTAGE, first import the API and SimPy:

```{code} python
:caption: Standard import lines for UPSTAGE simulations

import upstage_des.api as UP
import simpy as SIM
```

An UPSTAGE Actor is a container for State, along with methods for modifying the states, for changing tasks, and recording data. The Actor class is built to appear like a python `dataclass` to provide type hinting and tab-completion in most IDEs. Every attribute given will become a `State`, and you can use the `State` syntax to define more features for the attribute.

```{code} python
:caption: Creating our first Actor

class Cashier(UP.Actor):
    scan_speed_per_item: float
    break_time: float
    work_until_break: float
    items_scanned: int = UP.State(default=0, recording=True).create()
```

Our Cashier is very simple, it contains three states that are attributes of the cashier, and the final state is used for data recording. This is typical for an UPSTAGE Actor. Note that the keyword-argument ``recording`` has been set to ``True``. Now, whenever that state is modified, the time and value will be recorded.

```{seealso}
Every attribute on an `Actor` is a `State`, even if you don't use all the `State` features. Only set the attribute equal to a `State` to use the additional features. The `.create()` call is used to satisfy type checker, but is not necessary if you are not type checking.

See the [`State` docs](features-states.md) for more information.
```

Then you will later instantiate a cashier with:

```{code} python
:caption: Instantiating an actor

cashier = Cashier(
    name="Theoden",
    scan_speed_per_item=2.0,
    break_time=15.0,
    work_until_break=120.0,
    debug_logging=True,
)
```

Since we supplied a default for the `items_scanned` state, we do not need to include it. The two inputs not defined by our `Cashier` class are `name` and `debug_logging`. The `name` is required, and `debug_logging` is optional, and `False` by default. If turned on, the actor will store any logging information given to `actor.write_to_log()`. See [](features-logging.md) for more details. Also, all inputs are keyword-argument only for an Actor.

```{important}
All values you supply the simulation must be in consistent units. There are features to help with this, which are covered later in the documentation. For this example, our time units are in minutes.
```

The dataclass-like syntax gives IDEs the ability to suggest the initialization without use needing to make `__init__` methods for all our Actors and subclasses.

```{figure} _static/cashier_actor_hinting.png
:label: VSCode Type Hinting Example
:alt: Cashier Initialization Type Hinting
:align: center
```

Let's also make an Actor for the checkout lane and for the customers.

```{code} python
class CheckoutLane(UP.Actor):
    customer_queue: SIM.Store: UP.ResourceState(default=SIM.Store).create()


class Customer(UP.Actor):
    number_of_items: int
    events: str = UP.State(default="Creation", recording=True)
    payment_method: Literal["cash", "card"] = "card"
```

On the `CheckoutLane`, the `ResourceState` handles initializing SimPy resources with environment references without requiring the user to supply `env` on each init.

The `events` state will track when things happen to the customer through recording. Typing with the `Literal` will help your type checker enforce types on initializationa and throughout the simulation. If you want active validation, you can use the `State` initialization:

```{code} python
:caption: Type checking at runtime with States.

class Customer(UP.Actor):
    ...
    payment_method: Literal["cash", "card"] = UP.State(
        default="card",
        type_check_each=True
    ).create()

c = Customer(...)
# This will raise a TypeError
c.payment_method = "bitcoin"
```

## Tasks Planning

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

    from collections.abc import Generator
    from upstage_des.type_help import TASK_GEN


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

* Line 7-11: Assume the cashier has some "knowledge" about the checkout lane
  they are going to (the store manager will give this to them).

  * The knowledge has the name "checkout_lane", and we assume it must exist, or else throw an error.

* Line 12: Create a ``Get`` event that waits to get a customer from the lane's ResourceState.
  Note that we aren't yielding on this event yet.

* Line 14-18: Get information about the actor's break time.

  * We could use ``actor.get_knowledge``, but using the task's method puts extra information
    into the actor's log, if you have it enabled.

* Line 19-21: Get the time left in the sim until it's a break, and create a simple ``Wait``
  event to succeed at that time.

* Line 23: Yield an ``Any`` event, which succeeds when the first of its sub-events succeeds.

* Line 25: Test if the customer event succeeded first with the ``Event`` method ``is_complete``.

* Line 26-27: If it did succeed, call ``get_value`` on the ``Get`` event to get customer information
  and add it to our knowledge.

  * Here we just treat the customer information as an integer number of items. It could be anything.

* Line 29: Cancel the ``Get`` event. Otherwise, it will still exist and take a customer away if one shows up.

  * Later, when discussing interrupting, we'll see how UPSTAGE does this automatically in some instances.

* Line 30: We haven't covered ``TaskNetworks`` yet, but the ``set_actor_task_queue`` method controls what task happens next.

  * Here we are saying that if we've reached our break time, ignore customers and move on to the ``Break`` task.

  * We didn't define the task to go to if we see a customer, because we'll make that implicit in a few steps.

* Line 34: Create a task to check the customers out.

* Line 37-41: Retrieve the knowledge we set in the previous task. 

  * Notice how knowledge lets us be flexible about what our Actors can do, and how ``must_exist`` will
    help us ensure our tasks are doing the right thing.

* Line 43-47: Activate a linear changing state, which increases its value according to ``rate`` as the simulation runs.

  * We haven't talked about these yet, but check out the How To's for more: :doc:`/user_guide/how_tos/active_states`.

* Line 48-50: Scan each item at the specified rate, and increment the cashier's data.

* Line 51: Stop the ``time_scanning`` linear changing state from accumulating value.

* Line 53: Assume some follow-on wait for customer payment.

This is the foundation of how UPSTAGE manages behaviors. The simulation designer creates ``Tasks`` that
can be chained together to perform actions, modify data, and make decisions.

There is one other kind of Task, a |DecisionTask|, which does not consume the environment clock,
and will not yield any events [#f2]_.

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


That task has the ``make_decision`` method that needs to be sublcassed. The purpose of a
`DecisionTask` is to set and clear actor knowledge, and modify the task queue without
consuming the clock. It has additional benefits for rehearsal, which will be covered later.


A note on UPSTAGE Events
------------------------

UPSTAGE Events are custom wrappers around SimPy events that allow for accessing data about
that event, handling the ``Task`` internal event loop, and for rehearsal.

All ``Task`` s should yield UPSTAGE events, with one exception. A SimPy ``Process`` can be
yielded out as well, but this will warn the user, and is generally not recommended.

The event types are:

#. :py:class:`~upstage_des.events.Event`: Mimics SimPy's raw ``Event``, useful for marking pauses until a success.

   * See :py:meth:`~upstage_des.actor.Actor.create_knowledge_event` for a use case.

#. :py:class:`~upstage_des.events.All`: Succeed when all passed events succeed

#. :py:class:`~upstage_des.events.Any`: Succeed when any passed events succeed

#. :py:class:`~upstage_des.events.Get`: Get from a store or container

#. :py:class:`~upstage_des.events.FilterGet`: A get with a filter function

#. :py:class:`~upstage_des.events.Put`: Put something into a store or container

#. :py:class:`~upstage_des.events.ResourceHold`: Put and release holds on limited resources

#. :py:class:`~upstage_des.events.Wait`: A standard SimPy timeout


------------------------------------
Define a TaskNetwork for the Cashier
------------------------------------

The flow of Tasks is controlled by a TaskNetwork, and the setting of the queue within
tasks. A Task Network is defined by the nodes and the links:

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

The task classes are given names, and those strings are used to define the default and
allowable task ordering. The task ordering need to know the default task (can be None)
and the allowed tasks. Allowed tasks must be supplied. If no default is given, an error
will be thrown if no task ordering is given when a new task is selected. If the default
or the set task queue violates the allowed rule, an error will be thrown.

The task network forms the backbone of flexible behavior definitions, while a ``DecisionTask``
helps control the path through the network.

The ``cashier_task_network`` is a factory that creates network instances from the definition
that actors can use (one per actor/per network).

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

The :py:class:`~upstage_des.task_network.TaskNetworkFactory` class has some convience methods
for creating factories from typical use cases:

#. :py:meth:`~upstage_des.task_network.TaskNetworkFactory.from_single_looping`: From a single
   task, make a network that loops itself.

   * Useful for a Singleton task that, for example, receives communications and farms them out
     or manages other task networks.

#. :py:meth:`~upstage_des.task_network.TaskNetworkFactory.from_single_terminating`: A network
   that does one task, then freezes for the rest of the simulation.

#. :py:meth:`~upstage_des.task_network.TaskNetworkFactory.from_ordered_looping`: A series of
   tasks with no branching that loops.

#. :py:meth:`~upstage_des.task_network.TaskNetworkFactory.from_single_looping`: A series of tasks
   with no branching that terminates at the end.

--------------------
Setting up Customers
--------------------

To complete the simulation, we need to make customers arrive at the checkout lanes. This can
be done using a standard SimPy process:

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

    print(cashier._state_histories["items_scanned"])
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


Your run may be different, due to the calls to ``stage.random`` (a passthrough for ``random.Random()``).
See :doc:`Random Numbers </user_guide/how_tos/random_numbers>` for more.

Notice how lane 1 takes customers right away, but lane 2 stacks up. Also notice how the
``SelfMonitoringStore`` creates the ``._quantities`` datatype that shows the time history of number of 
items in the store. If it was a Container, instead of a Store, it would record the level.

.. [#f1] You can run this now and ignore the warning about an environment.
.. [#f2] This is not strictly true, it does yield a zero time timeout under the hood.
