================
Key/Value States
================

Key/Value states are a particular :doc:`State <states>` that acts like
a standard python dictionary or dataclass.

There is a use case for defining at runtime the names and values of Actor states,
but this is not supported through the class definition syntax. The
:py:class:`~upstage_des.states.DictionaryState` solves this problem by allowing
a runtime ingest of a dictionary of arbitrary keys and values. The other state,
:py:class:`~upstage_des.states.DataclassState` lets you supply a dataclass type
to the state.

These state types allow recording of entries or attributes of the state, while
most other states cannot record on internal changes. See
:ref:`Complex States <complex_states>` for more information about that issue.

In the case of a dictionary, you can type hint the values (the keys must be
strings). The dataclass types will also be known, and both will be checked
during runtime whenever you set an attribute or entry.

.. note::

    These states record data as ``statename.attribute``, but do not go
    deeper into sub-attributes when recording. They work best when the
    values are not themselves key/value-like objects.

To summarize, the main reasons for using these states are:

1. Type checking attributes or values during runtime
3. Direct recording of attributes on a per-attribute basis
4. Runtime creation of recordable states

DictionaryState
###############

A dictionary state is created in the same way as other states, and works with
:doc:`data recording </user_guide/tutorials/data>`. Note that the data recording functions
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

DataclassState
##############

A dataclass state is created in the same way as other states, and works with
:doc:`data recording </user_guide/tutorials/data>`. Note that the data recording functions
will be given the entire dataclass for the state, not just the single attribute
being updated.

The following example shows how to use, type hint, and examine a dataclass state.

.. code-block:: python

    from dataclasses import dataclass, fields
    import upstage_des.api as UP
    from upstage_des.type_help import TASK_GEN

    @dataclass
    class TestDC:
        a: int
        b: float

    def recorder(time: float, value: TestDC) -> float:
        return value.a + value.b

    class ExampleActor(UP.Actor):
        dc_state = UP.DataclassState[TestDC](
            valid_types=TestDC,
            recording=True,
            recording_functions=[(recorder, "total_of_data")],
        )

    class SomeTask(UP.Task):
        def task(self, *, actor: ExampleActor) -> TASK_GEN:
            actor.dc_state.a += 1
            actor.dc_state.b += 4
            yield UP.Wait(0.1)
            actor.dc_state.b += 4
            yield UP.Wait(0.1)
            actor.dc_state.a -= 3

    with UP.EnvironmentContext() as env:
        ea = ExampleActor(name="Exam", dc_state=TestDC(0, 0.0))
        task = SomeTask()
        task.run(actor=ea)
        env.run()
        # fields() works:
        fs = fields(ea.dc_state)
        assert [f.name for f in fs] == ["a", "b"]

        # This will error
        ea.dc_state.a = "cause error"

        # let's check histories
        assert len(ea._state_histories) == 3
        assert ea._state_histories["dc_state.a"] == [(0.0, 0), (0.0, 1), (0.2, -2)]
        assert ea._state_histories["dc_state.b"] == [(0.0, 0.0), (0.0, 4.0), (0.1, 8.0)]
        assert ea._state_histories["total_of_data"] == [
            (0.0, 0.0),
            (0.0, 1.0),
            (0.0, 5.0),
            (0.1, 9.0),
            (0.2, 6.0),
        ]

Type Hinting
############

Dictionary states, if untyped, allow for any kind of value. If you define
``valid_types`` the state will check that any input to a dictionary value
matches one of those types. The dictionary state does not do per-key typing. This
means you will need to check if the types vary in how they can be operated on.

.. warning::

    For stability, UPSTAGE assumes all ``DictionaryState`` dictionaries only 
    have strings for keys.

As usual, make sure the type hint for the state matches valid_types so that your
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

Dataclasses will also type check using the ``__annotations__`` information
from the dataclass object. For dataclasses, supply the class object to ``valid_types``
to enable that feature.

.. warning::

    The runtime type checking of these values does not recurse. Keeping the
    dictionary value types simple: ``valid_types = (int, str, dict)``, e.g.
    is 
