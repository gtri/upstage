=================
Dictionary States
=================

Dictionary states are a particular :doc:`State <states>` that acts like
a standard python dictionary. There is a use case for defining at runtime
the names and values of Actor states, but this is not supported through
the class definition syntax. The :py:class:`~upstage_des.states.DictionaryState`
solves this problem by allowing a runtime ingest of a dictionary of arbitrary
keys and values. 

This state type also allows recording of dictionary entries on the state, while
most other states cannot record on internal changes to a state. See
:ref:`Complex States <complex_states>` for more information about that issue.

A dictionary state is created in the same way as other states, and works with
:doc:`data recording </tutorials/data>`. Note that the data recording functions
will be given the entire dictionary for the state, not just the single entry
being recorded.

.. code-block:: python

    import upstage_des.api as UP

    def total_recorder(time: float, value: dict[str, int]) -> int:
        return sum(value.values())

    class Usher(UP.Actor):
        people_seen = UP.DictionaryState[int](
            recording=True,
            recording_functions=[(total_recorder, "total_customers")],
        )

    class TicketTaking(UP.Task):
        def task(self, *, actor: Usher):
            for customer in ["adult", "adult", "child", "adult", "child"]:
                actor.people_seen[customer] += 1
                yield UP.Wait(0.1)

Then it can be instantiated and run:

.. code-block:: python

    with UP.EnvironmentContext() as env:
        ush = User(name="Ticketeer", people_seen={"adult": 0, "child": 0})
        TicketTaking().run(actor=ush)
        env.run()
        print(env.now)
        >>> 0.5
        print(ush._state_histories)
        >>> {
        >>> 'people_seen.adult': [(0.0, 0), (0.0, 1), (0.1, 2), (0.3, 3)],
        >>> 'total_customers': [(0.0, 0), (0.0, 1), (0.1, 2), (0.2, 3), (0.3, 4), (0.4, 5)],
        >>> 'people_seen.child': [(0.0, 0), (0.2, 1), (0.4, 2)]
        >>> }


Dictionary states allow you to add more entries to the dictionary explicitly,
but they will behave like regular dictionaries in that unseen keys will cause
errors. You can mitigate this in the usual way:

.. code-block:: python

    class TicketTaking(UP.Task):
        def task(self, *, actor: Usher):
            for customer in ["adult", "adult", "child", "adult", "child", "vip"]:
                curr = actor.people_seen.setdefault(customer, 0)
                actor.people_seen[customer] += 1
                yield UP.Wait(0.1)

When you create a data table from the sim, the results come out naturally with
the pattern of ``<state_name>.<key>`` and the value you assigned. If you used
complicated objects as values in the dictionary, those will be processed as they
would be in any other circumstance. Note that the following example would fail
a ``mypy`` check since it can't interpret ``data["other"]``.

.. code-block:: python

    from upstage_des.data_utils import create_table

    class Usher(UP.Actor):
        data = UP.DictionaryState[dict](recording=True)
        tracker = UP.DictionaryState[int](recording=True)

    with UP.EnvironmentContext():
        ush = Usher(name="Ticketeer", data={"group": {}, "other": 3}, tracker={"value": 1})
        ush.data["group"]["this_key"] = 1
        ush.data["other"] += 1
        ush.data["group"]["new_key"] = {"another": "dictionary"}
        ush.tracker["value"] += 1

        rows, cols = create_table()
        print(rows)
        >>> ('Ticketeer', 'Usher', 'data.group.this_key', 0.0, 1, None)
        >>> ('Ticketeer', 'Usher', 'data.group.new_key',  0.0, {'another': 'dictionary'}, None)
        >>> ('Ticketeer', 'Usher', 'data.other',          0.0, 3, None)
        >>> ('Ticketeer', 'Usher', 'data.other',          0.0, 4, None)
        >>> ('Ticketeer', 'Usher', 'tracker.value',       0.0, 1, None)
        >>> ('Ticketeer', 'Usher', 'tracker.value',       0.0, 2, None)

The ``create_table()`` function will also recognize the ``DictionaryState`` if it
``save_static=True`` and output any non-recorded values in the same format.

Compared to ``Dataclass`` and ``Dict``
######################################

It's possible to use ``dataclass`` and ``dict`` objects as states in a plain
``UP.State[dict](recording=True)`` call and get data recording. The downside
is that you must call ``record_state(state_name)`` after updating the state
to record, which is easy to forget to do. Especially if you told the Actor
that the state was recording but you aren't getting out a recording.

The downside of ``dataclass`` is that it's not readily runtime defineable (it
is via ``dataclasses.make_dataclass()``) nor updateable once it's made. The upside
is that a dataclass has known types if you don't define it dynamically. 

The ``DictionaryState`` is meant to be a middle ground to mitigate those downsides
when desired. In the future it may also form the base class for other states that
may have similar key/value access features..

Type Hinting
############

Dictionary states, if untyped, allow for any kind of input/output. If you define
``valid_types`` the state will check that any input to a dictionary value
matches one of those types. The dictionary state does not do per-key typing. This
means you will need to check if the type is something you expect, or stick to
single typed dictionaries.

As usual, make sure the type hint for the state matched valid_types so that your
static type checker and the internal state type checking match.

.. code-block:: python

    import upstage_des.api as UP

    class Usher(UP.Actor):
        people_seen = UP.DictionaryState[int | float](valid_types=(int, float))

    with UP.EnvironmentContext():
        ush = User(name="Ticketeer", people_seen={"Customer": 1.0})
        ush.people_seen["boss"] = 1
        # This will error
        ush.people_seen["boss"] = "Boss' Name"
