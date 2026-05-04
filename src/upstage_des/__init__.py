# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""A framework for modeling and simulating complex systems of systems.

UPSTAGE (i.e., the Universal Platform for Simulating Tasks and Actors with
Graphs and Events) is built atop of SimPy, with the intent of simplifying the
development process for complex simulations.

"""

from ._logging import _install_null_handler
from ._version import __authors__, __version__

_install_null_handler()

__all__ = ("__authors__", "__version__")
