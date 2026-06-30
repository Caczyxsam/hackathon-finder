"""Streamlit web front-end for Hackathon Finder.

This is a thin UI layer over the existing package: it reuses pipeline.run(),
apply_filters() and the same sort logic as the desktop GUI, and reproduces the
desktop GUI's visual style (dark palette, chips, cards). The pipeline/extraction
logic and the CustomTkinter GUI are left unchanged.

Run locally:   streamlit run streamlit_app.py
"""

from __future__ import annotations

import calendar
import html
import subprocess
from datetime import date

import streamlit as st

from hackathon_finder import fetchers, pipeline
from hackathon_finder.filtering import apply_filters, parse_date, prize_value
from hackathon_finder.models import Filters, Hackathon

# --- Palette (copied from the desktop GUI so the look is identical) ----------
ACCENT = "#38BDF8"        # sky blue
ACCENT_HOVER = "#0EA5E9"
ACCENT_TEXT = "#0B1220"   # dark text on the bright accent
APP_BG = "#161A20"
CARD_BG = "#222831"
CARD_BORDER = "#2E3742"
TITLE_COLOR = "#F1F5F9"
SUBTLE = "#94A3B8"
CHIP_BG = "#2D3542"
CHIP_FG = "#CBD5E1"
PRIZE_BG = "#10B981"      # green
PRIZE_FG = "#04130C"
ONLINE_BG = "#8B5CF6"     # violet
SOURCE_BG = "#334155"

SORT_MODES = [
    "Date: soonest first",
    "Date: latest first",
    "Prize: highest first",
    "Prize: lowest first",
    "Source: A-Z",
    "Source: Z-A",
]


# --- Small helpers (mirrors of the desktop GUI's) ----------------------------
def _six_months_ahead() -> date:
    """Date six calendar months from today (day clamped to month length)."""
    today = date.today()
    month_index = today.month - 1 + 6
    year = today.year + month_index // 12
    month = month_index % 12 + 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _date_range_text(h: Hackathon) -> str:
    if h.start_date and h.end_date and h.end_date != h.start_date:
        return f"{h.start_date} – {h.end_date}"
    return h.start_date or h.end_date or "Dates unknown"


def _sort(items: list[Hackathon], mode: str) -> list[Hackathon]:
    """Same ordering rules as the desktop GUI."""
    items = list(items)
    if mode.startswith("Date"):
        reverse = "latest" in mode
        items.sort(key=lambda h: parse_date(h.start_date) or date.max, reverse=reverse)
    elif mode.startswith("Source"):
        reverse = "Z-A" in mode
        items.sort(key=lambda h: parse_date(h.start_date) or date.max)
        items.sort(key=lambda h: (h.source or "").lower(), reverse=reverse)
    else:  # events without a prize always go last
        reverse = "highest" in mode
        with_prize = [h for h in items if prize_value(h.prize_amount) is not None]
        without_prize = [h for h in items if prize_value(h.prize_amount) is None]
        with_prize.sort(key=lambda h: prize_value(h.prize_amount) or 0.0, reverse=reverse)
        items = with_prize + without_prize
    return items


@st.cache_resource(show_spinner=False)
def _ensure_chromium() -> bool:
    """Install the Playwright Chromium binary once per server container.

    Hosted platforms (e.g. Streamlit Community Cloud) install Python deps and the
    OS packages in packages.txt, but do not download the browser binary. We do it
    lazily here; @st.cache_resource makes it run only once, not on every rerun.
    """
    try:
        subprocess.run(["playwright", "install", "chromium"], check=False, timeout=300)
    except Exception:  # noqa: BLE001 - a failed install just means browser sources error
        pass
    return True


# --- Rendering ----------------------------------------------------------------
def _chip(text: str, bg: str = CHIP_BG, fg: str = CHIP_FG) -> str:
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        f'border-radius:10px;padding:3px 10px;margin:3px 6px 3px 0;'
        f'font-size:12px;white-space:nowrap;">{html.escape(text)}</span>'
    )


def _render_card(h: Hackathon) -> None:
    parts: list[str] = []
    parts.append(
        f'<div style="background:{CARD_BG};border:1px solid {CARD_BORDER};'
        f'border-radius:14px;padding:14px 16px;margin-bottom:14px;">'
    )

    # Header: title + source chip on the right.
    source_chip = (
        _chip(h.source, bg=SOURCE_BG, fg="#E2E8F0") if h.source else ""
    )
    parts.append(
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">'
        f'<span style="font-size:17px;font-weight:700;color:{TITLE_COLOR};">'
        f'{html.escape(h.name)}</span>'
        f'<span>{source_chip}</span></div>'
    )

    if h.organizer:
        parts.append(
            f'<div style="color:{SUBTLE};margin-top:2px;">{html.escape(h.organizer)}</div>'
        )

    # Chips row: date range, Online, location, prize.
    chips = [_chip(_date_range_text(h))]
    if h.is_online:
        chips.append(_chip("Online", bg=ONLINE_BG, fg="white"))
    location = ", ".join(p for p in (h.city, h.country) if p)
    if location:
        chips.append(_chip(location))
    elif not h.is_online:
        chips.append(_chip("Location unknown"))
    if h.prize_amount:
        chips.append(_chip(h.prize_amount, bg=PRIZE_BG, fg=PRIZE_FG))
    parts.append(f'<div style="margin-top:8px;">{"".join(chips)}</div>')

    if h.venue:
        parts.append(
            f'<div style="color:{SUBTLE};margin-top:6px;">Venue: {html.escape(h.venue)}</div>'
        )

    # Link button (styled like the accent button; opens in a new tab).
    if h.link:
        parts.append(
            f'<a href="{html.escape(h.link, quote=True)}" target="_blank" '
            f'style="display:inline-block;margin-top:12px;background:{ACCENT};'
            f'color:{ACCENT_TEXT};font-weight:700;text-decoration:none;'
            f'border-radius:10px;padding:8px 16px;">Open registration / event page</a>'
        )
    else:
        parts.append(
            f'<div style="display:inline-block;margin-top:12px;background:{CHIP_BG};'
            f'color:{SUBTLE};border-radius:10px;padding:8px 16px;">No link available</div>'
        )

    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


