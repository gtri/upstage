==============
API Stability
==============

This page describes the stability guarantees for UPSTAGE's public API.
It is aimed at users writing production simulations and at tooling
(IDEs, code-generation agents, etc.) that need to know which parts of
the API are safe to rely on.

Import surface
==============

All stable symbols are re-exported from a single module:

.. code-block:: python

    import upstage_des.api as UP

This is the canonical import path.  Every symbol listed in the tables
below is available as ``UP.<Name>``.  Internal modules (``upstage_des.base``,
``upstage_des.actor``, ``upstage_des.task``, etc.) may change shape
without notice; importing directly from them puts you in the
"experimental" tier regardless of what you import.

Stability tiers
===============

**Stable** — breaking changes are treated as breaking changes:
deprecation warning for at least one minor release, listed in the
changelog, migration guidance provided.

**Experimental** — subject to change in minor releases.  Changes
documented in the changelog, but no deprecation cycle guaranteed.

**Internal** — anything not listed below.  Names starting with a single
underscore (``_foo``), and any symbol reached through a module path
other than ``upstage_des.api``.  No stability guarantees.

Stable surface
==============

Core
----

+---------------------------------+---------------------------------------------+
| Symbol                          | Purpose                                     |
+=================================+=============================================+
| ``UP.Actor``                    | Base class for actors.                      |
+---------------------------------+---------------------------------------------+
| ``UP.State``                    | Descriptor for actor state.                 |
+---------------------------------+---------------------------------------------+
| ``UP.Task``                     | Base class for tasks.                       |
+---------------------------------+---------------------------------------------+
| ``UP.TaskNetwork``              | Runtime task-network instance.              |
+---------------------------------+---------------------------------------------+
| ``UP.TaskNetworkFactory``       | Factory for task-network instances.         |
+---------------------------------+---------------------------------------------+
| ``UP.TaskLinks``                | Link/transition declarations.               |
+---------------------------------+---------------------------------------------+
| ``UP.EnvironmentContext``       | Context manager for the simulation env.     |
+---------------------------------+---------------------------------------------+
| ``UP.Wait``, ``UP.Get``,        | Event wrappers used inside ``Task.task``.   |
| ``UP.Put``, ``UP.Any``,         |                                             |
| ``UP.All``, ``UP.FilterGet``,   |                                             |
| ``UP.ResourceHold``, ``UP.Event``|                                            |
+---------------------------------+---------------------------------------------+
| ``UP.process``                  | Decorator for simpy process generators.     |
+---------------------------------+---------------------------------------------+
| ``UP.UpstageError``,            | Exception hierarchy.                        |
| ``UP.SimulationError``,         |                                             |
| ``UP.RulesError``,              |                                             |
| ``UP.MotionAndDetectionError``  |                                             |
+---------------------------------+---------------------------------------------+

States (stable)
---------------

``UP.LinearChangingState``, ``UP.CartesianLocationChangingState``,
``UP.GeodeticLocationChangingState``, ``UP.DetectabilityState``,
``UP.DictionaryState``, ``UP.DataclassState``, ``UP.ResourceState``,
``UP.MultiStoreState``, ``UP.CommunicationStore``,
``UP.SharedLinearChangingState``.

Resources (stable)
------------------

``UP.ContinuousContainer``, ``UP.ReserveContainer``,
``UP.SortedFilterStore``, ``UP.SortedFilterGet``,
``UP.SelfMonitoringStore``, ``UP.SelfMonitoringContainer``,
``UP.SelfMonitoringContinuousContainer``,
``UP.SelfMonitoringFilterStore``, ``UP.SelfMonitoringReserveContainer``,
``UP.SelfMonitoringSortedFilterStore``, and their error classes.

Data types and units (stable)
-----------------------------

``UP.Location``, ``UP.CartesianLocation``, ``UP.GeodeticLocation``,
``UP.CartesianLocationData``, ``UP.GeodeticLocationData``,
``UP.unit_convert``.

Stage and entities (stable)
---------------------------

``UP.UpstageBase``, ``UP.NamedUpstageEntity``,
``UP.add_stage_variable``, ``UP.get_stage_variable``, ``UP.get_stage``.

Typing helpers (stable)
-----------------------

``UP.TASK_GEN``, ``UP.SIMPY_GEN``, ``UP.ROUTINE_GEN``.  These are the
recommended return-type annotations for task and process generators.

Experimental surface
====================

These APIs are **working today** but may change as we iterate.  Build on
them, but pin your UPSTAGE version if your production code depends on
details beyond the top-level names.

