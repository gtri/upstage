# Copyright (C) 2025 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.


from upstage_des.base import EnvironmentContext
from upstage_des.events import Get, Put
from upstage_des.resources.monitoring import (
    SelfMonitoringContainer,
)
from upstage_des.type_help import SIMPY_GEN


def test_monitoring_container_get() -> None:
    with EnvironmentContext() as env:
        smc = SelfMonitoringContainer(env, init=5)

        data: dict[str, float] = {}

        def _proc_one() -> SIMPY_GEN:
            yield Get(smc, 10.0).as_event()
            data["one"] = env.now

        def _proc_two() -> SIMPY_GEN:
            yield env.timeout(1.0)
            yield Get(smc, 3.0).as_event()
            data["two"] = env.now

        def _proc_three() -> SIMPY_GEN:
            yield env.timeout(2.0)
            yield Put(smc, 10.0).as_event()

        env.process(_proc_one())
        env.process(_proc_two())
        env.process(_proc_three())

        env.run()

        assert data.get("two", 0.0) == 1.0
        assert data.get("one", 0.0) == 2.0
        assert smc.level == 2


if __name__ == "__main__":
    test_monitoring_container_get()
