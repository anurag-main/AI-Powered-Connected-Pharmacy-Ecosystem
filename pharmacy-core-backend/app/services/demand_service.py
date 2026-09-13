"""How fast medicines leave the shelf. One definition, shared by every agent.

WHY THIS EXISTS
---------------
Three features need "how much of this sells per day", and before this module they
each answered it slightly differently:

    Expiry Risk   [midnight(as_of - 90), midnight(as_of))   clock: APP_TIMEZONE
    Reorder       [now - 30 days, forever)                  clock: system tz
    Inventory Risk (planned)  — would have been a third

The formula agreed; the *window* did not. Two of the three divergences change the
answer outright: the reorder window had no upper bound, so a back-dated or
future-dated sale counted, and it started at whatever time of day the report ran, so
running it twice in one afternoon measured two different windows. A pharmacist can
open the expiry screen and the reorder screen and see two velocities for one
medicine, with nothing on either screen to explain the gap.

This module is the single answer. It knows nothing about expiry, reorder, inventory,
forecasting, agents or the LLM — it is a domain calculator that four things happen to
call.

DATE SEMANTICS
--------------
A window is **half-open**::

    [start, end)        start included, end excluded

``DemandWindow.trailing(as_of=D, lookback_days=N)`` gives::

    start = midnight of (D - N days)      included
    end   = midnight of D                 excluded
    days  = N

Two consequences worth stating out loud, because both are deliberate:

1. **Today is excluded.** At 10am, today has banked two hours of trade. Counting it
   as a whole day drags every average down, and the drag changes depending on when
   you press the button. The window ends at last midnight so the same ``as_of``
   always measures the same thing.

2. **The span is exactly ``days`` whole days**, which is what makes
   ``units / days`` an honest average rather than a number divided by a window it
   does not match.

TIMEZONE
--------
``as_of`` defaults to :func:`app.core.time_range.today`, which reads
``APP_TIMEZONE`` (``Asia/Kolkata``). This is an Indian pharmacy: a sale rung up at
00:30 IST belongs to that day's takings, and resolving in UTC would file it under
the day before.

The datetimes compared against ``sales.sold_at`` are **naive**, because the column is
naive and stores server-local time. That is correct only while the app server and the
database share a timezone — true today, and the assumption to revisit at deployment.
The same caveat is recorded in ``app/core/time_range.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.time_range import today
from app.repositories.demand_repository import DemandRepository


@dataclass(frozen=True)
class DemandWindow:
    """A half-open span of time, ``[start, end)``, plus the day count it represents.

    ``days`` is carried rather than derived from ``end - start`` because it is the
    divisor in every velocity, and a caller reading the code should not have to work
    out whether the subtraction rounds the way they expect.
    """

    start: datetime
    end: datetime
    days: int

    def __post_init__(self) -> None:
        if self.days < 1:
            raise ValueError(f"A demand window must span at least one day, got {self.days}")
        if self.start >= self.end:
            raise ValueError(f"Window start {self.start} is not before end {self.end}")

    @classmethod
    def trailing(cls, *, lookback_days: int, as_of: date | None = None) -> "DemandWindow":
        """The ``lookback_days`` whole days ending at midnight on ``as_of``.

        ``as_of`` defaults to today in the pharmacy's timezone. Tests pass it
        explicitly so no test depends on the day it happens to run.
        """

        reference = as_of or today()
        return cls(
            start=datetime.combine(reference - timedelta(days=lookback_days), time.min),
            end=datetime.combine(reference, time.min),
            days=lookback_days,
        )

    def describe(self) -> str:
        """A label for logs and for telling the user what was actually measured."""

        return f"{self.start.date()} to {self.end.date()} (exclusive), {self.days} day(s)"


def daily_velocity(units_sold: int, days: int) -> float:
    """The canonical velocity formula: units per day over a whole window.

    Floored at zero. Negative units are only reachable through bad data — there is no
    CHECK constraint on ``sale_items.quantity`` — and a negative velocity would flow
    straight into a days-of-cover division and produce a confident absurdity.
    """

    if days < 1:
        raise ValueError(f"days must be at least 1, got {days}")

    return max(0.0, units_sold / days)


class DemandService:
    """The questions every stock-facing feature asks about sales history.

    Deterministic: SQL and Python, no model, no graph, no prompt. Consumers are the
    Expiry Risk agent, the Reorder agent, and — next — the Inventory Risk agent.
    """

    def __init__(self, db: Session) -> None:
        self.repository = DemandRepository(db)

    def units_sold(
        self, window: DemandWindow, *, medicine_ids: list[int] | None = None
    ) -> dict[int, int]:
        """``{medicine_id: units}`` over ``window``. Absent means sold nothing."""

        return self.repository.units_sold_by_medicine(
            start=window.start, end=window.end, medicine_ids=medicine_ids
        )

    def daily_velocity(
        self, window: DemandWindow, *, medicine_ids: list[int] | None = None
    ) -> dict[int, float]:
        """``{medicine_id: units per day}`` over ``window``.

        Only medicines that sold something appear. A caller wanting a row per
        medicine should default the missing ones to ``0.0`` at its own layer, where
        it knows which medicines it cares about — this service has no medicine list.
        """

        return {
            medicine_id: daily_velocity(units, window.days)
            for medicine_id, units in self.units_sold(window, medicine_ids=medicine_ids).items()
        }

    def last_sale_dates(
        self, *, medicine_ids: list[int] | None = None
    ) -> dict[int, date]:
        """``{medicine_id: date of most recent sale}``, over all time.

        Absent means never sold. Returned as a ``date`` and not a ``datetime``: every
        caller asks "how long ago", and handing back a timestamp invites someone to
        subtract two of them and get an answer that changes with the hour.
        """

        return {
            medicine_id: sold_at.date()
            for medicine_id, sold_at in self.repository.last_sale_at_by_medicine(
                medicine_ids=medicine_ids
            ).items()
        }

    def medicines_ever_sold(self, medicine_ids: list[int]) -> set[int]:
        """Which of these have any sales history at all.

        Distinct from ``units_sold`` returning nothing for them: a slow mover and a
        product that has never sold need different advice, and a report that conflates
        them tells a pharmacist to write off stock that simply launched last week.
        """

        return self.repository.medicines_with_any_sales(medicine_ids)
