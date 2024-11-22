===============
Stage Variables
===============

The ``stage`` is an UPSTAGE feature to allow thread-safe "global" variables accessible by any Actor or Task.

To add variables to the stage, within the :py:class:`~upstage.base.EnvironmentContext` manager use the :py:func:`~upstage.base.add_stage_variable` function.

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
===========================

Some variables are expected to exist on the stage for some features. These are found in the :py:class:`~upstage.base.StageProtocol` protocol,
and are listed below:

* "altitude_units": A string of "ft", "m", or other distance unit. See :py:func:`~upstage.units.convert.unit_convert` for a list.
* "distance_units": A string of distance units
* "stage_model": A model to use for Geodetic calculations. See :doc:`geography` for more.
* "intersection_model": A model to use for motion manager. See :doc:`geography` and :doc:`motion_manager` for more.
* "time_unit": Units of time. See :py:func:`~upstage.units.convert.unit_convert` for a list.

If they are not set and you use a feature that needs them, you'll get a warning about not being able to find a stage variable.


Accessing Stage through UpstageBase
===================================

The :py:class:`~upstage.base.UpstageBase` class can be inherited to provide access to ``self.env`` and ``self.stage`` in any object, not just 
actors and tasks. The following snippets shows how you might use it for pure SimPy capabilities.

.. code-block:: python

    class ManagerCode(UP.UpstageBase):
        def run(self):
            def _proc():
                process_time = self.stage.process_time
                yield self.env.timeout(process_time)
            
            self.env.process(_proc())


Accessing Stage through upstage.api
===================================

For convenience, you can also do the following:

.. code-block:: python

    import upstage.api as UP

    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("altitude_units", "centimeters")

        stage = UP.get_stage()
        assert stage.altitude_units == "centimeters"
        altitude_units = UP.get_stage_variable("altitude_units")
        assert altitude_units == "centimeters"
