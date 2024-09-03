======
Events
======

UPSTAGE Events mimic the SimPy events, and provide features that enable interrupts, rehearsal and other features with Task Networks.

All events accept a ``rehearsal_time_to_complete`` argument.

The available UPSTAGE events are:

:py:class:`~upstage.events.Event`
---------------------------------

Mimics SimPy's raw ``Event``, useful for marking pauses until a success.

See :py:meth:`~upstage.actor.Actor.create_knowledge_event` for a use case.

One use case is the knowledge event, which enables a way to publish and event to an actor, and have some other source ``succeed`` it.

.. code-block:: python

    class ActorTask(UP.Task):
        def task(self, *, actor):
            event = actor.create_knowledge_event(name="pause")
            yield event


    class ManagerTask(UP.Task):
        def task(self, *, actor):
            subordinate: UP.Actor = actor.subordinates[0]
            subordinate.succeed_knowledge_event(name="pause", some_data={...})


:py:class:`~upstage.events.Wait`
--------------------------------
A standard SimPy timeout. Can be explicit or generate from a random uniform distribution.

The random uniform distribution accepts an input for the rehearsal time, while the base version rehearses at the given time.

.. code-block:: python

    yield UP.Wait(3.14)
    ...
    yield UP.Wait.from_random_uniform(low, high, rehearsal_time_to_complete=high)


:py:class:`~upstage.events.Get`
-------------------------------
Get from a store or container.

.. code-block:: python

    get_event = UP.Get(some_store)
    item = yield get_event
    assert item == get_event.get_value()

    amount = 12.3
    get_event = UP.Get(some_container, amount)
    yield get_event
    assert get_event.get_value() == amount


:py:class:`~upstage.events.FilterGet`
-------------------------------------
A get with a filter function, used for SimPy's ``FilterStore``.

.. code-block:: python

    get_event = UP.FilterGet(some_store, filter=lambda item: item.value > 10)
    item = yield get_event


:py:class:`~upstage.resources.sorted.SortedFilterGet`
-----------------------------------------------------
A get with a filter or sorting function, used with :py:class:`~upstage.resources.sorted.SortedFilterStore`, and others.

.. code-block:: python

    get_event = UP.SortedFilterGet(
        some_store,
        filter=lambda item: item.value > 10,
        sorter=lambda item: (item.property, item.other_property),
    )
    item = yield get_event


:py:class:`~upstage.events.Put`
-------------------------------
Put something into a store or container

.. code-block:: python

    item = [1,2,3.4]
    put_event = UP.Put(some_store, item)
    yield put_event
    assert item in some_store.items

    amount = 12.3
    yield UP.Put(some_store, amount)


:py:class:`~upstage.events.ResourceHold`
----------------------------------------
Put and release holds on limited resources.

.. code-block:: python

    a_resource = SIM.Resource(env, capacity=1)
    request_object = UP.ResourceHold(a_resource)
    yield request_object
    # Now you have a hold on the resource
    ...
    yield request_object
    # Now you've given it back


:py:class:`~upstage.events.All`
-------------------------------
Succeed when all passed events succeed.

.. code-block:: python

    get_event = UP.Get(some_store)
    wait_event = UP.Wait(3.14)
    yield Any(get_event, wait_event)

    assert get_event.is_complete()
    assert wait_event.is_complete()


:py:class:`~upstage.events.Any`
-------------------------------
Succeed when any passed events succeed

.. code-block:: python

    get_event = UP.Get(some_store)
    wait_event = UP.Wait(3.14)
    yield Any(get_event, wait_event)

    # Determine what passed
    if get_event.is_complete():
        item = get_event.get_value()
    else:
        # cancel the get or else it will succeed
        get_event.cancel()
