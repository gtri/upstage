# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""The elements in the UPSTAGE Application Programmable Interface."""

# Core
# Director, stage, and Exceptions
# Actor
from upstage_des.actor import Actor
from upstage_des.base import (
    EnvironmentContext,
    MotionAndDetectionError,
    NamedUpstageEntity,
    RulesError,
    SimulationError,
    UpstageBase,
    UpstageError,
    add_stage_variable,
    get_stage,
    get_stage_variable,
)

# Comms
from upstage_des.communications.comms import CommsManager, Message, MessageContent

# Constants
from upstage_des.constants import PLANNING_FACTOR_OBJECT

# Data types
from upstage_des.data_types import (
    CartesianLocation,
    CartesianLocationData,
    GeodeticLocation,
    GeodeticLocationData,
    Location,
)

# Events
from upstage_des.events import All, Any, Event, FilterGet, Get, Put, ResourceHold, Wait

# Motion
from upstage_des.motion import SensorMotionManager, SteppedMotionManager

# Task network nucleus
from upstage_des.nucleus import NucleusInterrupt, TaskNetworkNucleus

# Resources
from upstage_des.resources.container import (
    ContainerEmptyError,
    ContainerError,
    ContainerFullError,
    ContinuousContainer,
)
from upstage_des.resources.monitoring import (
    SelfMonitoringContainer,
    SelfMonitoringContinuousContainer,
    SelfMonitoringFilterStore,
    SelfMonitoringReserveContainer,
    SelfMonitoringSortedFilterStore,
    SelfMonitoringStore,
)
from upstage_des.resources.reserve import ReserveContainer
from upstage_des.resources.sorted import SortedFilterGet, SortedFilterStore

# Routine
from upstage_des.routines import Routine, WindowedGet

# Nucleus-friendly states
from upstage_des.state_sharing import SharedLinearChangingState

# States
from upstage_des.states import (
    CartesianLocationChangingState,
    CommunicationStore,
    DetectabilityState,
    GeodeticLocationChangingState,
    LinearChangingState,
    ResourceState,
    State,
)

# Task
from upstage_des.task import DecisionTask, InterruptStates, Task, TerminalTask, process

# Task Networks
from upstage_des.task_network import TaskLinks, TaskNetwork, TaskNetworkFactory

# Conversion
from upstage_des.units import unit_convert

__all__ = [
    "UpstageError",
    "SimulationError",
    "MotionAndDetectionError",
    "RulesError",
    "Actor",
    "PLANNING_FACTOR_OBJECT",
    "UpstageBase",
    "NamedUpstageEntity",
    "EnvironmentContext",
    "add_stage_variable",
    "get_stage_variable",
    "get_stage",
    "All",
    "Any",
    "Event",
    "Get",
    "FilterGet",
    "SortedFilterGet",
    "Put",
    "ResourceHold",
    "Wait",
    "ContainerEmptyError",
    "ContainerError",
    "ContainerFullError",
    "ContinuousContainer",
    "SelfMonitoringContainer",
    "SelfMonitoringContinuousContainer",
    "SelfMonitoringFilterStore",
    "SelfMonitoringSortedFilterStore",
    "SelfMonitoringReserveContainer",
    "SelfMonitoringStore",
    "ReserveContainer",
    "SortedFilterStore",
    "CartesianLocation",
    "GeodeticLocation",
    "Location",
    "CartesianLocationData",
    "GeodeticLocationData",
    "LinearChangingState",
    "CartesianLocationChangingState",
    "State",
    "GeodeticLocationChangingState",
    "DetectabilityState",
    "ResourceState",
    "CommunicationStore",
    "DecisionTask",
    "Task",
    "process",
    "InterruptStates",
    "TerminalTask",
    "TaskNetwork",
    "TaskNetworkFactory",
    "TaskLinks",
    "TaskNetworkNucleus",
    "NucleusInterrupt",
    "SharedLinearChangingState",
    "CommsManager",
    "Message",
    "MessageContent",
    "SensorMotionManager",
    "SteppedMotionManager",
    "unit_convert",
    "Routine",
    "WindowedGet",
]
