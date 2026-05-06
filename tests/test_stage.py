# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test the stage."""

import pytest
from random import Random

from upstage_des.base import (
    EnvironmentContext,
    Stage,
    UpstageBase,
    UpstageError,
    add_stage_variable,
    get_stage,
    get_stage_variable,
)


def test_stage_default_values() -> None:
    with EnvironmentContext():
        stage = get_stage()
        assert stage.altitude_units == "ft"
        assert stage.distance_units == "nmi"
        assert stage.time_unit == "hr"
        assert stage.daily_time_count == 24.0
        assert stage.debug_log_time is False
        assert isinstance(stage.userdata, dict)
        assert len(stage.userdata) == 0


def test_stage_custom_initialization() -> None:
    rng = Random(42)
    stage = Stage(
        random=rng,
        altitude_units="m",
        distance_units="km",
        time_unit="s",
        daily_time_count=86400.0,
        debug_log_time=True,
    )
    with EnvironmentContext(stage=stage):
        retrieved_stage = get_stage()
        assert retrieved_stage is stage
        assert retrieved_stage.altitude_units == "m"
        assert retrieved_stage.distance_units == "km"
        assert retrieved_stage.time_unit == "s"
        assert retrieved_stage.daily_time_count == 86400.0
        assert retrieved_stage.debug_log_time is True


def test_stage_random_with_seed() -> None:
    with EnvironmentContext(random_seed=12345):
        stage = get_stage()
        assert isinstance(stage.random, Random)
        value1 = stage.random.random()
    
    with EnvironmentContext(random_seed=12345):
        stage = get_stage()
        value2 = stage.random.random()
    
    assert value1 == value2


def test_stage_random_with_generator() -> None:
    rng = Random(99999)
    expected_value = rng.random()
    
    rng = Random(99999)
    with EnvironmentContext(random_gen=rng):
        stage = get_stage()
        value = stage.random.random()
    
    assert value == expected_value


def test_stage_random_generator_takes_precedence() -> None:
    rng = Random(99999)
    with EnvironmentContext(random_seed=12345, random_gen=rng):
        stage = get_stage()
        assert stage.random is rng


def test_stage_access_from_upstage_base() -> None:
    with EnvironmentContext():
        base = UpstageBase()
        stage = base.stage
        assert stage.altitude_units == "ft"


def test_stage_not_available_outside_context() -> None:
    with pytest.raises(LookupError):
        get_stage()


def test_stage_property_error_outside_context() -> None:
    with pytest.warns(UserWarning, match="Environment not created at instantiation"):
        base = UpstageBase()
    with pytest.raises(LookupError):
        _ = base.stage


def test_stage_set_altitude_units_once() -> None:
    with EnvironmentContext():
        stage = get_stage()
        assert stage.altitude_units == "ft"
        
        stage.altitude_units = "miles"
        assert stage.altitude_units == "miles"
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.altitude_units = "meters"


def test_stage_set_distance_units_once() -> None:
    with EnvironmentContext():
        stage = get_stage()
        assert stage.distance_units == "nmi"
        
        stage.distance_units = "km"
        assert stage.distance_units == "km"
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.distance_units = "miles"


def test_stage_set_time_unit_once() -> None:
    with EnvironmentContext():
        stage = get_stage()
        assert stage.time_unit == "hr"
        
        stage.time_unit = "s"
        assert stage.time_unit == "s"
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.time_unit = "min"


def test_stage_set_daily_time_count_once() -> None:
    with EnvironmentContext():
        stage = get_stage()
        assert stage.daily_time_count == 24.0
        
        stage.daily_time_count = 86400.0
        assert stage.daily_time_count == 86400.0
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.daily_time_count = 1440.0


def test_stage_set_debug_log_time_once() -> None:
    with EnvironmentContext():
        stage = get_stage()
        assert stage.debug_log_time is False
        
        stage.debug_log_time = True
        assert stage.debug_log_time is True
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.debug_log_time = False


def test_stage_set_random_once() -> None:
    with EnvironmentContext():
        stage = get_stage()
        original_rng = stage.random
        
        new_rng = Random(42)
        stage.random = new_rng
        assert stage.random is new_rng
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.random = Random(100)


def test_stage_set_all_attributes_once() -> None:
    rng = Random(42)
    with EnvironmentContext(random_gen=rng):
        stage = get_stage()
        
        stage.altitude_units = "m"
        assert stage.altitude_units == "m"
        
        stage.distance_units = "km"
        assert stage.distance_units == "km"
        
        stage.time_unit = "s"
        assert stage.time_unit == "s"
        
        stage.daily_time_count = 86400.0
        assert stage.daily_time_count == 86400.0
        
        stage.debug_log_time = True
        assert stage.debug_log_time is True
        
        new_rng = Random(100)
        stage.random = new_rng
        assert stage.random is new_rng
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.altitude_units = "ft"
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.distance_units = "nmi"
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.time_unit = "hr"
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.daily_time_count = 24.0
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.debug_log_time = False
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.random = Random(200)


def test_add_stage_variable() -> None:
    with EnvironmentContext():
        add_stage_variable("custom_var", 42)
        stage = get_stage()
        assert stage.userdata["custom_var"] == 42


def test_get_stage_variable_from_userdata() -> None:
    with EnvironmentContext():
        add_stage_variable("custom_var", "test_value")
        value = get_stage_variable("custom_var")
        assert value == "test_value"


def test_get_stage_variable_from_stage_attribute() -> None:
    with EnvironmentContext():
        value = get_stage_variable("altitude_units")
        assert value == "ft"


