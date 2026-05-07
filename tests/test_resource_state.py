# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test resource states."""

import pytest
from upstage_des.api import Actor, ResourceState, EnvironmentContext, UpstageError
from simpy import Store, Container

from upstage_des.base import SIMPY_GEN


def test_resource_state_valid_types() -> None:
    class Holder(Actor):
        res: Store = ResourceState(default=Store, valid_types=Store).create()

    with EnvironmentContext():
        h = Holder(
            name="example",
        )
        h.update_resource("res", kind=Store)

        with pytest.raises(UpstageError, match="not of type"):
            h = Holder(
                name="example",
            )
            h.update_resource("res", kind=Container)

        with pytest.raises(UpstageError):
            class _(Actor):
                res: Store = ResourceState(valid_types=(1,))  # type: ignore [arg-type, assignment]

        with pytest.raises(UpstageError):
            class _(Actor):  # type: ignore [no-redef]
                res: Store = ResourceState(valid_types=(Actor,))  # type: ignore [assignment]


def test_resource_state_set_protection() -> None:
    class Holder(Actor):
        res: Store = ResourceState(default=Store, valid_types=(Store)).create()

    with EnvironmentContext():
        h = Holder(
            name="example",
        )
        with pytest.raises(UpstageError, match=".+It cannot be changed once set.+"):
            h.res = 1.0 # type: ignore[assignment]


def test_resource_state_no_default_init() -> None:
    class Holder(Actor):
        res: Store = ResourceState(default=Store, default_kwargs={"capacity": 12}).create()

    with EnvironmentContext():
        h = Holder(
            name="example",
        )
        assert isinstance(h.res, Store)
        assert h.res.capacity == 12


def test_resource_state_default_init() -> None:
    class Holder(Actor):
        res: Store = ResourceState(default=Store).create()
        res2: Container = ResourceState(
            default=Container, default_kwargs={"capacity": 11, "init": 5}
        ).create()

    class HolderBad(Actor):
        res: Store = ResourceState(default=Store).create()
        res2: Container = ResourceState(default=Container, default_kwargs={"capa": 11, "init": 5}).create()

    with EnvironmentContext():
        h = Holder(name="Example")
        assert isinstance(h.res, Store)
        assert h.res2.capacity == 11
        assert h.res2.level == 5

        h = Holder(name="Example")
        h.update_resource("res",capacity=10)
        h.update_resource("res2", capacity=12)
        assert isinstance(h.res, Store)
        assert h.res.capacity == 10
        assert h.res2.capacity == 12
        assert h.res2.level == 5

        # If you aren't type checking, you can do this:
        h = Holder(
            name="Example",
            res={"capacity": 11}, # type: ignore[arg-type]
            res2={"capacity": 13, "init": 6}, # type: ignore[arg-type]
        )
        assert isinstance(h.res, Store)
        assert h.res.capacity == 11
        assert h.res2.capacity == 13
        assert h.res2.level == 6

        with pytest.raises(UpstageError):
            HolderBad(name="Bad one")


def test_resource_state_kind_init() -> None:
    # This kind of initialization won't work with type checking, but it's
    # feasible.
    class Holder(Actor):
        res: Store = ResourceState().create()

    with EnvironmentContext():
        h = Holder(name="Example", res={"kind": Store, "capacity": 10}) # type: ignore[arg-type]
        assert isinstance(h.res, Store)
        assert h.res.capacity == 10

        h = Holder(name="Example", res={"kind": Container, "capacity": 100, "init": 50}) # type: ignore[arg-type]
        assert isinstance(h.res, Container)
        assert h.res.capacity == 100
        assert h.res.level == 50

        test_resources = [Store, Container]
        for the_class in test_resources:
            h = Holder(name="Example", res={"kind": the_class, "capacity": 99})
            assert isinstance(h.res, the_class)
            assert h.res.capacity == 99


def test_resource_state_simpy_store_running() -> None:
    class Holder(Actor):
        res: Store = ResourceState().create()

    with EnvironmentContext() as env:
        h = Holder(name="Example", res={"kind": Store, "capacity": 10})# type: ignore[arg-type]

        def put_process(entity: Holder) -> SIMPY_GEN:
            for i in range(11):
                yield env.timeout(1.0)
                yield entity.res.put(f"Item {i}")
            return "Done"

        def get_process(entity: Holder) -> SIMPY_GEN:
            res = yield entity.res.get()
            return res

        proc_1 = env.process(put_process(h))
        proc_2 = env.process(get_process(h))
        env.run()
        assert proc_2.value == "Item 0"
        assert proc_1.value == "Done"
