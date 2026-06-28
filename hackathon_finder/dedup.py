"""Remove duplicate hackathons that appear on more than one site."""

from __future__ import annotations

import re

from .models import Hackathon

_BLANK_FILLABLE = (
    "organizer", "end_date", "country", "city", "venue",
    "prize_amount", "prize_text", "link",
)


def _norm_name(name: str) -> str:
    """Normalize a name for comparison: lower case, alphanumeric words only."""
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def _fill_blanks(keep: Hackathon, other: Hackathon) -> None:
    """Copy values from `other` into any empty fields of `keep`."""
    for field_name in _BLANK_FILLABLE:
        if not getattr(keep, field_name) and getattr(other, field_name):
            setattr(keep, field_name, getattr(other, field_name))
    if not keep.is_online and other.is_online:
        keep.is_online = True


def dedup(items: list[Hackathon]) -> list[Hackathon]:
    """Merge duplicates keyed on normalized name + start date.

    The first occurrence is kept; later duplicates fill in any blank fields.
    Records with no name are always kept as-is.
    """
    by_key: dict[tuple[str, str], Hackathon] = {}
    order: list[tuple[str, str]] = []
    extras: list[Hackathon] = []

    for h in items:
        norm = _norm_name(h.name)
        if not norm:
            extras.append(h)
            continue
        key = (norm, h.start_date or "")
        if key in by_key:
            _fill_blanks(by_key[key], h)
        else:
            by_key[key] = h
            order.append(key)

    return [by_key[k] for k in order] + extras
