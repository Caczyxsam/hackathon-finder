"""Load all hackathons: fetch -> extract -> dedup (no filtering).

Filtering now happens live in the GUI, so the pipeline returns every
hackathon it can read. Each source is isolated: if one site fails to respond
or cannot be parsed, the others continue and the failure is reported back.
"""

from __future__ import annotations

from typing import Callable

from . import fetchers
from .dedup import dedup
from .extractor import extract_items, extract_text
from .models import Hackathon


def _short(error: Exception) -> str:
    text = str(error).strip().replace("\n", " ")
    return text[:200] if text else error.__class__.__name__


def run(
    progress: Callable[[str], None] = lambda _msg: None,
    api_key: str | None = None,
) -> tuple[list[Hackathon], list[tuple[str, str]]]:
    """Return (all_hackathons, errors). errors is a list of (source, message)."""
    raw: list[Hackathon] = []
    errors: list[tuple[str, str]] = []

    # 1) Sources with a clean data API (no browser needed).
    for source in fetchers.API_SOURCES:
        name = source["name"]
        progress(f"Fetching {name}…")
        try:
            items = source["fetch"]()
            progress(f"Reading {name}…")
            raw += extract_items(name, items, api_key)
        except Exception as error:  # noqa: BLE001 - report and keep going
            errors.append((name, _short(error)))

    # 2) The JavaScript sites via a single headless browser.
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=fetchers.USER_AGENT,
                viewport={"width": 1280, "height": 1600},
            )
            try:
                for source in fetchers.BROWSER_SOURCES:
                    name = source["name"]
                    progress(f"Fetching {name}…")
                    try:
                        text = fetchers.render_page(context, source["url"])
                        progress(f"Reading {name}…")
                        raw += extract_text(name, text, api_key)
                    except Exception as error:  # noqa: BLE001
                        errors.append((name, _short(error)))
            finally:
                context.close()
                browser.close()
    except Exception as error:  # noqa: BLE001 - browser/Playwright unavailable
        message = "headless browser unavailable: " + _short(error)
        for source in fetchers.BROWSER_SOURCES:
            errors.append((source["name"], message))

    # 3) Remove cross-site duplicates. No criteria filtering here.
    progress("Removing duplicates…")
    return dedup(raw), errors
