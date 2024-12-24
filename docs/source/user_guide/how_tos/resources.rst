==============
Resource Types
==============

UPSTAGE comes with new resource types in addition to the SimPy resources:

1. :py:class:`~upstage_des.resources.container.ContinuousContainer`
2. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringStore`
3. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringFilterStore`
4. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringContainer`
5. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringContinuousContainer`
6. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringSortedFilterStore`
7. :py:class:`~upstage_des.resources.monitoring.SelfMonitoringReserveContainer`
8. :py:class:`~upstage_des.resources.reserve.ReserveContainer`
9. :py:class:`~upstage_des.resources.sorted.SortedFilterStore`

The self-monitoring stores are discussed in :doc:`the simulation data section </user_guide/tutorials/data>`.
They enable recording of data within the store or container over time, with an optional input for a function to
evaluate when recording on the items in the stores.

ContinuousContainer
===================

This container accepts gets and puts that act continuously, requiring both a rate and time to get or pull at that rate:

.. code:: python

    tank = UP.ContinuousContainer(env, capacity=10, init=0)
    tank.put(rate=3.0, time=2.5)
    env.run(until=3.0)
    print(tank.level)
    >>> 7.5

The gets and puts can be done simultaneously, and the container will determine the current level when asked for it. The
container will also, by default, raise errors when it has reach capacity or when it is empty.

SortedFilterStore
=================

This store behaves similar to the SimPy ``FilterStore``, except that it also accepts a function that prioritizes the
items in the store.

.. code:: python

    with UP.EnvironmentContext() as env:
        shelf = UP.SortedFilterStore(env)
        # pre-load items
        shelf.items.extend([(1, "a"), (2, "b"), (1, "b"), (1, "B")])

        def _proc() -> tuple[float, str]:
            ans = yield shelf.get(
                filter=lambda x: x[1] == x[1].lower(),
                sorter=lambda x: (x[1], -x[0]),
                reverse=True,
            )
            return ans

        p = env.process(_proc())
        env.run()
        print(p.value)
        >>> (1, 'b')

In the above, we filter items to have lower-case letters. Then we sort by ascending alphabetical and
descending numerical. Note the use of ``reverse=True`` and the ``-x[0]`` to do this. That gives us the
tie-breaker between ``(1, "a")`` and ``(1, "b")`` that ignores ``(1, "B")``.

ReserveContainer
================

The reserve container is not a true Container, in that it doesn't hold on queues. It is used to hold first-come
reservations for something numeric. Those requests can be timed out, and then checked on later by the
requestor. This is useful if you want to reserve access to a limited resource, but don't want or need to
hold in a line to do so.

The public methods on the ``ReserveContainer`` are:

1. ``reserve(requestor, quantity, expiration=None)``: Hold an amount
2. ``cancel_request(requestor)``: Cancel a hold
3. ``take(requestor)``: Get the amount held - or fail if request expired
4. ``put(amount, capacity_increase=False)``: Put something in the container, optionally increasing capacity.

The workflow with this resource is to resever, take, then put back when done - if the resource represented isn't
consumable. 
