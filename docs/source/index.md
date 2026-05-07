# UPSTAGE

The Universal Platform for Simulating Tasks and Actors with Graphs and Events (UPSTAGE) library is a Python framework for creating robust, behavior-driven Discrete Event Simulations (DES).
The primary goal of UPSTAGE is to enable the quick creation of simulations at any desired level of abstraction with built-in data recording, simulation integrity and runtime checks, and
assistance for the usual pitfalls in custom discrete-event simulation: interrupts and cancellations.

UPSTAGE - which is built on the [SimPy](https://simpy.readthedocs.io/en/latest/) library - contains two primary components that are assembled to create a broad array of simulations.

The components are Actor - which contain State - and Task. Actors can have multiple networks running on them, their states can be shared, and there are features for interactions between task networks running on the same actor. Those tasks modify the states on their actor, with features for real-time states that update on request without requiring time-stepping or modifying the existing events.

```{image} _static/upstage-flow.png
:align: center
```

Additional features include:

1. Context-aware EnvironmentContext , accessed via UpstageBase, enabling thread-safe simulation globals for the Stage and Named Entities (see below).
2. Active States, such as LinearChangingState which represent continuous-time attributes of actors at discrete points.
3. Named Entitites in a thread-safe global context, enabling easier "director" logic creation with fewer args in your code
4. The stage: a global context variable for simulation properties and attributes. This enables under-the-hood coordination of motion, geography, and other features.
5. All States are recordable, and some record dataclass and dictionary values.
6. Numerous runtime checks and error handling for typical DES pitfalls: based on years of custom DES-building experience.
7. And more!

```{note}
This project is under active development. This branch of the docs is for the unreleased version 1.0. The docs may be innacurate.
```

## Installation from source

You can download UPSTAGE and install it manually. Clone, or download the archive and extract it. From the extraction location (and within a suitable Python environment):

```console
(venv) $ python -m pip install .
```

(or just `pip install .`)



## Contributing

To contribute to UPSTAGE, or to learn the steps for building documentation, running tests, and putting
in PRs, see [CONTRIBUTING.MD](https://github.com/gtri/upstage/blob/main/CONTRIBUTING.md))

## License and Attribution

This software is licensed under the BSD 3-Clause. Please see the `LICENSE` file in the repository for details.
