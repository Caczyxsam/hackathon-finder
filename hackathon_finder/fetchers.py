"""Get raw page content from each source.

Two sources expose a clean data API and need no browser:
  - Devpost: a public JSON API.
  - Hackathon Hub: a public Supabase REST endpoint (the same data its own
    front-end loads; the events never appear in the rendered HTML, so reading
    the API directly is far more reliable than scraping the page).

The other three sites are JavaScript single-page apps: their content does not
exist in the raw HTML, so a headless browser (Playwright) renders the page
first and we read the visible text.
"""

from __future__ import annotations

import re
from datetime import date

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Keep page/API text within a sane size before sending it to the LLM.
MAX_CONTENT_CHARS = 40000


# ---------------------------------------------------------------------------
# API sources (no browser needed)
# ---------------------------------------------------------------------------

def _strip_tags(text: str) -> str:
    """Remove simple HTML tags from a string (Devpost wraps prize in <span>)."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_devpost(pages: int = 2) -> list[dict]:
    """Fetch hackathons from Devpost's public JSON API as a list of records."""
    items: list[dict] = []
    for page in range(1, pages + 1):
        resp = requests.get(
            "https://devpost.com/api/hackathons",
            params={"page": page},
            headers={"User-Agent": USER_AGENT},
            timeout=25,
        )
        resp.raise_for_status()
        hackathons = resp.json().get("hackathons", [])
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
    return items


# Hackathon Hub serves its events from a public Supabase REST API. The key below
# is the site's public "anon" key (shipped in its own JavaScript, gated server
# side). If the site ever rotates it, capture the new one from the network tab.
_HACKATHONHUB_URL = "https://czcrgiykicowicoufthv.supabase.co/rest/v1/events_public"
_HACKATHONHUB_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6Y3JnaXlraWNvd2ljb3VmdGh2Iiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3NjMzMTI5MTksImV4cCI6MjA3ODg4ODkxOX0."
    "6t6d8obiFjsa_gTsQMn43_ACEC7VRRlC72l-IpFO6y0"
)


def fetch_hackathonhub(limit: int = 120) -> list[dict]:
    """Fetch upcoming events from Hackathon Hub's public Supabase API."""
    params = {
        "select": (
            "title,organizer_name,url,type,location_type,city,state,country,"
            "start_date,end_date,prize_money,language"
        ),
        "order": "start_date.asc",
        "start_date": f"gte.{date.today().isoformat()}",  # upcoming only
        "limit": str(limit),
    }
    headers = {
        "apikey": _HACKATHONHUB_ANON_KEY,
        "authorization": f"Bearer {_HACKATHONHUB_ANON_KEY}",
        "accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    resp = requests.get(_HACKATHONHUB_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


# Each API source is a name plus a no-argument fetch function returning text.
API_SOURCES = [
    {"name": "Devpost", "fetch": fetch_devpost},
    {"name": "Hackathon Hub", "fetch": fetch_hackathonhub},
]


# ---------------------------------------------------------------------------
# Browser sources (JavaScript pages that must be rendered)
# ---------------------------------------------------------------------------

BROWSER_SOURCES = [
    {"name": "Taikai", "url": "https://taikai.network/hackathons"},
    {"name": "Hackjunction", "url": "https://www.hackjunction.com/events"},
    {"name": "Ultrahack", "url": "https://ultrahack.org/hackathons"},
]

# Best-effort labels for cookie / consent buttons that can hide content.
_CONSENT_LABELS = [
    "Accept all", "Accept All", "Accept", "I agree", "Agree",
    "Allow all", "Allow", "Got it", "OK",
]


def _dismiss_overlays(page) -> None:
    """Try to close a cookie/consent banner so it does not hide the content."""
    for label in _CONSENT_LABELS:
        try:
            button = page.get_by_role("button", name=label, exact=False)
            if button.count() > 0:
                button.first.click(timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


def render_page(context, url: str, timeout_ms: int = 45000) -> str:
    """Render a JS page in a Playwright browser context and return its text."""
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        _dismiss_overlays(page)
        # Scroll to trigger lazy-loaded cards.
        for _ in range(6):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(600)
        page.wait_for_timeout(1000)

        text = page.evaluate("() => document.body.innerText") or ""
        # Some layouts keep cards out of innerText; fall back to all DOM text.
        if len(text.strip()) < 1200:
            raw = page.evaluate("() => document.body.textContent") or ""
            text = " ".join(raw.split())
        return text[:MAX_CONTENT_CHARS]
    finally:
        page.close()
