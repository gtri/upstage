# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Communications process helper."""

from collections.abc import Callable, Generator
from typing import Any

from simpy import Event, Process, Store

from upstage_des.communications.comms import CommsManager, Message, MessageContent
from upstage_des.task import process


def generate_comms_wait(
    incoming_store: Store,
    callback: Callable[[MessageContent], Any],
) -> Callable[[], Process]:
    """Create a process function to transfer communications to a callback.

    This hides cleanup and other stability functions from the user.

    Parameters
    ----------
    incoming_store : A simpy or upstage store
        The store that is linked to a CommsManager instance.
    callback : function
        The function to call with a received message

    Returns:
    -------
    function
        An UPSTAGE process function that passes messages
    """

    @process
    def comms_wait_proc() -> Generator[Event, str | Message, None]:
        while True:
            message = yield incoming_store.get()
            message = CommsManager.clean_message(message)
            callback(message)

    return comms_wait_proc
