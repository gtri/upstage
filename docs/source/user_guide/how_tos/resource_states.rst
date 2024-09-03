===============
Resource States
===============
.. include:: ../../class_refs.txt

In the tutorial for the first simulation, there was this example of a resource state:

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

The obvious question is, why? The following works just fine:

.. code-block:: python

    import upstage.api as UP
    import simpy as SIM

    class CheckoutLane(UP.Actor):
        customer_queue = UP.State[SIM.Store]()


    with UP.EnvironmentContext() as env:
        queue_store = UP.SelfMonitoringStore(env, capacity=10)
        lane = CheckoutLane(
            name="FirstLane",
            customer_queue=queue_store,
        )

        def proc():
            yield lane.customer_queue.put("thing")

        env.process(proc())
        env.run()
        print(lane.customer_queue.items)
    >>> ["thing"]


There are several reasons for doing this:

1. To make cloning an Actor for rehearsal more aware and intelligent about stores and containers as states
2. Simplifies actor instantiation. Instead of having to build a store on your own for each actor, the states accept simpler data types and handle the environment for you.
3. Better default behavior instead of needing a partial or a lambda function in the factory.
4. Default expectations, such as being frozen.
5. |State| does not understanding recording of entries or counts in stores or containers.


In practice, the second and last reasons are the most compelling in our experience.

-----------------------
Instantiation Arguments
-----------------------

The input an Actor needs to receive for a ResourceState is a dictionary of:

* 'kind': The class of the store or container, which is optional if you provided a default.
* 'capacity': A numeric capacity of the store or container.
* 'init': For containers only, an optional starting amount.
* key:value pairs for any other input expected as a keyword argument by the store or container class.


If you want to pre-load a store with items, it's recommended to run a process to yield them. That way you get all the 
recording you want, if you have it enabled.

The alternative is to do the trick of ``the_actor.some_store.items.extend(list_of_your_items)``, but that won't get the recording
to work. You could, in a pinch, run ``the_actor.some_store._record("hand-record")``.
