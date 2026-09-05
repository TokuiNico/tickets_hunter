"""refresh_datetime parsing in the bot entry point (nodriver_tixcraft.py)."""

import sys
from datetime import date, datetime

import pytest

# On Windows the entry point re-wraps stdout/stderr as UTF-8 at import time;
# restore pytest's capture streams afterwards so output capture keeps working.
_streams = (sys.stdout, sys.stderr)
import nodriver_tixcraft as bot  # noqa: E402

sys.stdout, sys.stderr = _streams


@pytest.mark.parametrize("value", ["", "   ", None])
def test_blank_disables_gate(value):
    assert bot.parse_refresh_datetime(value) is None


def test_full_datetime():
    assert bot.parse_refresh_datetime("2026/09/05 12:30:00") == datetime(2026, 9, 5, 12, 30, 0)
    assert bot.parse_refresh_datetime("  2026/09/05 12:30:00  ") == datetime(2026, 9, 5, 12, 30, 0)


def test_time_only_is_today():
    parsed = bot.parse_refresh_datetime("12:30:00")
    assert parsed.date() == date.today()
    assert (parsed.hour, parsed.minute, parsed.second) == (12, 30, 0)


@pytest.mark.parametrize("value", ["2026-09-05 12:30:00", "12:30", "25:00:00", "tomorrow", "2026/13/01 00:00:00"])
def test_invalid_formats_return_none(value):
    assert bot.parse_refresh_datetime(value) is None
