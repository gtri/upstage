# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from collections import deque
import logging

import pytest

import upstage_des.api as UP


class Bot(UP.Actor):
    """Minimal actor for logging tests."""


def test_logs_property_returns_list() -> None:
    """`actor.get_log()` returns the in-memory list."""
    with UP.EnvironmentContext():
        bot = Bot(name="b")
        assert bot.get_log() == deque()
        bot.write_to_log("hello")
        assert len(bot.get_log()) == 1
        assert "hello" in bot.get_log()[0][1]


def test_get_log_still_works() -> None:
    """`actor.get_log()` continues to return the in-memory list."""
    with UP.EnvironmentContext():
        bot = Bot(name="b")
        bot.write_to_log("one")
        assert bot.get_log() is bot.get_log()
        assert len(bot.get_log()) == 1


def test_log_list_still_populates() -> None:
    """Back-compat: the _log list still receives entries."""
    with UP.EnvironmentContext():
        bot = Bot(name="b")
        bot.write_to_log("first")
        bot.write_to_log("second")
        assert len(bot._log) == 2
        assert "first" in bot._log[0][1]
        assert "second" in bot._log[1][1]


def test_log_false_suppresses_list() -> None:
    """`debug_logging=False` stops the in-memory list from growing."""
    with UP.EnvironmentContext():
        bot = Bot(name="b", debug_logging=False)
        bot.write_to_log("silent")
        assert bot._log == deque()


def test_logging_module_receives_records(caplog: pytest.LogCaptureFixture) -> None:
    """Records reach the `upstage_des.actor.<name>` logger."""
    with caplog.at_level(logging.INFO, logger="upstage_des"):
        with UP.EnvironmentContext():
            bot = Bot(name="alice")
            bot.write_to_log("hi world")
    records = [r for r in caplog.records if r.name.startswith("upstage_des.actor.alice")]
    assert len(records) == 1
    assert records[0].getMessage() == "hi world"
    assert records[0].levelno == logging.INFO


def test_level_argument(caplog: pytest.LogCaptureFixture) -> None:
    """Custom `level=` routes to the matching logging level."""
    with caplog.at_level(logging.DEBUG, logger="upstage_des"):
        with UP.EnvironmentContext():
            bot = Bot(name="b")
            bot.write_to_log("verbose", level=logging.DEBUG)
            bot.write_to_log("normal")
            bot.write_to_log("alarm", level=logging.WARNING)
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
            bot = Bot(name="quiet", debug_logging=False)
            bot.write_to_log("ignored")  # INFO default, below WARNING
        assert not seen
    finally:
        root.removeHandler(handler)
        root.setLevel(prior)


def test_package_logger_has_null_handler() -> None:
    """Importing the package installs a NullHandler so library use is silent."""
    root = logging.getLogger("upstage_des")
    assert any(isinstance(h, logging.NullHandler) for h in root.handlers)


def test_printf_style_formatting() -> None:
    """printf-style args are interpolated when a sink wants the record."""
    with UP.EnvironmentContext():
        bot = Bot(name="b")
        bot.write_to_log("count=%d name=%s", 3, "foo")
        entry = bot._log[-1][1]
        assert "count=3 name=foo" in entry