+------------------------------------+----------------------------------------+
| Symbol                             | Why experimental                       |
+====================================+========================================+
| ``UP.Transition``                  | The normalised form for task-network   |
|                                    | transitions.  User-level tuple input   |
|                                    | remains stable; the ``Transition``     |
|                                    | shape itself may gain fields.          |
+------------------------------------+----------------------------------------+
| ``TaskLinks(transitions=[...])``   | Guard-based transitions are new.  Tuple|
|                                    | input ``(target, guard)`` /            |
|                                    | ``(target, guard, label)`` is stable,  |
|                                    | but priority/metadata fields may grow. |
+------------------------------------+----------------------------------------+
| ``Task.on_enter`` / ``on_exit``    | Zero-time hooks.  Signature is stable; |
|                                    | the call site inside the network loop  |
|                                    | may gain guarantees (e.g., ordering    |
|                                    | with nucleus interrupts).              |
+------------------------------------+----------------------------------------+
| ``TaskNetwork.to_mermaid`` /       | Output *format* is not stable — the    |
| ``to_dot``                         | layout, styling, and legend may        |
|                                    | evolve.  The method signatures are     |
|                                    | stable.                                |
+------------------------------------+----------------------------------------+
| Class-keyed                        | The ``{TaskCls: TaskLinks(...)}`` form |
| ``TaskNetworkFactory``             | is stable.  Validation messages and    |
|                                    | inferred-name heuristics may change.   |
+------------------------------------+----------------------------------------+
| ``UP.TaskNetworkNucleus``,         | Nucleus integration is stable at the   |
| ``UP.NucleusInterrupt``            | import level but its interrupt-cause   |
|                                    | payload shape is not frozen.           |
+------------------------------------+----------------------------------------+
| ``UP.SensorMotionManager``,        | Motion managers: public API is stable, |
| ``UP.SteppedMotionManager``        | internals are still evolving.          |
+------------------------------------+----------------------------------------+
| ``UP.PointToPointCommsManager``,   | Comms managers: message routing        |
| ``UP.RoutingTableCommsManager``,   | semantics may change.                  |
| ``UP.Message``, ``UP.MessageContent``|                                     |
+------------------------------------+----------------------------------------+
| ``UP.Routine``, ``UP.WindowedGet`` | Routine base class and builders.       |
+------------------------------------+----------------------------------------+

Internal — do not rely on
=========================

Anything reached through these paths is internal:

* ``upstage_des.base``, ``upstage_des.actor``, ``upstage_des.task``,
  ``upstage_des.states``, ``upstage_des.task_network``,
  ``upstage_des.events``, ``upstage_des.data_types``,
  ``upstage_des.resources.*``, ``upstage_des.motion.*``,
  ``upstage_des.communications.*``, ``upstage_des.geography.*``,
  ``upstage_des.data_utils.*``, ``upstage_des.utils``,
  ``upstage_des.math_utils``, ``upstage_des.nucleus``,
  ``upstage_des.state_sharing``, ``upstage_des.state_proxies``,
  ``upstage_des.routines``, ``upstage_des.constants``,
  ``upstage_des.type_help``.
* Any attribute or method whose name starts with an underscore
  (``_state_defs``, ``_debug_log``, ``_resolve``, ``_all_targets``,
  ``_next_task_name``, etc.).
* ``upstage_des.test.*`` — internal tests, not a fixtures library.

These are free to change in any release without notice.  If you find
yourself reaching for an internal, please `open an issue
<https://github.com/gtri/upstage/issues>`_ so we can discuss promoting
the symbol.

Logging
=======

UPSTAGE exposes a :mod:`logging` hierarchy rooted at ``upstage_des``.  The
library is silent by default — a ``NullHandler`` is attached on import and
the package logger defaults to ``WARNING``.  Opt in at your application
entry point::

    import logging

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    logging.getLogger("upstage_des").setLevel(logging.INFO)

Actor events go to ``upstage_des.actor.<actor.name>``.  Rehearsal clones
emit under ``upstage_des.actor.<actor.name>.rehearsal`` so you can filter
rehearsal output independently::

    logging.getLogger("upstage_des.actor").setLevel(logging.INFO)
    logging.getLogger("upstage_des.actor").addFilter(
        lambda rec: ".rehearsal" not in rec.name
    )

Inside a custom :class:`Task`, call ``actor.log`` with printf-style
arguments.  Formatting is deferred — when the log level is disabled and
``debug_log=False`` on the actor, the interpolation never runs, so
``repr``/``str`` cost on your arguments is avoided in hot loops::

    def task(self, *, actor):
        actor.log("picked up %s (qty=%d)", item, qty)        # INFO
        actor.log("low fuel: %.1f%%", remaining, level=logging.WARNING)

Two independent sinks are driven by every ``log`` call:

* The per-actor in-memory list (``actor.get_log()`` /
  ``actor._debug_log``) — controlled by the ``debug_log`` flag set at
  actor construction.  Use this for post-run analysis in notebooks.
* Python's ``logging`` — controlled by the standard level hierarchy.
  Use this for structured sinks (files, JSON, stdout during dev).

Deprecation policy
==================

When a **stable** symbol is slated for removal:

1. A ``DeprecationWarning`` is added on use, with a pointer to the
   replacement.
2. The symbol appears in the changelog under "Deprecated" for the
   minor release that introduces the warning.
3. Removal happens no sooner than one minor release later, and is
   listed under "Removed" in the changelog.

**Experimental** symbols may change without this cycle.  Breaking
changes to experimental APIs are still documented in the changelog.
