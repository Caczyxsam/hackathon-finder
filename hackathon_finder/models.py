"""Data types shared across the app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Hackathon:
    """One hackathon. Empty strings mean the value is unknown."""

    name: str = ""
    organizer: str = ""
    start_date: str = ""   # ISO date, e.g. "2026-09-14", or "" if unknown
    end_date: str = ""     # ISO date or ""
    country: str = ""
    city: str = ""
    venue: str = ""
    prize_amount: str = ""  # only a concrete cash amount, e.g. "€10,000", else ""
    prize_text: str = ""    # free text about the prize, if any
    link: str = ""          # registration or event page
    is_online: bool = False
    source: str = ""        # which website it came from


@dataclass
class Criteria:
    """The search settings entered by the user."""

    start: date
    end: date
    countries: list[str] = field(default_factory=list)  # normalized, lower case
    require_cash_prize: bool = False
