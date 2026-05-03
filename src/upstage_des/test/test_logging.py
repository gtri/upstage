# Copyright (C) 2025 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import logging

import pytest

import upstage_des.api as UP


class Bot(UP.Actor):
    """Minimal actor for logging tests."""


def test_logs_property_returns_list() -> None:
    """`actor.logs` returns the in-memory list."""
    with UP.EnvironmentContext():
        bot = Bot(name="b")
        assert bot.logs == []
        bot.log("hello")
        assert len(bot.logs) == 1
        assert "hello" in bot.logs[0][1]


def test_get_log_still_works() -> None:
    """`actor.get_log()` continues to return the in-memory list."""
    with UP.EnvironmentContext():
        bot = Bot(name="b")
        bot.log("one")
        assert bot.get_log() is bot.logs
        assert len(bot.get_log()) == 1


def test_log_no_args_is_deprecated() -> None:
    """Calling `log()` with no args warns and still returns the list."""
    with UP.EnvironmentContext():
        bot = Bot(name="b")
        bot.log("hi")
        with pytest.warns(DeprecationWarning, match="actor.logs or actor.get_log"):
            result = bot.log()
        assert result is not None
        assert len(result) == 1


def test_debug_log_list_still_populates() -> None:
    """Back-compat: the _debug_log list still receives entries."""
    with UP.EnvironmentContext():
        bot = Bot(name="b")
        bot.log("first")
        bot.log("second")
        assert len(bot._debug_log) == 2
        assert "first" in bot._debug_log[0][1]
        assert "second" in bot._debug_log[1][1]


def test_debug_log_false_suppresses_list() -> None:
    """`debug_log=False` stops the in-memory list from growing."""
    with UP.EnvironmentContext():
        bot = Bot(name="b", debug_log=False)
        bot.log("silent")
        assert bot._debug_log == []


def test_printf_style_formatting() -> None:
    """printf-style args are interpolated when a sink wants the record."""
    with UP.EnvironmentContext():
        bot = Bot(name="b")
        bot.log("count=%d name=%s", 3, "foo")
        entry = bot._debug_log[-1][1]
        assert "count=3 name=foo" in entry


def test_logging_module_receives_records(caplog: pytest.LogCaptureFixture) -> None:
    """Records reach the `upstage_des.actor.<name>` logger."""
    with caplog.at_level(logging.INFO, logger="upstage_des"):
        with UP.EnvironmentContext():
            bot = Bot(name="alice")
            bot.log("hi %s", "world")
    records = [r for r in caplog.records if r.name.startswith("upstage_des.actor.alice")]
    assert len(records) == 1
    assert records[0].getMessage() == "hi world"
    assert records[0].levelno == logging.INFO


def test_level_argument(caplog: pytest.LogCaptureFixture) -> None:
    """Custom `level=` routes to the matching logging level."""
    with caplog.at_level(logging.DEBUG, logger="upstage_des"):
        with UP.EnvironmentContext():
            bot = Bot(name="b")
            bot.log("verbose", level=logging.DEBUG)
            bot.log("normal")
            bot.log("alarm", level=logging.WARNING)
    levels = {r.getMessage(): r.levelno for r in caplog.records if r.name.startswith("upstage_des")}
    assert levels["verbose"] == logging.DEBUG
    assert levels["normal"] == logging.INFO
    assert levels["alarm"] == logging.WARNING


def test_level_filter_short_circuits_logger() -> None:
    """Records below the logger's level are dropped before emission."""
    seen: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record)

    handler = Capture(level=logging.DEBUG)
    root = logging.getLogger("upstage_des")
    prior = root.level
    root.addHandler(handler)
    try:
        root.setLevel(logging.WARNING)
        with UP.EnvironmentContext():
            bot = Bot(name="quiet", debug_log=False)
            bot.log("ignored")  # INFO default, below WARNING
        assert not seen
    finally:
        root.removeHandler(handler)
        root.setLevel(prior)


def test_both_sinks_disabled_skips_formatting() -> None:
    """When no sink wants the record, printf args are not interpolated."""

    class Boom:
        def __str__(self) -> str:
            raise AssertionError("formatting should have been short-circuited")

    logger = logging.getLogger("upstage_des")
    prior = logger.level
    try:
        logger.setLevel(logging.CRITICAL)  # logger doesn't want INFO
        with UP.EnvironmentContext():
            bot = Bot(name="silent", debug_log=False)  # list doesn't want INFO either
            # If formatting runs, Boom.__str__ will assert — proving the short-circuit.
            bot.log("this should not format: %s", Boom())
    finally:
        logger.setLevel(prior)


def test_rehearsal_logger_is_child(caplog: pytest.LogCaptureFixture) -> None:
    """Rehearsal clones log under the `.rehearsal` child so users can filter."""
    with caplog.at_level(logging.INFO, logger="upstage_des"):
        with UP.EnvironmentContext():
            bot = Bot(name="sol")
            clone = bot.clone()
            clone.log("from the rehearsal")
    rehearsal_records = [
        r
        for r in caplog.records
        if ".rehearsal" in r.name and r.getMessage() == "from the rehearsal"
    ]
    assert rehearsal_records, "expected a record on the .rehearsal logger"


def test_package_logger_has_null_handler() -> None:
    """Importing the package installs a NullHandler so library use is silent."""
    root = logging.getLogger("upstage_des")
    assert any(isinstance(h, logging.NullHandler) for h in root.handlers)
