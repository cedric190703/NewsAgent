"""A minimal 5-field cron matcher.

The scheduler only needs to answer "should this fire in the current minute?",
which does not justify a dependency. Supported syntax is the standard subset:

    *            every value
    5            an exact value
    1,5,9        a list
    1-5          a range
    */15         a step over the whole range
    1-20/5       a step over a range

Fields are `minute hour day-of-month month day-of-week` (Sunday is 0 or 7).
`@hourly`, `@daily`, `@midnight`, `@weekly`, `@monthly` and `@yearly` are
accepted as aliases.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
FIELD_NAMES = ("minute", "hour", "day-of-month", "month", "day-of-week")

ALIASES = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

MONTH_NAMES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
WEEKDAY_NAMES = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")

MONTHS = {name: index for index, name in enumerate(MONTH_NAMES, start=1)}
WEEKDAYS = {name: index for index, name in enumerate(WEEKDAY_NAMES)}


class CronError(ValueError):
    """The expression is not valid cron syntax."""


def _named(token: str, index: int) -> str:
    lowered = token.lower()
    if index == 3 and lowered in MONTHS:
        return str(MONTHS[lowered])
    if index == 4 and lowered in WEEKDAYS:
        return str(WEEKDAYS[lowered])
    return token


def _parse_field(raw: str, index: int) -> frozenset[int]:
    low, high = FIELD_RANGES[index]
    values: set[int] = set()

    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"empty {FIELD_NAMES[index]} field")

        step = 1
        if "/" in part:
            part, _, step_text = part.partition("/")
            if not step_text.isdigit() or int(step_text) < 1:
                raise CronError(f"invalid step in {FIELD_NAMES[index]}: {step_text!r}")
            step = int(step_text)
            part = part.strip() or "*"

        if part == "*":
            start, end = low, high
        elif "-" in part.lstrip("-"):
            start_text, _, end_text = part.partition("-")
            start, end = _to_int(start_text, index), _to_int(end_text, index)
        else:
            start = end = _to_int(part, index)

        if start > end:
            raise CronError(f"reversed range in {FIELD_NAMES[index]}: {part!r}")
        # Cron traditionally accepts 7 as Sunday, one past the nominal range.
        sunday_as_seven = index == 4 and end == 7
        if (start < low or end > high) and not sunday_as_seven:
            raise CronError(f"{FIELD_NAMES[index]} out of range {low}-{high}: {part!r}")
        values.update(value % 7 if index == 4 else value for value in range(start, end + 1, step))

    return frozenset(values)


def _to_int(token: str, index: int) -> int:
    token = _named(token.strip(), index)
    try:
        return int(token)
    except ValueError as exc:
        raise CronError(f"invalid {FIELD_NAMES[index]} value: {token!r}") from exc


class CronSchedule:
    """A parsed expression. `matches(moment)` is minute-resolution."""

    __slots__ = ("_fields", "expression")

    def __init__(self, expression: str) -> None:
        normalised = ALIASES.get(expression.strip().lower(), expression).strip()
        parts = normalised.split()
        if len(parts) != 5:
            raise CronError(
                f"expected 5 fields (minute hour day month weekday), got {len(parts)}"
            )
        self.expression = expression.strip()
        self._fields = tuple(_parse_field(part, i) for i, part in enumerate(parts))

    def matches(self, moment: datetime) -> bool:
        minute, hour, dom, month, dow = self._fields
        # Cron's quirk: when both day fields are restricted, either one matching
        # is enough (that is how vixie cron behaves, and people rely on it).
        weekday = (moment.weekday() + 1) % 7  # Monday=0 -> Sunday=0
        day_match = moment.day in dom
        weekday_match = weekday in dow
        dom_restricted = len(dom) < 31
        dow_restricted = len(dow) < 7

        if dom_restricted and dow_restricted:
            day_ok = day_match or weekday_match
        else:
            day_ok = day_match and weekday_match

        return (
            moment.minute in minute
            and moment.hour in hour
            and moment.month in month
            and day_ok
        )

    def next_after(self, moment: datetime, horizon_minutes: int = 366 * 24 * 60) -> datetime | None:
        """First matching minute strictly after `moment`, or None within the horizon."""

        cursor = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(horizon_minutes):
            if self.matches(cursor):
                return cursor
            cursor += timedelta(minutes=1)
        return None

    def __repr__(self) -> str:
        return f"CronSchedule({self.expression!r})"


def parse(expression: str) -> CronSchedule:
    return CronSchedule(expression)


def is_valid(expression: str) -> bool:
    try:
        CronSchedule(expression)
    except CronError:
        return False
    return True


def describe_next(expression: str, reference: datetime | None = None) -> str | None:
    """ISO timestamp of the next firing, for display in the UI."""

    try:
        schedule = CronSchedule(expression)
    except CronError:
        return None
    moment = (reference or datetime.now(timezone.utc)).astimezone(timezone.utc)
    upcoming = schedule.next_after(moment)
    return upcoming.isoformat() if upcoming else None
