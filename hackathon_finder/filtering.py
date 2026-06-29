"""Deterministic, in-code filtering applied to the loaded hackathons.

Filters are optional: with the default Filters() everything passes, so all
hackathons appear until the user narrows them down.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from .models import Filters, Hackathon


def parse_date(value: str) -> date | None:
    """Parse an ISO-like date string. Return None if it cannot be parsed."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    # Year + month only -> treat as the first of that month.
    m = re.match(r"^(\d{4})[-/.](\d{1,2})$", value)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return None
    return None


def prize_value(prize_amount: str) -> float | None:
    """Return the numeric value of a prize string, or None if there is none.

    Examples: "€10,000" -> 10000.0, "$2,000,000" -> 2000000.0, "" -> None.
    """
    match = re.search(r"\d[\d,]*(?:\.\d+)?", prize_amount or "")
    if not match:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def has_cash_prize(prize_amount: str) -> bool:
    """True if there is a concrete cash prize.

    The extractor only fills prize_amount with a real money amount (non-cash
    prizes go in prize_text), so any numeric value here means a cash prize.
    """
    return bool(re.search(r"\d", prize_amount or ""))


def _country_matches(h: Hackathon, countries: list[str]) -> bool:
    """Online events always pass. Otherwise the country must be in the list."""
    if h.is_online:
        return True
    hc = (h.country or "").strip().lower()
    if not hc:
        return False  # unknown country cannot match a specific list
    return any(c == hc or c in hc or hc in c for c in countries)


def apply_filters(items: list[Hackathon], f: Filters) -> list[Hackathon]:
    """Return only the hackathons that pass every active filter.

    Past events are always hidden: a hackathon whose start date is before today
    never appears, regardless of the other filters. Events with no usable start
    date are kept (we cannot tell that they are in the past).
    """
    today = date.today()
    allowed_sources = None if f.sources is None else {s.lower() for s in f.sources}
    results: list[Hackathon] = []
    for h in items:
        start = parse_date(h.start_date)
        if start is not None and start < today:
            continue  # already started / in the past
        if allowed_sources is not None and (h.source or "").lower() not in allowed_sources:
            continue
        if f.cash == "yes" and not has_cash_prize(h.prize_amount):
            continue
        if f.cash == "no" and has_cash_prize(h.prize_amount):
            continue
        if f.online == "yes" and not h.is_online:
            continue
        if f.online == "no" and h.is_online:
            continue
        if f.countries and not _country_matches(h, f.countries):
            continue
        if f.start or f.end:
            if start is None:
                continue  # no usable date cannot be confirmed in range
            if f.start and start < f.start:
                continue
            if f.end and start > f.end:
                continue
        results.append(h)
    return results
