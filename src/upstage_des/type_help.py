# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Help for typing task and simpy generators."""

from collections.abc import Generator
from typing import Any

from simpy import Event as SimEvent

from upstage_des.events import BaseEvent

TASK_GEN = Generator[BaseEvent, Any, None]
SIMPY_GEN = Generator[SimEvent, Any, Any]
