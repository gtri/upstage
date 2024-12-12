===============
Stage Variables
===============

The ``stage`` is an UPSTAGE feature to allow thread-safe "global" variables accessible by any Actor or Task.

To add variables to the stage, within the :py:class:`~upstage_des.base.EnvironmentContext` manager use the :py:func:`~upstage_des.base.add_stage_variable` function.

Once you set a stage variable, it cannot be changed. This is intentional, as the stage is meant to be static. Anything that changes should go through
SimPy or UPSTAGE tasks, states, or processes. 

.. code-block:: python

    class Person(UP.Actor):
        
        def do_thinking(self):
            number = self.stage.my_variable
            print(f"'{self}'' is thinking about {number}")


    class Think(UP.Task):
        def task(self, *, actor: Person):
            number = self.stage.my_variable
            print(f"Think Task is thinking about {number}")
            actor.do_thinking()
            yield UP.Event()


    with UP.EnvironmentContext(initial_time=0.0) as env:
        UP.add_stage_variable("my_variable", 3.14)
        p = Person(name="Arthur")
        Think().run(actor=p)
        env.run()

    >>> Think Task is thinking about 3.14
    >>> 'Person: Arthur' is thinking about 3.14


Expected Stage Variables
=========================

Some variables are expected to exist on the stage for some features. These are found in the :py:class:`~upstage_des.base.StageProtocol` protocol,
and are listed below:

* "altitude_units": A string of "ft", "m", or other distance unit. See :py:func:`~upstage_des.units.convert.unit_convert` for a list.
* "distance_units": A string of distance units
* "stage_model": A model to use for Geodetic calculations. See :doc:`geography` for more.
* "intersection_model": A model to use for motion manager. See :doc:`geography` and :doc:`motion_manager` for more.
* "time_unit": Units of time. See :py:func:`~upstage_des.units.convert.unit_convert` for a list.
* "daily_time_count": For non-standard time values, such as "ticks", this number is used to create logging outputs with "Days".

If they are not set and you use a feature that needs them, you'll get a warning about not being able to find a stage variable.

For more information about time units, see :doc:`times`.


Accessing Stage through UpstageBase
===================================

The :py:class:`~upstage_des.base.UpstageBase` class can be inherited to provide access to ``self.env`` and ``self.stage`` in any object, not just 
actors and tasks. The following snippets shows how you might use it for pure SimPy capabilities.

.. code-block:: python

    class ManagerCode(UP.UpstageBase):
        def run(self):
            def _proc():
                process_time = self.stage.process_time
                yield self.env.timeout(process_time)
            
            self.env.process(_proc())


Accessing Stage through upstage_des.api
=======================================

For convenience, you can also do the following:

.. code-block:: python

    import upstage_des.api as UP

    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("altitude_units", "centimeters")

        stage = UP.get_stage()
        assert stage.altitude_units == "centimeters"
        altitude_units = UP.get_stage_variable("altitude_units")
        assert altitude_units == "centimeters"


Accessing Stage outside of the EnvironmentContext
=================================================

There are some times when you may want the Stage to exist outside of the EnvironmentContext. When doing plotting of
geographic entities, for example, having access to the ``stage_model`` is useful. This is also helpful when visualizing
or doing analysis in Jupyter Notebooks, where you don't want to sit inside a context manager.

For this situation, UPSTAGE provides a way to operate the context manager without needing to be inside the context.

.. code-block:: python

    import upstage_des.api as UP
    from upstage_des.base import create_top_context, clear_top_context

    ctx = create_top_context()
    add_stage_variable("example", 1.234)

    assert get_stage_variable("example") == 1.234

    clear_top_context(ctx)
    
The two functions are just wrappers around the context manager's ``__enter__`` and ``__exit__`` methods, but they provide a clearer
idea of what's being done and why.
