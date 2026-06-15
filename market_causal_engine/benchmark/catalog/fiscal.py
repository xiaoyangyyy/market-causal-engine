"""Map fiscal period to typical 8-K earnings filing date ranges."""

from __future__ import annotations

import calendar
import re


_FISCAL_RE = re.compile(r"^(?P<year>\d{4})Q(?P<quarter>[1-4])$", re.I)


def parse_fiscal_period(fiscal_period: str | None) -> tuple[int, int] | None:
    if not fiscal_period:
        return None
    match = _FISCAL_RE.match(fiscal_period.strip().upper())
    if not match:
        return None
    return int(match.group("year")), int(match.group("quarter"))


def fiscal_period_date_range(fiscal_period: str | None) -> tuple[str, str] | None:
    """
    Approximate calendar window when a US large-cap typically files Item 2.02 8-K.

    Q1–Q3: same calendar year; Q4: Jan–Feb of the following year.
    """
    parsed = parse_fiscal_period(fiscal_period)
    if not parsed:
        return None
    year, quarter = parsed
    if quarter == 1:
        return f"{year}-04-01", f"{year}-05-31"
    if quarter == 2:
        return f"{year}-07-01", f"{year}-08-31"
    if quarter == 3:
        return f"{year}-10-01", f"{year}-11-30"
    next_year = year + 1
    last_day = 29 if calendar.isleap(next_year) else 28
    return f"{next_year}-01-01", f"{next_year}-02-{last_day:02d}"


def date_in_range(value: str, start: str, end: str) -> bool:
    return start <= value <= end
