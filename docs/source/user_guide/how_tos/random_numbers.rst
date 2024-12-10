==============
Random Numbers
==============

Random numbers are not supplied by UPSTAGE, you are responsible for rolling dice on your own.

However, UPSTAGE does use them in one area, which is in :py:class:`~upstage_des.events.Wait`, in the :py:meth:`~upstage_des.events.Wait.from_random_uniform` method.

The built-in python ``random`` module is used by default, and you can find it on ``stage.random``. It can be instantiated in a few ways:

.. code-block:: python

    from random import Random
    from upstage_des.api import UpstageBase, EnvironmentContext

    base = UpstageBase()

    with EnvironmentContext(random_seed=1234986):
        num = base.stage.random.uniform(1, 3)
        print(num)
        >>> 2.348057489610457

    rng = Random(1234986)
    with EnvironmentContext(random_gen=rng):
        num = base.stage.random.uniform(1, 3)
        print(num)
        >>> 2.348057489610457

    with EnvironmentContext():
        num = base.stage.random.uniform(1, 3)
        print(num)
        >>> 2.348057489610457

If you want to use your own random number generator, just supply it to the ``random_gen`` input, or as its own variable with ``UP.add_stage_variable``.

If you supply it as ``random_gen``, ensure that it has a ``uniform`` method so that the Wait event can use it.
