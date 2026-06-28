"""Get raw page content from each source.

Devpost has a clean JSON API and needs no browser.
The other four sites are JavaScript single-page apps: their content does not
exist in the raw HTML, so a headless browser (Playwright) renders the page
first and we read the visible text.
"""

from __future__ import annotations

import json
import re

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Sites that need a headless browser to render before content can be read.
BROWSER_SOURCES = [
    {"name": "Taikai", "url": "https://taikai.network/hackathons"},
    {"name": "Hackjunction", "url": "https://www.hackjunction.com/events"},
    {"name": "Ultrahack", "url": "https://ultrahack.org/hackathons"},
    {"name": "Hackathon Hub", "url": "https://hackathonhub.eu/events"},
]

# Keep page text within a sane size before sending it to the LLM.
MAX_CONTENT_CHARS = 40000


def _strip_tags(text: str) -> str:
    """Remove simple HTML tags from a string (Devpost wraps prize in <span>)."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_devpost(pages: int = 2) -> str:
    """Fetch hackathons from Devpost's public JSON API and return clean JSON text."""
    items: list[dict] = []
    for page in range(1, pages + 1):
        resp = requests.get(
            "https://devpost.com/api/hackathons",
            params={"page": page},
            headers={"User-Agent": USER_AGENT},
            timeout=25,
        )
        resp.raise_for_status()
        data = resp.json()
        hackathons = data.get("hackathons", [])
        if not hackathons:
            break
        for h in hackathons:
            items.append(
                {
                    "title": h.get("title", ""),
                    "organizer": h.get("organization_name", ""),
                    "dates": h.get("submission_period_dates", ""),
                    "location": (h.get("displayed_location") or {}).get("location", ""),
                    "prize": _strip_tags(h.get("prize_amount", "")),
                    "url": h.get("url", ""),
                    "open_state": h.get("open_state", ""),
                    "themes": [t.get("name", "") for t in h.get("themes", [])],
                }
            )
    return json.dumps(items, ensure_ascii=False, indent=2)


def render_page(context, url: str, timeout_ms: int = 45000) -> str:
    """Render a JS page in a Playwright browser context and return visible text."""
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # Give client-side data fetching a chance to finish.
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        # Scroll to trigger lazy-loaded cards.
        for _ in range(4):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(700)
        text = page.evaluate("() => document.body.innerText") or ""
        return text[:MAX_CONTENT_CHARS]
    finally:
        page.close()
