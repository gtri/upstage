# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Functions to help clean/clear the sim out."""

from upstage_des.actor import Actor


def clean_actor(actor: Actor) -> None:
    """End all tasks and delete actor memory.

    Args:
        actor (Actor): The actor to clean.
    """
    actor._clean()
