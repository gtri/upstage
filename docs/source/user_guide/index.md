# User Guide

These pages explain how to use UPSTAGE's primary features with examples.

Some simple simulations are created that demonstrate the basic features, and then each main UPSTAGE feature is covered in depth.

First, UPSTAGE lets you create ``Actors`` and modify the ``States`` of those actors through ``Tasks``, which are assembled into ``TaskNetwork``s that allow control flow of the tasks.

``States`` have multiple features that allow them to be time-varying while respecting discrete event behavior, along with being recordable. More advanced features include "mimicking" other states.

``Tasks`` and their networks can interacted with in multiple ways, and UPSTAGE provides ``Nucleus`` and Interrupt handling to support that.

There are also several convenience features for simulation building and running, including entity naming, geographic functions and states, and safe global variables in an environment context manager.

## Starting Point

These tutorials cover the core features of Actors, States, Tasks, and Task Networks. The final tutorial is a comparison of SimPy and UPSTAGE which will help motivate why UPSTAGE was created.

```{toctree}
:caption: Tutorials
:maxdepth: 1

tutorials/first_simulation
tutorials/interrupts
tutorials/rehearsal
tutorials/best_practices
tutorials/simpy_compare.rst
```

It is also recommended that you familiarize yourself with how [SimPy runs by itself](https://simpy.readthedocs.io/en/latest/), since
UPSTAGE is a layer on top of that library.

## Full Examples

These are complete examples for some of the above tutorials.

```{toctree}
:caption: Full Examples
:maxdepth: 1

tutorials/first_sim_full.rst
tutorials/rehearsal_sim.rst
tutorials/complex_cashier.rst
```

## How-to Guides

These pages detail the specific activities that can be accomplished using UPSTAGE, including how to extend UPSTAGE's features.

```{toctree}
:caption: How-Tos
:maxdepth: 1

how_tos/resource_states.rst
how_tos/active_states.rst
how_tos/mimic_states.rst
how_tos/nucleus.rst
how_tos/stage_variables.rst
how_tos/events.rst
how_tos/geography.rst
how_tos/decision_tasks.rst
how_tos/task_networks.rst
how_tos/state_sharing.rst
how_tos/entity_naming.rst
how_tos/motion_manager.rst
how_tos/communications.rst
how_tos/typing.rst
how_tos/random_numbers.rst
```
