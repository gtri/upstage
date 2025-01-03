"""Test the data recording/reporting capabilities."""

from collections import Counter

import upstage_des.api as UP
from upstage_des.data_utils import create_location_table, create_table


class Cashier(UP.Actor):
    items_scanned = UP.State[int](recording=True)
    other = UP.State[float]()
    cue = UP.State[UP.SelfMonitoringStore]()
    cue2 = UP.ResourceState[UP.SelfMonitoringContainer](default=UP.SelfMonitoringContainer)
    time_working = UP.LinearChangingState(default=0.0, recording=True, record_duplicates=True)


class Cart(UP.Actor):
    location = UP.CartesianLocationChangingState(recording=True)
    location_two = UP.CartesianLocationChangingState(recording=True)
    holding = UP.State[float](default=0.0, recording=True)


def test_data_reporting() -> None:
    with UP.EnvironmentContext() as env:
        t = UP.Task()
        cash = Cashier(
            name="Ertha",
            other=0.0,
            items_scanned=0,
            cue=UP.SelfMonitoringStore(env),
        )

        cash2 = Cashier(
            name="Bertha",
            other=0.0,
            items_scanned=0,
            cue=UP.SelfMonitoringStore(env),
        )
        store = UP.SelfMonitoringFilterStore(env, name="Store Test")
        cart = Cart(
            name="Wobbly Wheel",
            location=UP.CartesianLocation(1.0, 1.0),
            location_two=UP.CartesianLocation(1.0, 1.0),
        )

        for c in [cash, cash2]:
            c.items_scanned += 1
            c.cue.put("A")
            c.cue2.put(10)
            c.other = 3.0
            c.time_working = 0.0

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
        store.put("ABC")
        env.run()
        cart.location
        cart.location_two
        for c in [cash, cash2]:
            c.time_working

        state_table, cols = create_table()
        all_state_table, all_cols = create_table(skip_locations=False)
        loc_state_table, loc_cols = create_location_table()

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
    # Test for default values untouched in the sim showing up in the data.
    assert ctr[("Wobbly Wheel", "Cart", "holding")] == 1
    row = [r for r in state_table if r[:3] == ("Wobbly Wheel", "Cart", "holding")][0]
    assert row[4] == 0
    assert row[3] == 0.0
    # Continuing as before
    assert len(state_table) == 38
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
    assert len(all_state_table) == 38 + 8

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
