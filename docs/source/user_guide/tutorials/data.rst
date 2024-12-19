===============
Simulation Data
===============

UPSTAGE has three features for data recording:

1. Use `Actor.log()` to log a string message at a given time.

   * Note that on Actor creation, ``debug_log=True`` must be given.

2. Use ``a_state = UP.State(recording=True)``.

   * Access the data with ``actor._state_histories["a_state"]``

3. Use a ``SelfMonitoring<>`` Store or Container.

   * Access the data with ``a_store._quantities``

Each feature has a list of tuples of (time, value) pairs.

Actor Logging
=============

The actor debug logging records data about the flow of the actor through its task networks. It's designed
for debugging and seeing how your actors are behaving, but it can be a place to add additional data if 
you want to look it up later. 

.. code:: python

    with UP.EnvironmentContext():
        cashier = Cashier(
            name="Bob",
            debug_log=True,
        )
        # Log with an argument logs a message
        cashier.log("A message")
        # Log without an argument returns the log
        print(cashier.log())
        >>> [(0.0, '[Day    0 - 00:00:00] A message')]

The logging comes a list of tuples. The first entry is the time as a float - useful for filtering. The second
entry is a string of the message along with a formatted time. The time is based on :doc:`Time Units </user_guide/how_tos/times>`.

If you set the stage variable ``debug_log_time`` to ``False`` (it behaves as ``True`` by default), then the actor will
not log the time, and only put the message as the second entry. This message is typed to be a string, but since this
is python, if you aren't running a static type checker on your own code, you can put anything you like there.
If ``debug_log_time`` is ``True``, UPSTAGE will attempt to format it as a string, so make sure it's set to ``False``.

On a per-actor level, you can set ``debug_log_time`` as well, and that value will take priority over the stage value.

.. code:: python

    with UP.EnvironmentContext():
        cashier = Cashier(
            name="Bob",
            debug_log=True,
            debug_log_time=False,
        )
        cashier.log("A message")
        print(cashier.log())
        >>> [(0.0, 'A message')]

        cashier2 = Cashier(
            name="Betty",
            debug_log=True,
        )
        UP.set_stage_variable("debug_log_time", False)
        cashier2.log({'data': 1})
        print(cashier2.log())
        >>> [(0.0, {'data': 1})]


State Recording
===============

Nearly every state is recordable in UPSTAGE. The :py:class:`~upstage_des.states.ResourceState` is an exception covered
in the next section. To enable state recording, set ``recording=True``. After running the sim, use the ``_state_histories``
attribute on the actor to get the data.

.. code:: python

    class Cashier(UP.Actor):
        items_scanned = UP.State[int](recording=True)

    with UP.EnvironmentContext() as env:
        cash = Cashier(name="Ertha", items_scanned=0)
        cash.items_scanned += 1
        env.run(until=1)
        cash.items_scanned += 2
        env.run(until=2)
        cash.items_scanned += 1
        env.run(until=3)
        cash.items_scanned = -1

        print(cash._state_histories["items_scanned"])
        >>> [(0.0, 0), (0.0, 1), (1.0, 3), (2.0, 4), (3.0, -1)]

That returns a list of (time, value) tuples. This works for simple data types, but not mutable types:

.. code:: python

    from collections import Counter

    class Cashier(UP.Actor):
        people_seen = UP.State[str](default="", recording=True)
        items = UP.State[Counter[str, int]](default_factory=Counter, recording=True)

    with UP.EnvironmentContext() as env:
        cash = Cashier(name="Ertha")
        cash.people_seen = "James"
        cash.items["bread"] = 1
        env.run(until=0.75)
        cash.people_seen = "Janet"
        cash.items["bread"] += 2

        print(cash._state_histories)
        >>>{'people_seen': [(0.0, 'James'), (0.75, 'Janet')]}

Note that the string State of ``people_seen`` acts as a way to record data, even if we don't care in
the moment the name of the last scanned person. This lets states behave as carriers of current or past
information, depending on your needs.

The ``items`` value doesn't record, because the state doesn't see ``cash.items = ...``. For objects like that,
you should:

.. code:: python

    from collections import Counter

    class Cashier(UP.Actor):
        items = UP.State[Counter[str, int]](default_factory=Counter, recording=True)

    with UP.EnvironmentContext() as env:
        cash = Cashier(name="Ertha")
        cash.items["bread"] = 1
        cash.items = cash.items # <- Tell the state it's been changed explicitly
        env.run(until=0.75)
        cash.items["bread"] += 2
        cash.items["milk"] += 3
        cash.items = cash.items

        print(cash._state_histories)
        >>>{'items': [(0.0, Counter({'bread': 1})), (0.75, Counter({'bread': 3, 'milk': 3}))]}

This is clunky, but the ``Counter`` object has no way of knowing it belongs in a ``State`` to get the
recording to work. In the future, UPSTAGE may monkey-patch objects with ``__set__`` methods, but for
now this is the workaround.

Note also that UPSTAGE deep-copies the value in the state history, so any data should be compatible with that
operation.

Geographic Types
----------------

State recording of the built-in geographic states (cartesian and geodetic) is compatible
with the data objects. This for both the active state versions and the typical ``UP.State[CartesianLocation]()``
ways of creating the state.

Resource Recording
==================

If you have a state that is a simpy resource, UPSTAGE won't know how to record that state. For the reasons
discussed above, there's no way to link the changes in the referenced value of the state to the recording
mechanism. Even if there was, there's not an implicit understanding of the nature of the resource.

UPSTAGE comes with resource types, based on the SimPy types, that automatically record:

1. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringStore`  
2. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringFilterStore`
3. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringContainer`
4. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringContinuousContainer`
5. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringSortedFilterStore`
6. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringReserveContainer`

Each resource understands the kind of data it can hold, and records it appropriately. Containers are simpler,
and just record the level that they are at.

The ``SelfMonitoring<>Store`` resources accept an optional ``item_func`` argument, the result of which is put into
the recorded data. By default, the number of items in the store is used.

The following example shows how to use a monitoring store and get data back from it. The ``_quantities`` attribute
on the state is used to hold the data.

.. code:: python

    class CheckoutLane(UP.Actor):
        belt = UP.ResourceState(default=UP.SelfMonitoringStore)
    
    with UP.EnvironmentContext() as env:
        check = CheckoutLane(name="Lane 1: 10 Items or Fewer")

        # Mix simpy with UPSTAGE for simple processes
        def _proc():
            yield check.belt.put("Bread") # simpy event
            yield env.timeout(1.0)
            yield UP.Put(check.belt, "Milk").as_event() # UPSTAGE event as simpy
            yield UP.Put(check.belt, "Pizza").as_event()

        env.process(_proc())
        env.run()
        print(check.belt._quantities)
        >>> [(0.0, 0), (0.0, 1), (1.0, 2), (1.0, 3)]

Here's how to set your own item function, omitting the middle portion which stays the same:

.. code:: python
    
    from collections import Counter

    class CheckoutLane(UP.Actor):
        belt = UP.ResourceState(
            default=UP.SelfMonitoringStore,
            default_kwargs={"item_func":lambda x: Counter(x)},
        )

    ...

        print(check.belt._quantities)
        >>> [
            (0.0, Counter()),
            (0.0, Counter({'Bread': 1})), 
            (1.0, Counter({'Bread': 1, 'Milk': 1})),
            (1.0, Counter({'Bread': 1, 'Milk': 1, 'Pizza': 1}))
        ]

Or use the actor init to pass the item function:

.. code:: python

    check = CheckoutLane(
        name = "Lane 2",
        belt = {"item_func":lambda x: Counter(x)},
    )
