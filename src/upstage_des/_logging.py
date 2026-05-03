# Copyright (C) 2025 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Logger helpers for actors.

UPSTAGE exposes a logger hierarchy rooted at ``upstage_des``.  Individual
actors emit through ``upstage_des.actor.<actor.name>`` so users can filter,
silence, or route per-actor output with standard ``logging`` configuration.

By default, the root ``upstage_des`` logger has a ``NullHandler`` attached
and inherits ``logging.WARNING`` — quiet by default.  Users opt in by
configuring the logger at their application entry point::

    import logging
    logging.getLogger("upstage_des").setLevel(logging.INFO)
    logging.basicConfig()
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from upstage_des.actor import Actor

ROOT_LOGGER_NAME = "upstage_des"
ACTOR_LOGGER_PREFIX = f"{ROOT_LOGGER_NAME}.actor"


def _install_null_handler() -> None:
    """Attach a ``NullHandler`` to the package logger so library use is silent by default."""
    root = logging.getLogger(ROOT_LOGGER_NAME)
    if not any(isinstance(h, logging.NullHandler) for h in root.handlers):
        root.addHandler(logging.NullHandler())
    if root.level == logging.NOTSET:
        root.setLevel(logging.WARNING)


def get_actor_logger(actor: "Actor") -> logging.Logger:
    """Return the ``logging.Logger`` for a given actor.

    Rehearsal clones get a ``.rehearsal`` suffix so their emissions can
    be filtered independently from real-run logs.
    """
    name = f"{ACTOR_LOGGER_PREFIX}.{actor.name}"
    if getattr(actor, "_is_rehearsing", False):
        name = f"{name}.rehearsal"
    return logging.getLogger(name)
