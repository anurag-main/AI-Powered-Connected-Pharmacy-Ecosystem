"""Deterministic resolution of named periods into concrete date ranges.

WHY THIS EXISTS
---------------
An LLM asked "what were sales last month?" must not work out what "last month"
means. Models get month lengths, week starts and year boundaries wrong, and a wrong
date silently produces a confidently-wrong number. So the model's only job is to name
the period; this module turns that name into two dates, in code, testably.

    "last month"  ->  Period.LAST_MONTH  ->  DateRange(2026-08-01, 2026-08-31)

TIMEZONE
--------
Periods resolve in the pharmacy's local timezone, read from ``APP_TIMEZONE``
(default ``Asia/Kolkata`` — this is an Indian pharmacy). "Today" means today *there*,
not in UTC: a sale rung up at 00:30 IST belongs to that day's takings, and resolving
in UTC would file it under the previous day.

The database stores **naive** timestamps written in the server's own local time, so
comparisons here are naive local datetimes too. This is correct only while the app
server and the database share a timezone. That is true today (both on one machine)
and is the assumption to revisit at deployment — noted in ``docs/business_queries.md``.

BOUNDARIES
----------
A ``DateRange`` is a pair of **inclusive** calendar dates: ``LAST_MONTH`` for a
September "today" is 1–31 August, both endpoints included.

Turning that into a SQL predicate differs by column type, which is why the range
exposes two helpers rather than letting callers improvise:

- ``Date`` columns (``purchases.purchase_date``)  ->  ``col BETWEEN start AND end``
- ``DateTime`` columns (``sales.sold_at``)        ->  ``col >= start 00:00``
                                                      ``col <  end+1day 00:00``

The half-open upper bound on datetimes is the important one. ``col <= end`` would
compare against ``end 00:00:00`` and silently drop everything sold during the last
day of the range — the classic off-by-one-day reporting bug.
"""

from __future__ import annotations

import calendar
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Kolkata"


@lru_cache(maxsize=1)
def get_timezone() -> ZoneInfo:
    """The pharmacy's local timezone, from ``APP_TIMEZONE``.

    Windows ships no system zone database, so ``tzdata`` is a pinned dependency.
    A missing or misspelt zone raises here rather than falling back to UTC: a silent
    fallback would shift every period boundary by hours and produce confidently wrong
    "today" figures, which is far worse than refusing to start.
    """

    name = os.environ.get("APP_TIMEZONE", DEFAULT_TIMEZONE)

    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise RuntimeError(
            f"APP_TIMEZONE={name!r} could not be loaded ({exc}). Set a valid IANA "
            "zone such as 'Asia/Kolkata', and ensure the tzdata package is installed."
        ) from exc


def today() -> date:
    """Today's date in the pharmacy's timezone.

    Every period resolves relative to this. Tests pass an explicit ``as_of`` instead
    of freezing the clock, so no test depends on the day it happens to run.
    """

    return datetime.now(get_timezone()).date()


class Period(StrEnum):
    """The named periods a question may refer to.

    A closed set, because the planner picks from it. An open string would put date
    arithmetic back in the model's hands, which is what this module exists to prevent.
    """

    ALL_TIME = "all_time"
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_QUARTER = "this_quarter"
    LAST_QUARTER = "last_quarter"
    THIS_YEAR = "this_year"
    LAST_YEAR = "last_year"
    CUSTOM = "custom"