def test_add_stage_variable_duplicate_error() -> None:
    with EnvironmentContext():
        add_stage_variable("my_var", 10)
        with pytest.raises(UpstageError, match="already exists in the stage userdata"):
            add_stage_variable("my_var", 20)


def test_add_stage_variable_conflicts_with_stage_attribute() -> None:
    with EnvironmentContext():
        with pytest.raises(UpstageError, match="already exists in the stage"):
            add_stage_variable("altitude_units", "m")


def test_get_stage_variable_nonexistent() -> None:
    with EnvironmentContext():
        with pytest.raises(UpstageError, match="does not exist"):
            get_stage_variable("nonexistent_var")


def test_stage_userdata_mutable() -> None:
    with EnvironmentContext():
        stage = get_stage()
        stage.userdata["test_key"] = "test_value"
        assert stage.userdata["test_key"] == "test_value"
        
        stage.userdata["test_key"] = "updated_value"
        assert stage.userdata["test_key"] == "updated_value"


def test_stage_attributes_independent_across_contexts() -> None:
    with EnvironmentContext():
        stage1 = get_stage()
        stage1.altitude_units = "m"
        assert stage1.altitude_units == "m"
    
    with EnvironmentContext():
        stage2 = get_stage()
        assert stage2.altitude_units == "ft"
        stage2.altitude_units = "km"
        assert stage2.altitude_units == "km"


def test_stage_shared_across_instances() -> None:
    with EnvironmentContext():
        base1 = UpstageBase()
        base2 = UpstageBase()
        
        stage1 = base1.stage
        stage2 = base2.stage
        
        assert stage1 is stage2


def test_stage_context_isolation() -> None:
    with EnvironmentContext(random_seed=1):
        stage1 = get_stage()
        stage1.userdata["test"] = "value1"
        
        with EnvironmentContext(random_seed=2):
            stage2 = get_stage()
            assert "test" not in stage2.userdata
            stage2.userdata["test"] = "value2"
            assert stage2.userdata["test"] == "value2"
        
        assert stage1.userdata["test"] == "value1"


def test_stage_random_different_without_seed() -> None:
    with EnvironmentContext():
        stage1 = get_stage()
        value1 = stage1.random.random()
    
    with EnvironmentContext():
        stage2 = get_stage()
        value2 = stage2.random.random()
    
    assert value1 != value2


def test_multiple_random_calls_same_sequence() -> None:
    with EnvironmentContext(random_seed=12345):
        stage = get_stage()
        values1 = [stage.random.random() for _ in range(5)]
    
    with EnvironmentContext(random_seed=12345):
        stage = get_stage()
        values2 = [stage.random.random() for _ in range(5)]
    
    assert values1 == values2


def test_stage_userdata_complex_types() -> None:
    with EnvironmentContext():
        stage = get_stage()
        stage.userdata["dict_data"] = {"nested": {"key": "value"}}
        stage.userdata["list_data"] = [[1, 2], [3, 4]]
        stage.userdata["set_data"] = {1, 2, 3}
        
        assert stage.userdata["dict_data"]["nested"]["key"] == "value"
        assert stage.userdata["list_data"][1][0] == 3
        assert 2 in stage.userdata["set_data"]


def test_stage_userdata_always_mutable() -> None:
    with EnvironmentContext():
        stage = get_stage()
        
        stage.userdata["key1"] = "value1"
        assert stage.userdata["key1"] == "value1"
        
        stage.userdata["key1"] = "value2"
        assert stage.userdata["key1"] == "value2"
        
        stage.userdata["key1"] = "value3"
        assert stage.userdata["key1"] == "value3"


def test_stage_read_before_set() -> None:
    with EnvironmentContext():
        stage = get_stage()
        
        assert stage.altitude_units == "ft"
        
        stage.altitude_units = "m"
        assert stage.altitude_units == "m"


def test_stage_multiple_attributes_set_independently() -> None:
    with EnvironmentContext():
        stage = get_stage()
        
        stage.altitude_units = "m"
        assert stage.altitude_units == "m"
        
        stage.distance_units = "km"
        assert stage.distance_units == "km"
        
        with pytest.raises(UpstageError, match="can only be set once"):
            stage.altitude_units = "ft"
        
        stage.time_unit = "s"
        assert stage.time_unit == "s"


def test_stage_set_then_read_multiple_times() -> None:
    with EnvironmentContext():
        stage = get_stage()
        
        stage.altitude_units = "yards"
        assert stage.altitude_units == "yards"
        assert stage.altitude_units == "yards"
        assert stage.altitude_units == "yards"


def test_environment_context_with_stage_instance() -> None:
    rng = Random(42)
    stage = Stage(
        random=rng,
        altitude_units="meters",
        distance_units="km",
        time_unit="min",
    )
    
    with EnvironmentContext(stage=stage):
        retrieved_stage = get_stage()
        assert retrieved_stage is stage
        assert retrieved_stage.altitude_units == "meters"
        assert retrieved_stage.distance_units == "km"
        assert retrieved_stage.time_unit == "min"
        assert retrieved_stage.random is rng


def test_environment_context_with_stage_instance_ignores_random_seed() -> None:
    rng = Random(100)
    stage = Stage(
        random=rng,
        altitude_units="feet",
    )
    
    with EnvironmentContext(random_seed=999, stage=stage):
        retrieved_stage = get_stage()
        assert retrieved_stage is stage
        assert retrieved_stage.random is rng
