==========
Time Units
==========

At the base level, the UPSTAGE clock (the SimPy clock, really) only cares about the number, and does not care
about units. This is not people-friendly, especially for debug logging or inputting times in some cases.

UPSTAGE has a few features for dealing with units of time.

The stage variable ``time_unit`` defines what each increment of the clock means. If you don't set it, UPSTAGE assumes
you mean "hours". When you call for ``pretty_now`` from anything inheriting :py:class:`~upstage_des.base.UpstageBase`,
you will get a timestamp string like: "Day   3 - 13:06:21". The actor debug logging uses that method on every log action.

If you give a time that isn't standard, such as "clock ticks", you'll get back something like "123.000 clock ticks" if the
environment time is 123. For non-standard clock times, you can also define how much time passage constitutes a "day". This
is just a way to track long time passage in a simpler way. If you're simulating logistics on 2D world where there are 125
"clock ticks" in a day, then setting the stage variable ``daily_time_count`` to 125 will lead to ``pretty_now`` outputs such
as: "Day   1 - 30 clock ticks" for an environment time of 155.

Wait with units
===============

The only feature UPSTAGE currently has that uses the time units for controlling the clock is
the :py:class:`~upstage_des.events.Wait` event. That event takes a ``timeout_unit`` argument that will convert the
given timeout value from the ``timeout_unit`` into the units defined in ``time_unit`` on the stage. If the unit isn't
compatible, then an error will be thrown.

Allowable time units
====================

Time units that UPSTAGE can convert are: seconds, minutes, hours, days, and weeks. The "standard" time values are just
seconds, minutes, and hours. Any other time unit won't use ``pretty_now`` to output "Day - H:M:S" style. Units that
aren't part of those times won't work with the ``Wait`` feature for ``timeout_unit``. 

UPSTAGE tries to lowercase your time units, and allow for some flexibility in saying "s", "second", "hr", "hour", "hours",
and the like. While there are libraries for doing unit conversions, UPSTAGE prefers to have no dependencies other than
SimPy, so it is restricted in that way. 

See the docstring on :py:func:`~upstage_des.units.convert.unit_convert` for more.

However, all time units are convertible into a single unit on initialization or input data processing, and this is the
recommended way to run your simulations to ensure your units are correct and consistent.
