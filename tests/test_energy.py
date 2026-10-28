"""Regression tests for energy units, midnight, restart and outages."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.renon_flex.energy import DailyEnergy

ROME = ZoneInfo("Europe/Rome")


def test_one_kw_for_one_hour_is_one_kwh():
    energy = DailyEnergy()
    start = datetime(2026, 10, 28, 12, tzinfo=ROME)
    for seconds in range(0, 3601, 10):
        result = energy.update(1000, start + timedelta(seconds=seconds), seconds)
    assert result == 1.0


def test_midnight_only_counts_current_day():
    energy = DailyEnergy()
    start = datetime(2026, 10, 28, 23, 59, 55, tzinfo=ROME)
    energy.update(3600, start, 0)
    assert energy.update(3600, start + timedelta(seconds=10), 10) == 0.005
    assert energy.day == "2026-10-29"


@pytest.mark.parametrize("failed", [False, True])
def test_outages_are_not_counted(failed):
    energy = DailyEnergy()
    start = datetime(2026, 10, 28, 12, tzinfo=ROME)
    energy.update(3600, start, 0)
    if failed:
        energy.reset_sample()
    elapsed = 20 if failed else 120
    assert energy.update(3600, start + timedelta(seconds=elapsed), elapsed) == 0


def test_restart_and_negative_power():
    energy = DailyEnergy(day="2026-10-28", kwh=2.5)
    start = datetime(2026, 10, 28, 12, tzinfo=ROME)
    assert energy.update(-1000, start, 1000) == 2.5
    assert energy.update(1000, start + timedelta(seconds=10), 1010) == 2.5


def test_dst_fallback_uses_elapsed_time():
    energy = DailyEnergy()
    first = datetime(2026, 10, 25, 2, 59, 55, tzinfo=ROME)
    second = datetime(2026, 10, 25, 2, 0, 5, tzinfo=ROME, fold=1)
    energy.update(3600, first, 0)
    assert energy.update(3600, second, 10) == 0.01
