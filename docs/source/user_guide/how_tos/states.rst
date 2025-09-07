======
States
======

States are a core UPSTAGE feature that gives :py:meth:`~upstage_des.actor.Actor` classes their useful and
changeable data. There are advanced state features, such as :doc:`Active States <active_states>` and
:doc:`Resource States <resource_states>`.

The :py:class:`~upstage_des.states.State` class is a python
`descriptor <https://docs.python.org/3/howto/descriptor.html>`_. This provides hooks for getting and setting
values stored on the Actor instance under the name of the state while allowing configuration, data recording,
and other features.

Plain states are created as follows, with nearly all the arguments shown for the state creation:

.. code-block:: python

    import ustage_des.api as UP

    class Cashier(UP.Actor):
        friendliness = UP.State[float](
            valid_types=(float,),
            recording=True,
            default=1.0,
            frozen = False,
            record_duplicates = False,
            allow_none_default = False,
        )


Note the typing of the ``State``, which tells your IDE and ``mypy`` what to expect out.

State inputs:

1. ``valid_types``: Types that the state can take for runtime checks. This may be removed in the future.
2. ``recording``: If the state records every time its value changes.
3. ``default``: A default value to use for the state. This allows the actor to be instantiated without it.
4. ``frozen``: If ``True``, any attempt to set the state value throws an exception (default ``False``).
5. ``record_duplicates``: If recording, allow duplicates to be recorded (default ``False``).
6. ``allow_none_default``: If ``True``, the state can have no default value set and not throw the exception.
7. ``default_factory``: Not shown, but provide a function to create the default value. Useful for mutable defaults.

The ``allow_none_default`` input is useful if you won't have access to the information needed to set a state when
your Actor is instantiated. This is common when you need actors to have mutual references to each other, for example.

If you set a default and a default factory, UPSTAGE will raise an error to force you to pick one or the other.

Some states do not use all these parameters, so consult the specific documentation for more.

Particular States
#################

Specific state descriptions and other state features can be found on these pages:

1. :doc:`Active States <active_states>`
2. :doc:`Resource States <resource_states>`
3. :doc:`Dictionary and Dataclass States <keyvalue_states>`
4. :doc:`State Sharing <state_sharing>`
5. :doc:`Mimic States <mimic_states>`
