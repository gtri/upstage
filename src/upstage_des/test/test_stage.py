# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest

from upstage_des.api import (
    EnvironmentContext,
    UpstageBase,
    UpstageError,
    add_stage_variable,
)


class Stager(UpstageBase): ...


def test_stage() -> None:
    with EnvironmentContext():
        source = Stager()
        # Complain when accessing an unset attribute
        with pytest.raises(AttributeError):
            source.stage.stage_model

        # setting with the method
        add_stage_variable("stage_model", 1)
        assert source.stage.stage_model == 1

        # Setting without the method
        add_stage_variable("altitude_units", 2)
        assert source.stage.altitude_units == 2

        # Setting should yell after a set
        with pytest.raises(UpstageError):
            add_stage_variable("altitude_units", 3)

    # After the context, it should not exists
    with pytest.raises(UpstageError):
        source.stage
