# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from upstage_des import api


def test_api() -> None:
    api_items = dir(api)

    items_to_test = (
        "UpstageError",
        "SimulationError",
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
        "Location",
        "CartesianLocation",
        "GeodeticLocation",
        "CartesianLocationData",
        "GeodeticLocationData",
        "LinearChangingState",
        "CartesianLocationChangingState",
        "State",
        "GeodeticLocationChangingState",
        "DetectabilityState",
        "ResourceState",
        "DecisionTask",
        "Task",
        "process",
        "InterruptStates",
        "TerminalTask",
        "TaskNetwork",
        "TaskNetworkFactory",
        "TaskLinks",
        "CommsManager",
        "Message",
        "MessageContent",
        "MotionAndDetectionError",
        "SensorMotionManager",
        "SteppedMotionManager",
        "TaskNetworkNucleus",
        "NucleusInterrupt",
        "SharedLinearChangingState",
        "CommunicationStore",
        "unit_convert",
        "Routine",
        "WindowedGet",
    )

    for item in items_to_test:
        assert item in api_items

    for item in api_items:
        if not item.startswith("_"):
            assert item in items_to_test
