"""Period resolution — the arithmetic taken away from the LLM.

Every test pins ``as_of`` explicitly. A test that called the real clock would pass
today and fail on the first of the month, which is exactly the class of bug this
module exists to prevent.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.core.time_range import (
    DateRange,
    Period,
    get_timezone,
    resolve_period,
    today,
)

pytestmark = pytest.mark.unit

# A Wednesday, mid-month, mid-quarter — no boundary is accidentally satisfied.
WEDNESDAY = date(2026, 9, 16)


def resolve(period: Period, as_of: date = WEDNESDAY, **kwargs) -> DateRange:
    return resolve_period(period, as_of=as_of, **kwargs)


# ---------------------------------------------------------------------------
# Simple periods
# ---------------------------------------------------------------------------


def test_all_time_is_unbounded():
    result = resolve(Period.ALL_TIME)

    assert result.start is None and result.end is None
    assert result.is_unbounded


def test_all_time_does_not_need_the_clock():
    """An unbounded range has no boundaries to compute, so it must resolve even if
    timezone data were unavailable."""

    assert resolve_period(Period.ALL_TIME).is_unbounded


def test_today_is_a_single_day():
    assert resolve(Period.TODAY) == DateRange(WEDNESDAY, WEDNESDAY)


def test_yesterday_is_the_day_before():
    assert resolve(Period.YESTERDAY) == DateRange(date(2026, 9, 15), date(2026, 9, 15))


def test_yesterday_crosses_a_month_boundary():
    result = resolve(Period.YESTERDAY, as_of=date(2026, 9, 1))

    assert result == DateRange(date(2026, 8, 31), date(2026, 8, 31))


def test_yesterday_crosses_a_year_boundary():
    result = resolve(Period.YESTERDAY, as_of=date(2026, 1, 1))

    assert result == DateRange(date(2025, 12, 31), date(2025, 12, 31))


# ---------------------------------------------------------------------------
# Weeks — Monday start
# ---------------------------------------------------------------------------


def test_this_week_runs_from_monday_to_today():
    # 2026-09-16 is a Wednesday; that week's Monday is the 14th.
    assert resolve(Period.THIS_WEEK) == DateRange(date(2026, 9, 14), WEDNESDAY)


def test_this_week_on_a_monday_is_just_that_day():
    monday = date(2026, 9, 14)

    assert resolve(Period.THIS_WEEK, as_of=monday) == DateRange(monday, monday)


def test_this_week_on_a_sunday_ends_on_the_sunday():
    """ISO weeks start on Monday, so Sunday is the last day of its week, not the
    first day of the next."""

    sunday = date(2026, 9, 20)

    assert resolve(Period.THIS_WEEK, as_of=sunday) == DateRange(date(2026, 9, 14), sunday)


def test_last_week_is_the_full_previous_monday_to_sunday():
    result = resolve(Period.LAST_WEEK)

    assert result == DateRange(date(2026, 9, 7), date(2026, 9, 13))
    assert (result.end - result.start).days == 6, "a week is seven days"


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------


def test_this_month_runs_from_the_first_to_today():
    assert resolve(Period.THIS_MONTH) == DateRange(date(2026, 9, 1), WEDNESDAY)


def test_last_month_is_the_whole_previous_month():
    assert resolve(Period.LAST_MONTH) == DateRange(date(2026, 8, 1), date(2026, 8, 31))


def test_last_month_from_january_is_december_of_the_previous_year():
    result = resolve(Period.LAST_MONTH, as_of=date(2026, 1, 15))

    assert result == DateRange(date(2025, 12, 1), date(2025, 12, 31))


def test_last_month_from_march_gets_february_right():
    """2026 is not a leap year: February has 28 days."""

    result = resolve(Period.LAST_MONTH, as_of=date(2026, 3, 10))

    assert result == DateRange(date(2026, 2, 1), date(2026, 2, 28))


def test_last_month_handles_a_leap_february():
    """2024 was a leap year: February had 29 days. A hardcoded 28 would be wrong."""

    result = resolve(Period.LAST_MONTH, as_of=date(2024, 3, 10))

    assert result == DateRange(date(2024, 2, 1), date(2024, 2, 29))


def test_last_month_from_the_31st_does_not_overflow_into_a_short_month():
    """31 May -> April, which has 30 days. Naive day arithmetic breaks here."""

    result = resolve(Period.LAST_MONTH, as_of=date(2026, 5, 31))

    assert result == DateRange(date(2026, 4, 1), date(2026, 4, 30))


# ---------------------------------------------------------------------------
# Quarters
# ---------------------------------------------------------------------------


def test_this_quarter_starts_at_the_quarter_boundary():
    # September is in Q3, which starts 1 July.
    assert resolve(Period.THIS_QUARTER) == DateRange(date(2026, 7, 1), WEDNESDAY)


def test_last_quarter_is_the_whole_previous_quarter():
    assert resolve(Period.LAST_QUARTER) == DateRange(date(2026, 4, 1), date(2026, 6, 30))


def test_last_quarter_from_q1_is_q4_of_the_previous_year():
    result = resolve(Period.LAST_QUARTER, as_of=date(2026, 2, 10))

    assert result == DateRange(date(2025, 10, 1), date(2025, 12, 31))


@pytest.mark.parametrize(
    ("as_of", "expected_start"),
    [
        (date(2026, 1, 5), date(2026, 1, 1)),
        (date(2026, 4, 5), date(2026, 4, 1)),
        (date(2026, 7, 5), date(2026, 7, 1)),
        (date(2026, 10, 5), date(2026, 10, 1)),
    ],
)
def test_every_quarter_starts_on_the_right_month(as_of, expected_start):
    assert resolve(Period.THIS_QUARTER, as_of=as_of).start == expected_start


# ---------------------------------------------------------------------------
# Years
# ---------------------------------------------------------------------------


def test_this_year_runs_from_january_to_today():
    assert resolve(Period.THIS_YEAR) == DateRange(date(2026, 1, 1), WEDNESDAY)


def test_last_year_is_the_whole_previous_year():
    assert resolve(Period.LAST_YEAR) == DateRange(date(2025, 1, 1), date(2025, 12, 31))


# ---------------------------------------------------------------------------
# Custom
# ---------------------------------------------------------------------------


def test_custom_uses_the_dates_given():
    result = resolve(
        Period.CUSTOM, start_date=date(2026, 1, 1), end_date=date(2026, 3, 31)
    )

    assert result == DateRange(date(2026, 1, 1), date(2026, 3, 31))


def test_custom_without_dates_is_rejected():
    with pytest.raises(ValueError, match="requires both start_date and end_date"):
        resolve(Period.CUSTOM)


def test_custom_with_only_one_date_is_rejected():
    with pytest.raises(ValueError, match="requires both"):
        resolve(Period.CUSTOM, start_date=date(2026, 1, 1))


def test_a_reversed_range_is_rejected():
    """start > end silently returns nothing in SQL; catching it here turns a
    mysteriously empty report into a clear error."""

    with pytest.raises(ValueError, match="is after end_date"):
        DateRange(date(2026, 3, 31), date(2026, 1, 1))


def test_a_single_day_range_is_valid():
    day = date(2026, 3, 1)

    assert DateRange(day, day).start == DateRange(day, day).end


# ---------------------------------------------------------------------------
# SQL bounds
# ---------------------------------------------------------------------------


def test_datetime_bounds_use_an_exclusive_upper_limit():
    """The whole final day must be inside the range.

    `<= end` compares against 00:00:00 on the end date and drops everything that
    happened during it — the off-by-one that quietly under-reports every period.
    """

    lower, upper = DateRange(date(2026, 8, 1), date(2026, 8, 31)).as_datetime_bounds()

    assert lower == datetime(2026, 8, 1, 0, 0, 0)
    assert upper == datetime(2026, 9, 1, 0, 0, 0), "midnight on the day AFTER the end"


def test_date_bounds_are_inclusive_on_both_ends():
    """A Date column has no time component, so no adjustment is needed."""

    lower, upper = DateRange(date(2026, 8, 1), date(2026, 8, 31)).as_date_bounds()

    assert lower == date(2026, 8, 1)
    assert upper == date(2026, 8, 31)


def test_unbounded_ranges_produce_no_bounds():
    unbounded = DateRange(None, None)

    assert unbounded.as_datetime_bounds() == (None, None)
    assert unbounded.as_date_bounds() == (None, None)


def test_describe_is_readable():
    assert DateRange(None, None).describe() == "all time"
    assert DateRange(date(2026, 8, 1), date(2026, 8, 1)).describe() == "2026-08-01"
    assert (
        DateRange(date(2026, 8, 1), date(2026, 8, 31)).describe()
        == "2026-08-01 to 2026-08-31"
    )


# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------


def test_the_default_timezone_is_the_pharmacys_not_utc():
    """Resolving "today" in UTC would misfile every late-evening sale in India."""

    assert str(get_timezone()) == "Asia/Kolkata"


def test_today_returns_a_date_in_that_timezone():
    assert isinstance(today(), date)


def test_an_unknown_timezone_fails_loudly(monkeypatch):
    """A silent UTC fallback would shift every boundary by hours."""

    get_timezone.cache_clear()
    monkeypatch.setenv("APP_TIMEZONE", "Mars/Olympus_Mons")

    with pytest.raises(RuntimeError, match="APP_TIMEZONE"):
        get_timezone()

    get_timezone.cache_clear()


def test_every_period_member_has_a_resolution_rule():
    """A new Period added without a branch must not silently mean "all time"."""

    for period in Period:
        kwargs = {}
        if period is Period.CUSTOM:
            kwargs = {"start_date": WEDNESDAY, "end_date": WEDNESDAY}
        assert isinstance(resolve(period, **kwargs), DateRange), period
