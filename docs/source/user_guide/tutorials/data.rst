========================================
Simulation Data Gathering and Processing
========================================

UPSTAGE has four features for data recording:

1. Use ``Actor.log()`` to log a string message at a given time.

   * Note that on Actor creation, ``debug_log=True`` must be given.

2. Use ``a_state = UP.State(recording=True)``.

   * Access the data with ``actor._state_histories["a_state"]``
   * The data will be in the form ``tuple[time, value]``
   * For :doc:`ActiveStates </user_guide/how_tos/active_states>`, the ``value`` may be
     a special ``Enum`` saying if the state is being activated, deactivated,
     or is active/inactive.

3. Use a ``SelfMonitoring<>`` Store or Container.

   * Access the data with ``a_store._quantities``
   * The data will be in the form ``tuple[time, value]``

4. Use the generic data recorder: ``record_data(data_object)``.

   * Access data with ``get_recorded_data()``.
   * The data will be in the form ``[(time, data), (time, data), ...]

UPSTAGE also has utility methods for pulling most of the available data into a
tabular format, along with providing column headers.


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

Nearly every state is recordable in UPSTAGE. The :py:class:`~upstage_des.states.ResourceState`
is an exception covered in the next section. To enable state recording, set ``recording=True``.
After running the sim, use the ``_state_histories`` attribute on the actor to get the data.

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

That returns a list of (time, value) tuples. This works for simple data types,
but not mutable types:

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

Complex States
--------------

The ``items`` value doesn't record, because the state doesn't see the ``cash.items = ...`` operation.
For objects like that, you can use the ``record_state`` method on the ``Actor``:

.. code:: python

    from collections import Counter

    class Cashier(UP.Actor):
        items = UP.State[Counter[str, int]](default_factory=Counter, recording=True)

    with UP.EnvironmentContext() as env:
        cash = Cashier(name="Ertha")
        cash.items["bread"] = 1
        cash.record_state("items")
        # or, cash.items = cash.items
        env.run(until=0.75)
        cash.items["bread"] += 2
        cash.items["milk"] += 3
        cash.record_state("items")

        print(cash._state_histories)
        >>>{'items': [(0.0, Counter({'bread': 1})), (0.75, Counter({'bread': 3, 'milk': 3}))]}

Note also that UPSTAGE deep-copies the value in the state history, so any data should be compatible with that
operation.

UPSTAGE will output data from ``dataclass`` states, and ``dict[str, Any]`` states by creating rows in the
data table with the naming convention ``state_name.attribute_name``, where the attribute is either a dataclass
attribute or a key from the dictionary.

Geographic Types
----------------

State recording of the built-in geographic states (cartesian and geodetic) is compatible
with the data objects. This for both the active state versions and the typical ``UP.State[CartesianLocation]()``
ways of creating the state.

It's recommended, since UPSTAGE does not store much data about the motion of geographic states, to poll or ensure you
get the state value whenever you want to know where it is. While activating and deactivating will record the value,
if an actor is moving along waypoints, each waypoint doesn't record itself unless asked.

Active State Recording
======================

Active states record in the same way, but extra information is given to tell the user if the state
was activated or not and if it was switching to/from active or inactive.

The state history will still be ``(time, value)`` pairs, but on activation and deactivation an ``Enum``
value is placed in the history to indicated which has taken place. The state value isn't recorded in
that row of the history because it will have been calculated immediately prior and recorded.

.. code:: python

    class Cashier(UP.Actor):
        time_worked = UP.LinearChangingState(default=0.0, recording=True)

    with UP.EnvironmentContext() as env:
        cash = Cashier(name="Ertha")

        cash.activate_linear_state(
            state="time_worked",
            rate=1.0,
            task=None, # this is fine to do outside of a task.
        )

        env.run(until=1)
        cash.time_worked
        env.run(until=3)
        cash.time_worked
        cash.deactivate_state(state="time_worked", task=None)
        env.run(until=4)
        cash.time_worked = 5.0

        print(cash._state_histories["time_worked"])
        >>> [
            (0.0, 0.0),
            (0.0, <ActiveStatus.activating: 'ACTIVATING'>),
            (1.0, 1.0),
            (3.0, 3.0),
            (3.0, <ActiveStatus.deactivating: 'DEACTIVATING'>),
            (4.0, 5.0),
        ]

The built-in data gathering will account for this for you, but if you are manually processing
the active state histories, the (de)activation signal in the history should always come
after a recording at the same time value.

Remember that if you never ask for the value of ``time_worked``, it will only report it on
activation and deactivation.

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


General Data Recording
======================

General data recording is for data that may not conveniently work with states or monitored
stores. UPSTAGE provides a simple interface for storing general information:

.. code-block:: python

    from upstage_des.data_utils import record_data

    with UP.EnvironmentContext() as env:
        ...
        record_data("The cashier made a funny joke")
        ...
        record_data({"received": ["fruit", "eggs"], "shipping method": "car"})
        ...

The optional parameter ``copy`` can be set to ``True`` to attempt a deep copy of the
object to record a snapshot of a mutable type that may change.        

Data Gathering
==============

There are three functions for gathering data from UPSTAGE:

