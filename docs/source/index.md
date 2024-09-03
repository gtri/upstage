# ![logo](_static/upstage-logo-medium.png) UPSTAGE

The Universal Platform for Simulating Tasks and Actors with Graphs and Events (UPSTAGE) library is a Python framework for creating robust, behavior-driven Discrete Event Simulations (DES).
The primary goal of UPSTAGE is to enable the quick creation of simulations at any desired level of abstraction with built-in data recording, simulation integrity and runtime checks, and
assistance for the usual pitfalls in custom discrete-event simulation: interrupts and cancellations.

UPSTAGE - which is built on the [SimPy](https://simpy.readthedocs.io/en/latest/) library - contains two primary components that are assembled to create a broad array of simulations.

The components are {{ Actor }} - which contain {{ State }} - and {{ Task }}, which can be assembled into a {{ TaskNetwork }}. Actors can have multiple networks running on them, their states can be shared, and there are features for interactions between task networks running on the same actor. Those tasks modify the states on their actor, with features for real-time states that update on request without requiring time-stepping or modifying the existing events.

```{image} _static/upstage-flow.png
:align: center
```

Additional features include:

1. Context-aware {{ EnvironmentContext }}, accessed via {{ UpstageBase }}, enabling thread-safe simulation globals for the Stage and Named Entities (see below).
2. Active States, such as {{ LinearChangingState }} which represent continuous-time attributes of actors at discrete points.
3. Spatial-aware data types like {{ CartesianLocation }}, and states like the waypoint-following {{ GeodeticLocationChangingState }}.
4. Geodetic and cartesian positions, distances, and motion - with ranged sensing.
5. {{ NamedEntity }} in a thread-safe global context, enabling easier "director" logic creation with fewer args in your code
6. The stage: a global context variable for simulation properties and attributes. This enables under-the-hood coordination of motion, geography, and other features.
7. Rehearsal: Write planning and simulation code in one place only, and "rehearse" an actor through a task network using planning factors to discover task feasibility.
8. All States are recordable
9. Numerous runtime checks and error handling for typical DES pitfalls: based on years of custom DES-building experience.
10. And more!

```{note}
This project is under active development.
```

## Installation

```{warning}
Work-In-Progress
```

```console
(venv) $ pip install upstage
```

### Installation from source

Alternatively, you can download UPSTAGE and install it manually. Clone, or download the archive and extract it. From the extraction location (and within a suitable Python environment):

```console
(venv) $ python -m pip install .
```

(or just `pip install .`)

### Installation for running tests

Note that the tests include the two full examples from the documentation.

```console
(venv) $ pip install uptage[test]
(venv) $ pytest
```

### Installation for building docs

Unless you're adding to the codebase, you won't need to run the `sphinx-apidoc` command.

```console
(venv) $ pip install upstage[docs]
(venv) $ sphinx-apidoc -o .\docs\source\ .\src\upstage\ .\src\upstage\test\
(venv) $ sphinx-build -b html .\docs\source\ .\docs\build\
```

## User Guide

```{toctree}
:caption: Guide
:maxdepth: 3

user_guide/index
```

## Contributing

To contribute to UPSTAGE, or to learn the steps for building documentation and running tests, see [CONTRIBUTING.MD](https://github.com/JamesArruda/upstage/blob/main/CONTRIBUTING.md))

## License and Attribution

This software is licensed under the BSD 3-Clause. Please see the `LICENSE` file in the repository for details.

## Reference

This section contains information-oriented reference materials for developers
looking to understand the UPSTAGE software components and its API.

The API documentation is auto-generated.

```{toctree}
:caption: API
:maxdepth: 2

modules.rst
```
