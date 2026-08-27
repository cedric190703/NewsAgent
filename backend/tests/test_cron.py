from datetime import datetime, timezone

import pytest

from app.services import cron


def at(day=27, hour=10, minute=0, month=8, year=2026):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "expression,moment,expected",
    [
        ("* * * * *", at(), True),
        ("0 10 * * *", at(minute=0), True),
        ("0 10 * * *", at(minute=1), False),
        ("*/15 * * * *", at(minute=45), True),
        ("*/15 * * * *", at(minute=46), False),
        ("5,10 * * * *", at(minute=10), True),
        ("0 9-17 * * *", at(hour=13), True),
        ("0 9-17 * * *", at(hour=18), False),
        ("0 0 1 * *", at(day=1, hour=0), True),
        ("0 0 1 * *", at(day=2, hour=0), False),
        # 2026-08-27 is a Thursday.
        ("0 10 * * thu", at(), True),
        ("0 10 * * mon", at(), False),
        ("0 10 * * mon-fri", at(), True),
        ("0 10 * * sat,sun", at(), False),
        # Sunday is both 0 and 7. 2026-08-30 is a Sunday.
        ("0 10 * * 7", at(day=30), True),
        ("0 10 * * 0", at(day=30), True),
    ],
)
def test_matches(expression, moment, expected):
    assert cron.parse(expression).matches(moment) is expected


@pytest.mark.parametrize(
    "alias,moment",
    [
        ("@hourly", at(minute=0)),
        ("@daily", at(hour=0, minute=0)),
        ("@midnight", at(hour=0, minute=0)),
        ("@monthly", at(day=1, hour=0, minute=0)),
    ],
)
def test_aliases(alias, moment):
    assert cron.parse(alias).matches(moment)


def test_either_day_field_may_match_when_both_are_restricted():
    """Vixie cron ORs day-of-month with day-of-week; people depend on that."""

    schedule = cron.parse("0 0 1 * mon")
    assert schedule.matches(at(day=1, hour=0, minute=0))  # 1st, a Saturday
    assert schedule.matches(at(day=31, hour=0, minute=0))  # a Monday


@pytest.mark.parametrize(
    "expression",
    ["", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *", "5-1 * * * *",
     "*/0 * * * *", "abc * * * *", "0 0 0 * *"],
)
def test_invalid_expressions_are_rejected(expression):
    with pytest.raises(cron.CronError):
        cron.parse(expression)
    assert cron.is_valid(expression) is False


def test_next_after_skips_the_current_minute():
    schedule = cron.parse("0 9 * * *")
    assert schedule.next_after(at(hour=9, minute=0)) == at(day=28, hour=9)


def test_describe_next_returns_iso_or_none():
    assert cron.describe_next("0 9 * * *", at()) == "2026-08-28T09:00:00+00:00"
    assert cron.describe_next("garbage") is None