1. :py:func:`upstage_des.data_utils.data_utils.create_table`
   
   * Finds all actors and their recording states
   * Finds all ``SelfMonitoring<>`` resources that are not attached
     to actors.
   * Ignores location states by default
   * Reports actor name, actor type, state name, state value, and
     if the state has an active status.
   * If ``skip_locations`` is set to ``False``, then location objects
     will go into the state value column.
   * If ``save_static`` is set to ``True``, then non-recording states
     will have their last value recorded in the table with an ``Activation Status``
     column value of ``"Last Seen"``.
   * Data are in long-form, meaning rows may share a timestamp.

2. :py:func:`upstage_des.data_utils.data_utils.create_location_table`
  
   * Finds all location states on Actors
   * Reports location data as individual columns for the dimensions
     of the location (XYZ or LLA).
   * Reports on active/inactive state data.
   * Data are not completely in long-form. XYZ are on a single row, but
     rows can have the same timestamp if they are different states.

3. :py:func:`upstage_des.data_utils.data_recorder.get_recorded_data`

   * Returns the list of tuples of time and data that was recorded.
   * No other features, it is up to the user to pick what they want
     and how they want to process it.

Using the example in :doc:`Data Gathering Example </user_guide/tutorials/data_creation_example>`, the
following table (a partial amount shown) would be obtained from the ``create_table`` function:

.. table::

    +-----------+-------------------------+-------------+----+-----+-----------------+
    |Entity Name|       Entity Type       | State Name  |Time|Value|Activation Status|
    +===========+=========================+=============+====+=====+=================+
    |Ertha      |Cashier                  |items_scanned|   0|  0.0|                 |
    +-----------+-------------------------+-------------+----+-----+-----------------+
    |Ertha      |Cashier                  |items_scanned|   3| -1.0|                 |
    +-----------+-------------------------+-------------+----+-----+-----------------+
    |Ertha      |Cashier                  |cue          |   3|  1.0|                 |
    +-----------+-------------------------+-------------+----+-----+-----------------+
    |Ertha      |Cashier                  |cue2         |   3| 11.0|                 |
    +-----------+-------------------------+-------------+----+-----+-----------------+
    |Ertha      |Cashier                  |time_working |   3|  2.9|active           |
    +-----------+-------------------------+-------------+----+-----+-----------------+
    |Ertha      |Cashier                  |other        |   0|  3.0|Last Seen        |
    +-----------+-------------------------+-------------+----+-----+-----------------+
    |Bertha     |Cashier                  |cue          |   0|  0.0|                 |
    +-----------+-------------------------+-------------+----+-----+-----------------+
    |Bertha     |Cashier                  |cue2         |   0|  0.0|                 |
    +-----------+-------------------------+-------------+----+-----+-----------------+
    |Bertha     |Cashier                  |time_working |   0|  0.0|inactive         |
    +-----------+-------------------------+-------------+----+-----+-----------------+    
    |Store Test |SelfMonitoringFilterStore|Resource     |   0|  0.0|                 |
    +-----------+-------------------------+-------------+----+-----+-----------------+

The location table will look like the following table. Now how the active states can be 
"activating", "active", or "deactivating". Not shown is the "inactive" value, which
is used for when an active state value is changed, but not because it has been set
to change automatically.

.. table::

    +------------+-----------+------------+----+-------+-------+-+-----------------+
    |Entity Name |Entity Type| State Name |Time|   X   |   Y   |Z|Activation Status|
    +============+===========+============+====+=======+=======+=+=================+
    |Wobbly Wheel|Cart       |location    |   0| 1.0000| 1.0000|0|activating       |
    +------------+-----------+------------+----+-------+-------+-+-----------------+
    |Wobbly Wheel|Cart       |location    |   1| 2.5364| 2.2803|0|active           |
    +------------+-----------+------------+----+-------+-------+-+-----------------+
    |Wobbly Wheel|Cart       |location    |   2| 4.0728| 3.5607|0|active           |
    +------------+-----------+------------+----+-------+-------+-+-----------------+
    |Wobbly Wheel|Cart       |location    |   3| 5.6093| 4.8411|0|deactivating     |
    +------------+-----------+------------+----+-------+-------+-+-----------------+
    |Wobbly Wheel|Cart       |location_two|   0| 1.0000| 1.0000|0|activating       |
    +------------+-----------+------------+----+-------+-------+-+-----------------+
    |Wobbly Wheel|Cart       |location_two|   1|-0.5051|-0.3170|0|active           |
    +------------+-----------+------------+----+-------+-------+-+-----------------+
    |Wobbly Wheel|Cart       |location_two|   3|-3.5154|-2.9510|0|deactivating     |
    +------------+-----------+------------+----+-------+-------+-+-----------------+

If you were to have ``pandas`` installed, a dataframe could be created with:

.. code:: python

    import pandas as pd
    import upstage_des.api as UP
    from upstage_des.data_utils import create_table

    with UP.EnvironmentContext() as env:
        ...
        env.run()
        
        table, header = create_table()
        df = pd.DataFrame(table, columns=header)

.. note::

    The table creation methods must be called within the context, but
    the resulting data does not need to stay in the context.

    The exception is that if a state has a value that uses the environment
    or the stage, you may see a warning if you try to access attributes or
    methods on that object.
