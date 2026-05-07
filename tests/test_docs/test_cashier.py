from typing import Literal

import pytest

import upstage_des.api as UP
import simpy as SIM

class Cashier(UP.Actor):
    scan_speed_per_item: float
    break_time: float
    work_until_break: float
    items_scanned: int = UP.State(default=0, recording=True).create()


class CheckoutLane(UP.Actor):
    customer_queue: SIM.Store = UP.ResourceState(default=SIM.Store).create()


class Customer(UP.Actor):
    number_of_items: int
    events: str = UP.State(default="Creation", recording=True).create()
    payment_method: Literal["cash", "card"] = UP.State(
        default="card",
        type_check_each=True,
    ).create()


def test_cashier() -> None:

    with UP.EnvironmentContext() as env:
        cashier = Cashier(
            name="Theoden",
            scan_speed_per_item=1.0,
            break_time=15.0,
            work_until_break=120.0,
        )

        c = Customer(
            name="Billy",
            number_of_items=23,
            payment_method="cash",
        )
        line = CheckoutLane(
            name="Aise 1",
        )
        with pytest.raises(TypeError):
            c.payment_method = "bitcoin" # type: ignore[assignment]