@dataclass(frozen=True)
class DateRange:
    """An inclusive span of calendar dates. ``None`` on both ends means all time."""

    start: date | None
    end: date | None

    def __post_init__(self) -> None:
        if self.start and self.end and self.start > self.end:
            raise ValueError(
                f"start_date {self.start} is after end_date {self.end}"
            )

    @property
    def is_unbounded(self) -> bool:
        return self.start is None and self.end is None

    def as_date_bounds(self) -> tuple[date | None, date | None]:
        """For a ``Date`` column: both endpoints inclusive."""

        return self.start, self.end

    def as_datetime_bounds(self) -> tuple[datetime | None, datetime | None]:
        """For a ``DateTime`` column: inclusive lower, **exclusive** upper.

        The upper bound is midnight on the day *after* ``end``, so the whole of the
        final day is included. See the module docstring on why ``<= end`` is a bug.
        """

        lower = datetime.combine(self.start, datetime.min.time()) if self.start else None
        upper = (
            datetime.combine(self.end + timedelta(days=1), datetime.min.time())
            if self.end
            else None
        )
        return lower, upper

    def describe(self) -> str:
        """A short label for logs and for telling the user what was actually measured."""

        if self.is_unbounded:
            return "all time"
        if self.start == self.end:
            return str(self.start)
        return f"{self.start} to {self.end}"


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _month_range(year: int, month: int) -> DateRange:
    """The whole of one month. ``monthrange`` handles February and leap years."""

    last_day = calendar.monthrange(year, month)[1]
    return DateRange(date(year, month, 1), date(year, month, last_day))


def _quarter_of(value: date) -> int:
    return (value.month - 1) // 3 + 1


def _quarter_range(year: int, quarter: int) -> DateRange:
    first_month = 3 * (quarter - 1) + 1
    last_month = first_month + 2
    last_day = calendar.monthrange(year, last_month)[1]
    return DateRange(date(year, first_month, 1), date(year, last_month, last_day))


def resolve_period(
    period: Period,
    *,
    as_of: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> DateRange:
    """Turn a named period into concrete dates.

    ``as_of`` defaults to today in the pharmacy timezone; tests pass it explicitly.
    ``start_date`` / ``end_date`` apply only to :attr:`Period.CUSTOM`.

    Weeks start on **Monday** (ISO 8601), so "this week" on a Sunday is the six days
    behind you, not the day itself.
    """

    # Resolved before the clock is consulted: an all-time range has no boundaries to
    # compute, so it must not depend on timezone data being available.
    if period is Period.ALL_TIME:
        return DateRange(None, None)

    if period is Period.CUSTOM:
        if start_date is None or end_date is None:
            raise ValueError(
                "Period.CUSTOM requires both start_date and end_date"
            )
        return DateRange(start_date, end_date)

    reference = as_of or today()

    if period is Period.TODAY:
        return DateRange(reference, reference)

    if period is Period.YESTERDAY:
        yesterday = reference - timedelta(days=1)
        return DateRange(yesterday, yesterday)

    if period is Period.THIS_WEEK:
        monday = reference - timedelta(days=reference.weekday())
        return DateRange(monday, reference)

    if period is Period.LAST_WEEK:
        this_monday = reference - timedelta(days=reference.weekday())
        last_monday = this_monday - timedelta(days=7)
        return DateRange(last_monday, this_monday - timedelta(days=1))

    if period is Period.THIS_MONTH:
        return DateRange(reference.replace(day=1), reference)

    if period is Period.LAST_MONTH:
        first_of_this_month = reference.replace(day=1)
        last_of_previous = first_of_this_month - timedelta(days=1)
        return _month_range(last_of_previous.year, last_of_previous.month)

    if period is Period.THIS_QUARTER:
        quarter_start = _quarter_range(reference.year, _quarter_of(reference)).start
        return DateRange(quarter_start, reference)

    if period is Period.LAST_QUARTER:
        quarter = _quarter_of(reference)
        if quarter == 1:
            return _quarter_range(reference.year - 1, 4)
        return _quarter_range(reference.year, quarter - 1)

    if period is Period.THIS_YEAR:
        return DateRange(date(reference.year, 1, 1), reference)

    if period is Period.LAST_YEAR:
        previous = reference.year - 1
        return DateRange(date(previous, 1, 1), date(previous, 12, 31))

    # Unreachable while Period is exhaustive — but a new member added without a branch
    # here must fail loudly rather than silently resolve to all time.
    raise ValueError(f"No resolution rule for period {period!r}")
