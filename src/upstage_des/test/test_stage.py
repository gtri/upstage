# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest

from upstage_des.api import (
    EnvironmentContext,
    UpstageBase,
    UpstageError,
    add_stage_variable,
    get_stage,
    get_stage_variable,
)
from upstage_des.base import clear_top_context, create_top_context


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


def test_contextless_stage() -> None:
    ctx = create_top_context()
    add_stage_variable("example", 1.234)

    assert get_stage_variable("example") == 1.234

    stage = get_stage()
    assert stage.example == 1.234

    # dropping into a new context ignores the above
    with EnvironmentContext():
        add_stage_variable("example", 8.675)
        assert get_stage_variable("example") == 8.675

    assert get_stage_variable("example") == 1.234

    clear_top_context(ctx)

    with pytest.raises(ValueError, match="Stage should have been set."):
        get_stage_variable("example")


if __name__ == "__main__":
    test_contextless_stage()
