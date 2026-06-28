"""Run the whole flow: fetch -> extract -> filter -> dedup.

Each source is isolated: if one site fails to respond or cannot be parsed,
the others continue and the failure is reported back to the caller.
"""

from __future__ import annotations

from typing import Callable

from . import fetchers
from .dedup import dedup
from .extractor import extract
from .filtering import filter_all
from .models import Criteria, Hackathon


def _short(error: Exception) -> str:
    text = str(error).strip().replace("\n", " ")
    return text[:200] if text else error.__class__.__name__


def run(
    criteria: Criteria,
    progress: Callable[[str], None] = lambda _msg: None,
) -> tuple[list[Hackathon], list[tuple[str, str]]]:
    """Return (results, errors). errors is a list of (source_name, message)."""
    raw: list[Hackathon] = []
    errors: list[tuple[str, str]] = []

    # 1) Devpost via its JSON API (no browser needed).
    progress("Fetching Devpost…")
    try:
        content = fetchers.fetch_devpost()
        progress("Reading Devpost…")
        raw += extract("Devpost", content)
    except Exception as error:  # noqa: BLE001 - report and keep going
        errors.append(("Devpost", _short(error)))

    # 2) The four JavaScript sites via a single headless browser.
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(user_agent=fetchers.USER_AGENT)
            try:
                for source in fetchers.BROWSER_SOURCES:
                    name = source["name"]
                    progress(f"Fetching {name}…")
                    try:
                        text = fetchers.render_page(context, source["url"])
                        progress(f"Reading {name}…")
                        raw += extract(name, text)
                    except Exception as error:  # noqa: BLE001
                        errors.append((name, _short(error)))
            finally:
                context.close()
                browser.close()
    except Exception as error:  # noqa: BLE001 - browser/Playwright unavailable
        message = "headless browser unavailable: " + _short(error)
        for source in fetchers.BROWSER_SOURCES:
            errors.append((source["name"], message))

    # 3) Deterministic filtering, then remove cross-site duplicates.
    progress("Filtering…")
    results = dedup(filter_all(raw, criteria))
    return results, errors
