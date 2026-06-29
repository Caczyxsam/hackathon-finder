"""CustomTkinter GUI.

Load every hackathon once, then filter and sort them live without re-fetching.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
import webbrowser
import calendar
from datetime import date

import customtkinter as ctk

from . import config, fetchers, pipeline
from .filtering import apply_filters, parse_date, prize_value
from .models import Filters, Hackathon

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# Cool, modern palette.
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


def _six_months_ahead() -> str:
    """ISO date six calendar months from today (day clamped to month length)."""
    today = date.today()
    month_index = today.month - 1 + 6
    year = today.year + month_index // 12
    month = month_index % 12 + 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def _date_range_text(h: Hackathon) -> str:
    if h.start_date and h.end_date and h.end_date != h.start_date:
        return f"{h.start_date} – {h.end_date}"
    return h.start_date or h.end_date or "Dates unknown"


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Hackathon Finder")
        self.geometry("820x820")
        self.minsize(700, 620)
        self.configure(fg_color=APP_BG)

        self._loading = False
        self._all: list[Hackathon] = []      # every hackathon loaded
        self._errors: list[tuple[str, str]] = []
        self._origin = ""                    # note about where the data came from

        self._build_header()
        self._build_filters()
        self._build_status()
        self._build_results()
        self._load_cached()

    # ---- layout ---------------------------------------------------------
    def _build_header(self) -> None:
        head = ctk.CTkFrame(self, corner_radius=16, fg_color=CARD_BG)
        head.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            head,
            text="Hackathon Finder",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=ACCENT,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(14, 6))

        ctk.CTkLabel(head, text="Anthropic API key").grid(
            row=1, column=0, sticky="w", padx=14, pady=4
        )
        self.api_entry = ctk.CTkEntry(head, width=420, show="•", placeholder_text="sk-ant-…")
        self.api_entry.grid(row=1, column=1, sticky="w", padx=8, pady=4)
        saved_key = os.environ.get("ANTHROPIC_API_KEY", "") or config.load_api_key()
        if saved_key:
            self.api_entry.insert(0, saved_key)

        self.load_button = ctk.CTkButton(
            head,
            text="Load hackathons",
            command=self._on_load,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
            height=36,
        )
        self.load_button.grid(row=1, column=2, sticky="e", padx=14, pady=4)

        ctk.CTkLabel(
            head,
            text="The key is saved on this computer so you only enter it once.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).grid(row=2, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 12))

    def _build_filters(self) -> None:
        box = ctk.CTkFrame(self, corner_radius=16, fg_color=CARD_BG)
        box.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            box, text="Filters", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=SUBTLE,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(12, 6))

        # Cash prize and Online: three-way segmented buttons.
        ctk.CTkLabel(box, text="Cash prize").grid(row=1, column=0, sticky="w", padx=14, pady=4)
        self.cash_var = tk.StringVar(value="Any")
        self._segmented(box, self.cash_var).grid(row=1, column=1, sticky="w", padx=8, pady=4)

        ctk.CTkLabel(box, text="Online").grid(row=1, column=2, sticky="w", padx=14, pady=4)
        self.online_var = tk.StringVar(value="Any")
        self._segmented(box, self.online_var).grid(row=1, column=3, sticky="w", padx=8, pady=4)

        # Countries.
        ctk.CTkLabel(box, text="Countries").grid(row=2, column=0, sticky="w", padx=14, pady=4)
        self.countries_entry = ctk.CTkEntry(
            box, width=420, placeholder_text="e.g. Finland, Germany (blank = all)"
        )
        self.countries_entry.grid(row=2, column=1, columnspan=3, sticky="w", padx=8, pady=4)
        self.countries_entry.bind("<Return>", lambda _e: self._apply())

        # Sources: one checkbox per site (all on = every source).
        ctk.CTkLabel(box, text="Sources").grid(row=3, column=0, sticky="w", padx=14, pady=4)
        sources_row = ctk.CTkFrame(box, fg_color="transparent")
        sources_row.grid(row=3, column=1, columnspan=3, sticky="w", padx=8, pady=4)
        self.source_vars: dict[str, tk.BooleanVar] = {}
        for name in fetchers.source_names():
            var = tk.BooleanVar(value=True)
            self.source_vars[name] = var
            ctk.CTkCheckBox(
                sources_row, text=name, variable=var, command=self._apply,
                checkbox_width=18, checkbox_height=18,
                fg_color=ACCENT, hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=12),
            ).pack(side="left", padx=(0, 12))

        # Date range.
        ctk.CTkLabel(box, text="Date from").grid(row=4, column=0, sticky="w", padx=14, pady=4)
        self.from_entry = ctk.CTkEntry(box, width=140, placeholder_text="YYYY-MM-DD")
        self.from_entry.grid(row=4, column=1, sticky="w", padx=8, pady=4)
        self.from_entry.insert(0, date.today().isoformat())  # default: today
        ctk.CTkLabel(box, text="to").grid(row=4, column=2, sticky="w", padx=14, pady=4)
        self.to_entry = ctk.CTkEntry(box, width=140, placeholder_text="YYYY-MM-DD")
        self.to_entry.grid(row=4, column=3, sticky="w", padx=8, pady=4)
        self.to_entry.insert(0, _six_months_ahead())  # default: 6 months ahead
        self.from_entry.bind("<Return>", lambda _e: self._apply())
        self.to_entry.bind("<Return>", lambda _e: self._apply())

        # Sort + buttons.
        ctk.CTkLabel(box, text="Sort by").grid(row=5, column=0, sticky="w", padx=14, pady=(4, 12))
        self.sort_var = tk.StringVar(value=SORT_MODES[0])
        ctk.CTkOptionMenu(
            box, values=SORT_MODES, variable=self.sort_var,
            command=lambda _v: self._apply(), width=200,
            fg_color=CHIP_BG, button_color=SOURCE_BG, button_hover_color=ACCENT_HOVER,
            corner_radius=8,
        ).grid(row=5, column=1, sticky="w", padx=8, pady=(4, 12))

        ctk.CTkButton(
            box, text="Apply filters", command=self._apply, width=120,
            corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT, font=ctk.CTkFont(weight="bold"),
        ).grid(row=5, column=2, sticky="w", padx=8, pady=(4, 12))
        ctk.CTkButton(
            box, text="Reset", command=self._reset_filters, width=80,
            corner_radius=10, fg_color=CHIP_BG, hover_color=SOURCE_BG,
        ).grid(row=5, column=3, sticky="w", padx=8, pady=(4, 12))

    def _segmented(self, parent, variable) -> ctk.CTkSegmentedButton:
        return ctk.CTkSegmentedButton(
            parent,
            values=["Any", "Yes", "No"],
            variable=variable,
            command=lambda _v: self._apply(),
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=CHIP_BG,
            text_color=CHIP_FG,
        )

    def _build_status(self) -> None:
        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.pack(fill="x", padx=20, pady=(0, 4))

    def _build_results(self) -> None:
        self.results_frame = ctk.CTkScrollableFrame(
            self, label_text="Hackathons", fg_color="transparent",
            label_fg_color=APP_BG, label_text_color=SUBTLE,
        )
        self.results_frame.pack(fill="both", expand=True, padx=16, pady=(4, 16))

    # ---- helpers --------------------------------------------------------
    def _set_status(self, text: str, warn: bool = False) -> None:
        color = "#d9534f" if warn else ("gray10", "gray90")
        self.status_label.configure(text=text, text_color=color)

    def _clear_results(self) -> None:
        for child in self.results_frame.winfo_children():
            child.destroy()

    def _chip(self, parent, text: str, bg: str = CHIP_BG, fg: str = CHIP_FG) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent, text=f"  {text}  ", fg_color=bg, text_color=fg,
            corner_radius=10, height=24, font=ctk.CTkFont(size=12),
        )

    # ---- loading --------------------------------------------------------
    def _on_load(self) -> None:
        if self._loading:
            return
        api_key = self.api_entry.get().strip()
        if not api_key:
            self._set_status("Enter your Anthropic API key first.", warn=True)
            return
        try:
            config.save_api_key(api_key)
        except Exception:  # noqa: BLE001
            pass

        self._loading = True
        self.load_button.configure(state="disabled", text="Loading…")
        self._clear_results()
        self._set_status("Starting…")

        threading.Thread(target=self._worker, args=(api_key,), daemon=True).start()

    def _worker(self, api_key: str) -> None:
        def progress(message: str) -> None:
            self.after(0, lambda: self._set_status(message))

        try:
            results, errors = pipeline.run(progress, api_key)
        except Exception as error:  # noqa: BLE001
            self.after(0, lambda: self._load_failed(str(error)))
            return
        self.after(0, lambda: self._loaded(results, errors))

    def _load_cached(self) -> None:
        """On startup, show the most recently saved hackathons, if any."""
        try:
            items, saved_at = config.load_hackathons()
        except Exception:  # noqa: BLE001
            items, saved_at = [], ""
        if items:
            self._all = items
            self._errors = []
            self._origin = (
                f"saved {saved_at.replace('T', ' ')}" if saved_at else "saved data"
            )
            self.load_button.configure(text="Reload hackathons")
            self._apply()

    def _load_failed(self, message: str) -> None:
        self._loading = False
        self.load_button.configure(state="normal", text="Load hackathons")
        self._set_status(f"Loading failed: {message}", warn=True)

    def _loaded(self, results: list[Hackathon], errors: list[tuple[str, str]]) -> None:
        self._loading = False
        self.load_button.configure(state="normal", text="Reload hackathons")
        self._all = results
        self._errors = errors
        self._origin = ""
        if results:
            # Update the saved list only when the research returned something,
            # so a fully-failed load does not wipe the previous results.
            try:
                config.save_hackathons(results)
            except Exception:  # noqa: BLE001
                pass
        self._apply()  # show everything (filters default to "all")

    # ---- filtering / rendering -----------------------------------------
    def _read_filters(self) -> Filters:
        countries = [
            c.strip().lower()
            for c in self.countries_entry.get().split(",")
            if c.strip()
        ]
        start = self._read_date(self.from_entry)
        end = self._read_date(self.to_entry)
        sources = [name for name, var in self.source_vars.items() if var.get()]
        return Filters(
            countries=countries,
            cash=self.cash_var.get().lower(),
            online=self.online_var.get().lower(),
            start=start,
            end=end,
            sources=sources,
        )

    @staticmethod
    def _read_date(entry) -> date | None:
        text = entry.get().strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise ValueError("Dates must be YYYY-MM-DD or left blank.")

    def _reset_filters(self) -> None:
        self.cash_var.set("Any")
        self.online_var.set("Any")
        for var in self.source_vars.values():
            var.set(True)
        self.countries_entry.delete(0, "end")
        self.from_entry.delete(0, "end")
        self.from_entry.insert(0, date.today().isoformat())  # default: today
        self.to_entry.delete(0, "end")
        self.to_entry.insert(0, _six_months_ahead())  # default: 6 months ahead
        self.sort_var.set(SORT_MODES[0])
        self._apply()

    def _apply(self) -> None:
        if self._loading:
            return
        try:
            filters = self._read_filters()
        except ValueError as error:
            self._set_status(str(error), warn=True)
            return

        shown = self._sort(apply_filters(self._all, filters))
        self._render(shown)

        total = len(self._all)
        if total == 0:
            summary = "No hackathons loaded yet. Enter your key and click Load."
        else:
            summary = f"Showing {len(shown)} of {total} hackathons."
            if self._origin:
                summary += f"  ({self._origin})"
        if self._errors:
            failed = ", ".join(name for name, _ in self._errors)
            summary += f"  Could not read: {failed}."
        self._set_status(summary, warn=bool(self._errors) and total == 0)

    def _sort(self, items: list[Hackathon]) -> list[Hackathon]:
        mode = self.sort_var.get()
        items = list(items)
        if mode.startswith("Date"):
            reverse = "latest" in mode
            items.sort(key=lambda h: parse_date(h.start_date) or date.max, reverse=reverse)
        elif mode.startswith("Source"):
            reverse = "Z-A" in mode
            # Secondary order: soonest first within each source.
            items.sort(key=lambda h: parse_date(h.start_date) or date.max)
            items.sort(key=lambda h: (h.source or "").lower(), reverse=reverse)
        else:  # events without a prize always go last
            reverse = "highest" in mode
            with_prize = [h for h in items if prize_value(h.prize_amount) is not None]
            without_prize = [h for h in items if prize_value(h.prize_amount) is None]
            with_prize.sort(key=lambda h: prize_value(h.prize_amount) or 0.0, reverse=reverse)
            items = with_prize + without_prize
        return items

    def _render(self, items: list[Hackathon]) -> None:
        self._clear_results()
        if self._errors:
            self._render_errors(self._errors)
        for h in items:
            self._render_card(h)
        if not items and self._all:
            ctk.CTkLabel(
                self.results_frame, text="No hackathons match these filters.",
                text_color=SUBTLE,
            ).pack(anchor="w", padx=8, pady=8)

    def _render_errors(self, errors: list[tuple[str, str]]) -> None:
        box = ctk.CTkFrame(
            self.results_frame, corner_radius=12, fg_color="#3A2630",
            border_width=1, border_color="#7F1D1D",
        )
        box.pack(fill="x", padx=4, pady=(4, 12))
        ctk.CTkLabel(
            box, text="Some sites could not be read:",
            font=ctk.CTkFont(weight="bold"), text_color="#FCA5A5", anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))
        for name, message in errors:
            ctk.CTkLabel(
                box, text=f"•  {name}: {message}", text_color="#F1D5D5",
                anchor="w", justify="left", wraplength=600,
            ).pack(fill="x", padx=12, pady=1)
        ctk.CTkLabel(box, text="", height=4).pack()

    def _render_card(self, h: Hackathon) -> None:
        card = ctk.CTkFrame(
            self.results_frame, corner_radius=14, fg_color=CARD_BG,
            border_width=1, border_color=CARD_BORDER,
        )
        card.pack(fill="x", padx=4, pady=7)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(13, 2))
        ctk.CTkLabel(
            header, text=h.name, font=ctk.CTkFont(size=17, weight="bold"),
            text_color=TITLE_COLOR, anchor="w", justify="left", wraplength=540,
        ).pack(side="left", fill="x", expand=True)
        if h.source:
            self._chip(header, h.source, bg=SOURCE_BG, fg="#E2E8F0").pack(
                side="right", padx=(8, 0)
            )

        if h.organizer:
            ctk.CTkLabel(
                card, text=h.organizer, text_color=SUBTLE,
                anchor="w", justify="left", wraplength=580,
            ).pack(fill="x", padx=16)

        chips = ctk.CTkFrame(card, fg_color="transparent")
        chips.pack(fill="x", padx=12, pady=(8, 2))
        self._chip(chips, _date_range_text(h)).pack(side="left", padx=4, pady=2)
        if h.is_online:
            self._chip(chips, "Online", bg=ONLINE_BG, fg="white").pack(side="left", padx=4, pady=2)
        location = ", ".join(p for p in (h.city, h.country) if p)
        if location:
            self._chip(chips, location).pack(side="left", padx=4, pady=2)
        elif not h.is_online:
            self._chip(chips, "Location unknown").pack(side="left", padx=4, pady=2)
        if h.prize_amount:
            self._chip(chips, h.prize_amount, bg=PRIZE_BG, fg=PRIZE_FG).pack(side="left", padx=4, pady=2)

        if h.venue:
            ctk.CTkLabel(
                card, text=f"Venue: {h.venue}", text_color=SUBTLE,
                anchor="w", justify="left", wraplength=580,
            ).pack(fill="x", padx=16, pady=(2, 0))

        button = ctk.CTkButton(
            card, text="Open registration / event page", width=240, height=32,
            corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
            command=lambda url=h.link: webbrowser.open(url) if url else None,
        )
        if not h.link:
            button.configure(
                state="disabled", text="No link available",
                fg_color=CHIP_BG, text_color=SUBTLE,
            )
        button.pack(anchor="w", padx=16, pady=(10, 14))


def main() -> None:
    App().mainloop()
