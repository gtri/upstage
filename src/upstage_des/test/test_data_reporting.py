"""Test the data recording/reporting capabilities."""

from collections import Counter
from dataclasses import dataclass

import simpy as SIM

import upstage_des.api as UP
from upstage_des.data_utils import (
    create_location_table,
    create_table,
    get_recorded_data,
    record_data,
)
from upstage_des.type_help import SIMPY_GEN


@dataclass
class Information:
    value_1: int
    value_2: float


class Cashier(UP.Actor):
    items_scanned = UP.State[int](recording=True)
    other = UP.State[float]()
    cue = UP.State[UP.SelfMonitoringStore]()
    cue2 = UP.ResourceState[UP.SelfMonitoringContainer](default=UP.SelfMonitoringContainer)
    time_working = UP.LinearChangingState(default=0.0, recording=True, record_duplicates=True)
    info = UP.State[Information](recording=True)


class Cart(UP.Actor):
    location = UP.CartesianLocationChangingState(recording=True)
    location_two = UP.CartesianLocationChangingState(recording=True)
    holding = UP.State[float](default=0.0, recording=True)
    some_data = UP.State[dict[str, float]](recording=True)


def test_data_reporting() -> None:
    with UP.EnvironmentContext() as env:
        t = UP.Task()
        cash = Cashier(
            name="Ertha",
            other=0.0,
            items_scanned=0,
            cue=UP.SelfMonitoringStore(env),
            info=Information(0, 0),
        )

        cash2 = Cashier(
            name="Bertha",
            other=0.0,
            items_scanned=0,
            cue=UP.SelfMonitoringStore(env),
            info=Information(1, 1),
        )
        store = UP.SelfMonitoringFilterStore(env, name="Store Test")
        cart = Cart(
            name="Wobbly Wheel",
            location=UP.CartesianLocation(1.0, 1.0),
            location_two=UP.CartesianLocation(1.0, 1.0),
            some_data={"exam": 2.0},
        )

        for c in [cash, cash2]:
            c.items_scanned += 1
            c.cue.put("A")
            c.cue2.put(10)
            c.time_working = 0.0
        cash.other = 3.0

        cart.activate_location_state(
            state="location",
            speed=2.0,
            waypoints=[UP.CartesianLocation(7.0, 6.0)],
            task=t,
        )
        cart.activate_location_state(
            state="location_two",
            speed=2.0,
            waypoints=[UP.CartesianLocation(-7.0, -6.0)],
            task=t,
        )

        env.run(until=0.1)
        for c in [cash, cash2]:
            c.activate_linear_state(
                state="time_working",
                rate=1.0,
                task=t,
            )

        env.run(until=1)
        cart.location
        cart.location_two
        cash.items_scanned += 2
        store.put("XYZ")
        cash.info.value_1 = 3
        cash.record_state("info")
        cash2.info.value_2 = 4.3
        cash2.record_state("info")

        for c in [cash, cash2]:
            c.cue.put("B")
            c.cue2.put(3)
            c.time_working

        env.run(until=2)
        cart.location
        cash.items_scanned += 1
        env.run(until=3)
        cart.location
        cart.location_two
        cart.some_data["exam"] = 4.0
        cart.record_state("some_data")

        cart.deactivate_state(state="location", task=t)
        cart.deactivate_state(state="location_two", task=t)

        cash2.deactivate_state(state="time_working", task=t)

        for c in [cash, cash2]:
            c.cue.get()
            c.cue2.get(2)
            c.time_working

        cash.items_scanned = -1
        env.run(until=3.3)
        cart.location
        cart.location_two = UP.CartesianLocation(-1.0, -1.0)
        cart.some_data["new"] = 123.45
        cart.record_state("some_data")
        store.put("ABC")
        env.run()
        cart.location
        cart.location_two
        for c in [cash, cash2]:
            c.time_working

        state_table, cols = create_table()
        all_state_table, all_cols = create_table(skip_locations=False)
        loc_state_table, loc_cols = create_location_table()
        new_table, _ = create_table(skip_locations=True, save_static=True)
        orig_table, _ = create_table(skip_locations=True, save_static=False)

    ctr = Counter([row[:3] for row in state_table])
    assert ctr[("Ertha", "Cashier", "items_scanned")] == 5
    assert ctr[("Ertha", "Cashier", "cue")] == 4
    assert ctr[("Ertha", "Cashier", "cue2")] == 4
    assert ctr[("Ertha", "Cashier", "time_working")] == 6
    assert ctr[("Bertha", "Cashier", "items_scanned")] == 2
    assert ctr[("Bertha", "Cashier", "cue")] == 4
    assert ctr[("Bertha", "Cashier", "cue2")] == 4
    assert ctr[("Bertha", "Cashier", "time_working")] == 5
    assert ctr[("Store Test", "SelfMonitoringFilterStore", "Resource")] == 3
    assert ctr[("Ertha", "Cashier", "info.value_1")] == 2
    assert ctr[("Ertha", "Cashier", "info.value_2")] == 2
    assert ctr[("Bertha", "Cashier", "info.value_1")] == 2
    assert ctr[("Bertha", "Cashier", "info.value_2")] == 2
    # Test for default values untouched in the sim showing up in the data.
    assert ctr[("Wobbly Wheel", "Cart", "holding")] == 1
    assert ctr[("Wobbly Wheel", "Cart", "some_data.exam")] == 3
    assert ctr[("Wobbly Wheel", "Cart", "some_data.new")] == 1
    row = [r for r in state_table if r[:3] == ("Wobbly Wheel", "Cart", "holding")][0]
    assert row[4] == 0
    assert row[3] == 0.0
    # Continuing as before
    assert len(state_table) == 50
    assert cols == all_cols
    assert cols == [
        "Entity Name",
        "Entity Type",
        "State Name",
        "Time",
        "Value",
        "Activation Status",
    ]

    ctr = Counter([row[:3] for row in all_state_table])
    assert ctr[("Ertha", "Cashier", "items_scanned")] == 5
    assert ctr[("Ertha", "Cashier", "cue")] == 4
    assert ctr[("Ertha", "Cashier", "cue2")] == 4
    assert ctr[("Ertha", "Cashier", "time_working")] == 6
    assert ctr[("Bertha", "Cashier", "items_scanned")] == 2
    assert ctr[("Bertha", "Cashier", "cue")] == 4
    assert ctr[("Bertha", "Cashier", "cue2")] == 4
    assert ctr[("Bertha", "Cashier", "time_working")] == 5
    assert ctr[("Store Test", "SelfMonitoringFilterStore", "Resource")] == 3
    assert ctr[("Wobbly Wheel", "Cart", "holding")] == 1
    assert ctr[("Wobbly Wheel", "Cart", "location")] == 4
    assert ctr[("Wobbly Wheel", "Cart", "location_two")] == 4
    assert len(all_state_table) == 38 + 8 + 12

    assert loc_cols == [
        "Entity Name",
        "Entity Type",
        "State Name",
        "Time",
        "X",
        "Y",
        "Z",
        "Activation Status",
    ]
    assert len(loc_state_table) == 8
    assert loc_state_table[-1] == (
        "Wobbly Wheel",
        "Cart",
        "location_two",
        3.3,
        -1.0,
        -1.0,
        0.0,
        "inactive",
    )

    match1 = ("Ertha", "Cashier", "other", 0.0, 3.0, "Last Seen")
    assert match1 in new_table
    assert match1 not in all_state_table

    match2 = ("Bertha", "Cashier", "other", 0.0, 0.0, "Last Seen")
    assert match2 in new_table
    assert match2 not in all_state_table

    # Only the two "other" states should show up
    assert len(new_table) - len(orig_table) == 2


