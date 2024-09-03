=========
Geography
=========

UPSTAGE has built-in features for simple geographic math and behaviors. These features are built up into a :py:class:`~upstage.states.GeodeticLocation` state.

Discrete Event Simulation does not lend itself well to geography and repeated distance checking (for something like a sensor, e.g.), so UPSTAGE provides the capability to
schedule intersections of moving actors and stationary sensors. Those features are covered in the :doc:`Motion Manager <motion_manager>` documentation.

UPSTAGE prefers geography to be in Latitude / Longitude / Altitude order.

The geographic code is not meant to maintain a high level of precision in all calculations. Given the naturally abstracting nature of DES, some small errors are expected in terms of timing and distances.
For most simulations, these small differences have no effect on the results or behavior. Also, the code is done entirely with built-in ``math`` functions. We preferred to avoid ``numpy`` just to keep
the install dependencies to ``SimPy``. 


Geographic DataTypes and State
===============================

These are the built-in features that use geography:

:py:class:`~upstage.data_types.GeodeticLocation`
------------------------------------------------

This data type stores a Latitude / Longitude / Altitude (optional) for a point around the globe.

Two geodetic locations can be subtracted from each other to get their great circle path distance at zero altitude:

.. note::

    All distances are ground distances for Spherical and WGS84 unless you ask for a different one. Therefore, all speeds should be ground speed.

    Altitude is taken into account for intersection and range (see :doc:`motion_manager`)

.. code-block:: python

    from upstage.geography import Spherical

    with UP.EnvironmentContext():
        UP.add_stage_variable("stage_model", Spherical)
        UP.add_stage_variable("distance_units", "nmi")
        UP.add_stage_variable("altitude_units", "ft")
        # Note that in_radians defaults to False.
        loc1 = UP.GeodeticLocation(33.7490, -84.3880, 1050, in_radians=False)
        loc2 = UP.GeodeticLocation(39.7392, -104.9903, 30_000, in_radians=False)
        dist = loc1 - loc2
        print(dist)
        >>> 1052.6666594454714
        dist_with_altitude = loc1.dist_with_altitude(loc2)
        >>> 1052.6774420025818
        straight_line = loc1.straight_line_distance(loc2)
        >>> 1049.3621152419862

Location instances *must* be created within an :py:class:`~upstage.base.EnvironmentContext` context, otherwise they won't have access to the geographic model at runtime. Additionally, these stage variables must be set:

* ``stage_model`` must be set to be either ``Spherical`` or ``WGS84``, or whatever class performs ``.distance`` on lat/lon/altitude pairs. 
* ``distance_units``: One of: "m", "km", "mi", "nmi", or "ft"
* OPTIONAL: ``altitude_units``: One of: "m", "km", "mi", "nmi", or "ft". Altitude can be different, because feet or meters are typical for altitude, while mi/nmi/km are typical for point to point distances.
   
   * Include this for any geographic features using intersections or for the ``GeodeticLocationChangingState``

The distance between two points is the great circle distance, and altitude is ignored. This is a design choice for simplicity, where altitude change doesn't affect timing, especially over long distances. This also means
that any speeds you specify are implicitly ground speed, which is more useful.

However, if a sensor is looking straight up, the distance to an object 30 thousand feet up shouldn't be zero. To account for altitude in the distance, use
:py:func:`~upstage.data_types.GeodeticLocation.dist_with_altitude` or :py:func:`~upstage.data_types.GeodeticLocation.straight_line_distance`.
Note that the intersection models (covered elsewhere) do distance checks in ECEF, not with the ``GeodeticLocation`` subtraction method, so you don't have to worry about this distinction for those motion features.

Once a ``GeodeticLocation`` is created, it cannot be changed. This is for safety of not changing a location from underneath code that expects to use it a certain way. Some methods are provided to help get copies:

* :py:meth:`~upstage.data_types.GeodeticLocation.copy`: Make a copy of the location
* :py:meth:`~upstage.data_types.GeodeticLocation.to_radians`: Make a copy of the location with the latitude and longitude in radians
* :py:meth:`~upstage.data_types.GeodeticLocation.to_degrees`: Make a copy of the location with the latitude and longitude in degrees


For comparison, here's what ``pyproj`` gets for the calculations (pyproj is not currently a dependency for UPSTAGE):

.. code-block:: python

    import pyproj
    from upstage.api import unit_convert
    # NOTE: Numpy is not a requirement of UPSTAGE
    import numpy as np

    lonlatalt_to_ecef_transformer: pyproj.Transformer = pyproj.Transformer.from_crs(
        {"proj": "latlong", "ellps": "WGS84", "datum": "WGS84"},
        {"proj": "geocent", "ellps": "WGS84", "datum": "WGS84"}
    )
    lat1, lon1 = 33.7490, -84.3880
    lat2, lon2 = 39.7392, -104.9903
    ecef_1 = lonlatalt_to_ecef_transformer.transform(lon1, lat1, 0)
    ecef_2 = lonlatalt_to_ecef_transformer.transform(lon2, lat2, 0)
    dist_m = np.sqrt(((np.array(ecef_1) - np.array(ecef_2))**2).sum())
    dist = unit_convert(dist_m, "m", "nmi")
    # The straight-line ECEF distance
    print(dist)
    >>> 1049.302887568968
    az12,az21,dist = pyproj.Geod(ellps='WGS84').inv(-84.3880, 33.7490, -104.9903, 39.7392)
    dist = UP.unit_convert(dist, "m", "nmi")
    # The great-circle distance
    print(dist)
    >>> 1053.3987119745102

Both distances are within .07% of UPSTAGE's calculations.