# --- Page setup ---------------------------------------------------------------
st.set_page_config(page_title="Hackathon Finder", page_icon="\U0001f6e0️", layout="centered")

# Match the desktop GUI's dark background and accent.
st.markdown(
    f"""
    <style>
      .stApp {{ background-color: {APP_BG}; }}
      .hf-title {{ font-size:28px;font-weight:800;color:{ACCENT};margin-bottom:2px; }}
      .hf-note {{ color:gray;font-size:12px; }}
    </style>
    """,
    unsafe_allow_html=True,
)

_ensure_chromium()

if "all" not in st.session_state:
    st.session_state["all"] = []
    st.session_state["errors"] = []

st.markdown('<div class="hf-title">Hackathon Finder</div>', unsafe_allow_html=True)

# --- API key + load -----------------------------------------------------------
api_key = st.text_input(
    "Anthropic API key",
    type="password",
    placeholder="sk-ant-…",
    help="Your key is used only for this session and is never stored on the server.",
)
st.markdown(
    '<div class="hf-note">Each tester uses their own key; it is kept only for this session.</div>',
    unsafe_allow_html=True,
)

load_label = "Reload hackathons" if st.session_state["all"] else "Load hackathons"
if st.button(load_label, type="primary", disabled=not api_key):
    with st.status("Starting…", expanded=True) as status:
        try:
            results, errors = pipeline.run(
                lambda msg: status.update(label=msg), api_key.strip()
            )
            if results:
                st.session_state["all"] = results
            st.session_state["errors"] = errors
            status.update(label="Done.", state="complete")
        except Exception as error:  # noqa: BLE001
            status.update(label=f"Loading failed: {error}", state="error")

# --- Filters ------------------------------------------------------------------
st.markdown(f'<div style="color:{SUBTLE};font-weight:700;margin-top:8px;">Filters</div>',
            unsafe_allow_html=True)

col_cash, col_online = st.columns(2)
with col_cash:
    cash = st.segmented_control("Cash prize", ["Any", "Yes", "No"], default="Any", key="f_cash")
with col_online:
    online = st.segmented_control("Online", ["Any", "Yes", "No"], default="Any", key="f_online")

countries_text = st.text_input(
    "Countries", placeholder="e.g. Finland, Germany (blank = all)", key="f_countries"
)

selected_sources = st.multiselect(
    "Sources",
    options=fetchers.source_names(),
    default=fetchers.source_names(),
    key="f_sources",
)

col_from, col_to, col_sort = st.columns([1, 1, 1.4])
with col_from:
    date_from = st.date_input("Date from", value=date.today(), format="YYYY-MM-DD", key="f_from")
with col_to:
    date_to = st.date_input("to", value=_six_months_ahead(), format="YYYY-MM-DD", key="f_to")
with col_sort:
    sort_mode = st.selectbox("Sort by", SORT_MODES, index=0, key="f_sort")

# --- Filter, sort, render -----------------------------------------------------
filters = Filters(
    countries=[c.strip().lower() for c in countries_text.split(",") if c.strip()],
    cash=(cash or "Any").lower(),
    online=(online or "Any").lower(),
    start=date_from,
    end=date_to,
    sources=selected_sources,
)

all_items = st.session_state["all"]
errors = st.session_state["errors"]
shown = _sort(apply_filters(all_items, filters), sort_mode)

# Status line.
total = len(all_items)
if total == 0:
    st.info("No hackathons loaded yet. Enter your key and click Load.")
else:
    summary = f"Showing {len(shown)} of {total} hackathons."
    st.markdown(f'<div style="color:{SUBTLE};margin:6px 0;">{summary}</div>',
                unsafe_allow_html=True)

if errors:
    failed = "\n".join(f"- **{name}**: {msg}" for name, msg in errors)
    st.warning("Some sites could not be read:\n\n" + failed)

for h in shown:
    _render_card(h)

if not shown and all_items:
    st.markdown(f'<div style="color:{SUBTLE};">No hackathons match these filters.</div>',
                unsafe_allow_html=True)