def test_store_failure() -> None:
    class Exam(UP.Actor):
        a_store = UP.ResourceState[SIM.Store](default=SIM.Store)

    with UP.EnvironmentContext() as env:
        ex = Exam(name="example")

        def _proc() -> SIMPY_GEN:
            yield ex.a_store.put("a thing")
            yield env.timeout(1.0)
            assert ex.a_store.items == ["a thing"]
            yield ex.a_store.get()

        env.process(_proc())
        env.run()
        assert env.now == 1
        assert ex.a_store.items == []

        data, cols = create_table()
        assert data == []


def test_data_recorder() -> None:
    with UP.EnvironmentContext() as env:
        record_data("First")
        record_data({"ok": "working"})
        env.run(until=3.0)
        record_data(1.23)
        env.run(until=4.0)
        info = Information(1, 2.0)
        record_data(info, copy=True)
        record_data(info, copy=False)
        info.value_1 = 5

        the_data = get_recorded_data()
        assert len(the_data) == 5
        assert the_data[0] == (0.0, "First")
        assert the_data[1] == (0.0, {"ok": "working"})
        assert the_data[2] == (3.0, 1.23)
        assert the_data[3][0] == 4.0
        info_stored = the_data[3][1]
        assert getattr(info_stored, "value_1", None) == 1
        assert getattr(info_stored, "value_2", None) == 2.0
        assert id(info_stored) != id(info)

        assert the_data[4][0] == 4.0
        info_stored_2 = the_data[4][1]
        assert getattr(info_stored_2, "value_1", None) == 5
        assert getattr(info_stored_2, "value_2", None) == 2.0
        assert id(info_stored_2) == id(info)


if __name__ == "__main__":
    test_store_failure()
