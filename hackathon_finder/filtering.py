"""Deterministic, in-code filtering. The LLM never decides what to keep."""

from __future__ import annotations

import re
from datetime import date

from .models import Criteria, Hackathon

# Currency symbols and common codes used to detect a real cash prize.
_CURRENCY = r"(?:[$€£₹¥]|\b(?:usd|eur|gbp|inr|jpy|cad|aud|chf|sek|nok|dkk|pln)\b)"


def parse_date(value: str) -> date | None:
    """Parse an ISO-like date string. Return None if it cannot be parsed."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            from datetime import datetime

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


def has_cash_prize(prize_amount: str) -> bool:
    """True if the prize field clearly contains a cash amount."""
    s = (prize_amount or "").strip()
    if not s or not re.search(r"\d", s):
        return False
    return re.search(_CURRENCY, s, re.IGNORECASE) is not None


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def in_window(h: Hackathon, criteria: Criteria, today: date) -> bool:
    """True if the event is upcoming and starts within the search window."""
    start = parse_date(h.start_date)
    if start is None:
        return False  # no usable date -> cannot confirm it is upcoming
    end = parse_date(h.end_date) or start
    if end < today:
        return False  # already finished
    lower = max(today, criteria.start)
    return lower <= start <= criteria.end


def country_ok(h: Hackathon, criteria: Criteria) -> bool:
    """Online events always pass. Otherwise the country must be allowed."""
    if h.is_online:
        return True
    if not criteria.countries:
        return True  # user set no country restriction
    if not h.country:
        return False  # strict: unknown country is excluded
    hc = _norm(h.country)
    return any(c == hc or c in hc or hc in c for c in criteria.countries)


def cash_ok(h: Hackathon, criteria: Criteria) -> bool:
    if not criteria.require_cash_prize:
        return True
    return has_cash_prize(h.prize_amount)


def filter_all(items: list[Hackathon], criteria: Criteria) -> list[Hackathon]:
    """Apply all filters. Returns only events that pass every check."""
    today = date.today()
    return [
        h
        for h in items
        if h.name
        and in_window(h, criteria, today)
        and country_ok(h, criteria)
        and cash_ok(h, criteria)
    ]
