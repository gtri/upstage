===================
Environment Context
===================

UPSTAGE uses Python's [context variable](https://docs.python.org/3/library/contextvars.html)
capabilities to safely manage "global" state information while not polluting the module
level data with run-specific information.

The context manager accepts three arguments:

1. Simulation start time (passes through to ``simpy.Environment``)
2. A random seed for ``random.Random``
3. A random number generator object, if different than ``random.Random``

For more about the random numbers, see :doc:`Random Numbers </user_guide/how_tos/random_numbers>`.

.. note::

    If you get a warning or error about not finding an environment, you have likely
    tried to instantiate an actor, task, or other UPSTAGE object outside of an
    environment context.


Creating Contexts
=================

Use the ``EnvironmentContext`` context manager:

.. code:: python

    impoprt upstage_des.api as UP

    with UP.EnvironmentContext() as env:
        ...
        # everything in here can find that environment
        ...
        env.run()

Or, create a context at the current scope:

.. code:: python

    from upstage_des.base import create_top_context, clear_top_context

    ctx = create_top_context()
    env = ctx.env_ctx.get()
    ...
    env.run()

    clear_top_context(ctx)

This way is friendlier to Jupyter notebooks, where you might run a simulation and want to
explore the data without needing to remain in the context manager.