:py:class:`~upstage.states.GeodeticLocationChangingState`
---------------------------------------------------------

This is a State that allows activation and movement along great-circle waypoints with altitude changing along the waypoints. When initializing, it accepts a ``GeodeticLocation`` object, and it returns those when you ask it for
the state's value. Here is its basic usage:

.. code-block:: python

    from upstage.utils import waypoint_time_and_dist

    class Plane(UP.Actor):
        location: UP.GeodeticLocation = UP.GeodeticLocationChangingState(recording=True)
        speed = UP.State[float](valid_types=float, default=100.0)

    class Fly(UP.Task):
        def task(self, *, actor: Plane):
            # waypoints do not include the starting point
            waypoints = actor.get_knowledge("flying to", must_exist=True)
            time, dist = waypoint_time_and_dist(
                start=actor.location,
                waypoints=waypoints,
                speed=actor.speed,
            )
            actor.activate_location_state(
                state="location",
                waypoints=waypoints,
                speed=actor.speed,
                task=self,
            )
            yield UP.Wait(time)
            actor.deactivate_state(state="location", task=self)


    with UP.EnvironmentContext():
        plane = Plane(
            name="Flyer",
            location = UP.GeodeticLocation(lat, lon, alt),
        )
        ...

The :py:func:`~upstage.utils.waypoint_time_and_dist` function is a convenience function that gets the great circle distance and time over a set of waypoints to help schedule the arrival time.


Cartesian Locations
===================

These aren't geographic, but they serve the same purpose, so we include them here.

:py:class:`~upstage.data_types.CartesianLocation`
-------------------------------------------------

This data type stores an X / Y / Z (optional) location in 2 or 3D space (z is set to zero if not included).

Two cartestian locations can be subtracted from each other to get their distance:

.. code-block:: python

    with UP.EnvironmentContext():
        # use_altitude_units defaults to False - meaning you don't need to set the stage variables.
        loc1 = UP.CartesianLocation(33.7490, -84.3880, 1050, use_altitude_units=False)
        loc2 = UP.CartesianLocation(39.7392, -104.9903, 30_000, use_altitude_units=False)
        dist = loc1 - loc2
        print(dist)
        >>> 28950.007950556097


We still allow you to set distance and altitude units because the 'z' value could be in a different units system.

.. code-block:: python

    with UP.EnvirronmentContext():
        UP.add_stage_variable("distance_units", "km")
        UP.add_stage_variable("altitude_units", "m")
        loc1 = UP.CartesianLocation(33.7490, -84.3880, 1050, use_altitude_units=True)
        loc2 = UP.CartesianLocation(39.7392, -104.9903, 30_000, use_altitude_units=True)
        dist = loc1 - loc2
        print(dist)
        >>> 36.0338696413527

The distance is always implied to be in ``distance_units``, without setting it. If the z component is in a different unit, then we need to know both to get the straight-line distance.


:py:class:`~upstage.states.CartesianLocationChangingState`
----------------------------------------------------------

This active state works the exact same as the ``GeodeticLocationChangingState`` , except that it requires waypoints to be ``CartesianLocation`` s.


Geography Sub-Module
====================

The :py:mod:`upstage.geography` module contains:

:py:class:`~upstage.geography.spherical.Spherical`
--------------------------------------------------

This class contains methods for finding distances, positions, and for segmenting great-circle paths on the assumption of a spherical earth.

Typically, you will not need to use these methods directly, but they are avaiable and can be useful for results plotting, for example. 

The most useful methods, besides distance, may be:

#. :py:meth:`~upstage.geography.spherical.Spherical.geo_linspace`, which will give you evenly spaced points along a great circle route. 
#. :py:meth:`~upstage.geography.spherical.Spherical.geo_circle`, which will give you evently spaced points to draw a circle in spherical coordinates
#. :py:meth:`~upstage.geography.spherical.Spherical.point_from_bearing_dist`, which gives you a point relative to a base location at some distance and bearing.

:py:class:`~upstage.geography.wgs84.WGS84`
-------------------------------------------

This class contains methods for finding distances, positions, and for segmenting great-circle paths on the assumption of a WGS84 ellipsoid. These methods take longer to run than the Spherical version,
so be sure the extra accuracy is worth it.

Typically, you will not need to use these methods directly, but they are avaiable and can be useful for results plotting, for example. 

The most useful methods, besides distance, may be:

#. :py:meth:`~upstage.geography.spherical.WGS84.geo_linspace`, which will give you evenly spaced points along a great circle route. 
#. :py:meth:`~upstage.geography.spherical.WGS84.geo_circle`, which will give you evently spaced points to draw a circle in spherical coordinates
#. :py:meth:`~upstage.geography.spherical.WGS84.point_from_bearing_dist`, which gives you a point relative to a base location at some distance and bearing.

:py:mod:`upstage.geography.intersections`
-------------------------------------------

The :py:func:`~upstage.geography.intersections.get_intersection_locations` function calculates an intersection between a great circle path and a sphere. It can be passed an instance of ``Spherical`` or ``WGS84``
to do distance calculations with.

The intersections are calculated by taking evenly spaced points along the great circle path and finding the two points where an intersection occurs between. It then divides that segment more finely, and calculates
the two points where the intersection is between. The number of point in the subdividing process is an input through ``subdivide_levels``, which default to 10 and 20. Before the subdivision happens, the code uses
``dist_between`` to do the first division. The default is 5 nautical miles. If you have a 5 nmi distance, then do 10 and 20 subdivisions, the distance of each segment is roughly 152 feet, which is the maximum error
of the intersection point in that case.
