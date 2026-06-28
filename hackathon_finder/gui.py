"""Minimalist CustomTkinter GUI: a small form, then result cards."""

from __future__ import annotations

import os
import threading
import tkinter as tk
import webbrowser
from datetime import date, timedelta

import customtkinter as ctk

from . import config, pipeline
from .models import Criteria, Hackathon

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def _date_range_text(h: Hackathon) -> str:
    if h.start_date and h.end_date and h.end_date != h.start_date:
        return f"{h.start_date} – {h.end_date}"
    return h.start_date or h.end_date or "Dates: unknown"


def _location_text(h: Hackathon) -> str:
    parts = [p for p in (h.city, h.country) if p]
    where = ", ".join(parts)
    if h.is_online:
        return "Online" + (f" · {where}" if where else "")
    return where or "Location: unknown"


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Hackathon Finder")
        self.geometry("760x720")
        self.minsize(640, 560)
        self._running = False

        self._build_form()
        self._build_status()
        self._build_results()

    # ---- layout ---------------------------------------------------------
    def _build_form(self) -> None:
        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            form, text="Hackathon Finder", font=ctk.CTkFont(size=20, weight="bold")
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(12, 8))

        today = date.today()
        ctk.CTkLabel(form, text="Start date (YYYY-MM-DD)").grid(
            row=1, column=0, sticky="w", padx=12, pady=4
        )
        self.start_entry = ctk.CTkEntry(form, width=160)
        self.start_entry.insert(0, today.isoformat())
        self.start_entry.grid(row=1, column=1, sticky="w", padx=12, pady=4)

        ctk.CTkLabel(form, text="End date (YYYY-MM-DD)").grid(
            row=1, column=2, sticky="w", padx=12, pady=4
        )
        self.end_entry = ctk.CTkEntry(form, width=160)
        self.end_entry.insert(0, (today + timedelta(days=90)).isoformat())
        self.end_entry.grid(row=1, column=3, sticky="w", padx=12, pady=4)

        ctk.CTkLabel(form, text="Allowed countries (comma separated)").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=12, pady=4
        )
        self.countries_entry = ctk.CTkEntry(
            form, width=360, placeholder_text="e.g. Finland, Germany (blank = any)"
        )
        self.countries_entry.grid(
            row=2, column=1, columnspan=3, sticky="w", padx=12, pady=4
        )

        self.cash_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            form, text="Require a promised cash prize", variable=self.cash_var
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=(8, 4))

        ctk.CTkLabel(form, text="Anthropic API key").grid(
            row=4, column=0, sticky="w", padx=12, pady=(4, 12)
        )
        self.api_entry = ctk.CTkEntry(
            form, width=360, show="•", placeholder_text="sk-ant-…"
        )
        self.api_entry.grid(
            row=4, column=1, columnspan=2, sticky="w", padx=12, pady=(4, 2)
        )
        # Pre-fill from the environment, otherwise from the saved config file.
        saved_key = os.environ.get("ANTHROPIC_API_KEY", "") or config.load_api_key()
        if saved_key:
            self.api_entry.insert(0, saved_key)

        ctk.CTkLabel(
            form,
            text="The key is saved on this computer so you only enter it once.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).grid(row=5, column=1, columnspan=3, sticky="w", padx=12, pady=(0, 10))

        self.search_button = ctk.CTkButton(
            form, text="Find hackathons", command=self._on_search
        )
        self.search_button.grid(row=4, column=3, sticky="e", padx=12, pady=(4, 12))

    def _build_status(self) -> None:
        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.pack(fill="x", padx=20, pady=(0, 4))

    def _build_results(self) -> None:
        self.results_frame = ctk.CTkScrollableFrame(self, label_text="Results")
        self.results_frame.pack(fill="both", expand=True, padx=16, pady=(4, 16))

    # ---- helpers --------------------------------------------------------
    def _set_status(self, text: str, warn: bool = False) -> None:
        # ("light", "dark") tuple is the theme default for normal text.
        color = "#d9534f" if warn else ("gray10", "gray90")
        self.status_label.configure(text=text, text_color=color)

    def _clear_results(self) -> None:
        for child in self.results_frame.winfo_children():
            child.destroy()

    # ---- search flow ----------------------------------------------------
    def _on_search(self) -> None:
        if self._running:
            return
        try:
            criteria = self._read_criteria()
        except ValueError as error:
            self._set_status(str(error), warn=True)
            return

        api_key = self.api_entry.get().strip()
        if not api_key:
            self._set_status("Enter your Anthropic API key first.", warn=True)
            return

        # Remember the key for next time (best effort; never blocks the search).
        try:
            config.save_api_key(api_key)
        except Exception:  # noqa: BLE001
            pass

        self._running = True
        self.search_button.configure(state="disabled")
        self._clear_results()
        self._set_status("Starting…")

        thread = threading.Thread(
            target=self._worker, args=(criteria, api_key), daemon=True
        )
        thread.start()

    def _read_criteria(self) -> Criteria:
        try:
            start = date.fromisoformat(self.start_entry.get().strip())
            end = date.fromisoformat(self.end_entry.get().strip())
        except ValueError:
            raise ValueError("Dates must be valid and in YYYY-MM-DD format.")
        if end < start:
            raise ValueError("End date must not be before the start date.")
        countries = [
            c.strip().lower()
            for c in self.countries_entry.get().split(",")
            if c.strip()
        ]
        return Criteria(
            start=start,
            end=end,
            countries=countries,
            require_cash_prize=self.cash_var.get(),
        )

    def _worker(self, criteria: Criteria, api_key: str) -> None:
        def progress(message: str) -> None:
            self.after(0, lambda: self._set_status(message))

        try:
            results, errors = pipeline.run(criteria, progress, api_key)
        except Exception as error:  # noqa: BLE001
            self.after(0, lambda: self._finish_error(str(error)))
            return
        self.after(0, lambda: self._finish(results, errors))

    def _finish_error(self, message: str) -> None:
        self._running = False
        self.search_button.configure(state="normal")
        self._set_status(f"Search failed: {message}", warn=True)

    def _finish(
        self,
        results: list[Hackathon],
        errors: list[tuple[str, str]],
    ) -> None:
        self._running = False
        self.search_button.configure(state="normal")

        summary = f"Found {len(results)} hackathon(s)."
        if errors:
            failed = ", ".join(name for name, _ in errors)
            summary += f"  Could not read: {failed}."
        self._set_status(summary, warn=bool(errors) and not results)

        if errors:
            self._render_errors(errors)
        for h in results:
            self._render_card(h)
        if not results:
            ctk.CTkLabel(
                self.results_frame,
                text="No hackathons matched your criteria.",
            ).pack(anchor="w", padx=8, pady=8)

    # ---- rendering ------------------------------------------------------
    def _render_errors(self, errors: list[tuple[str, str]]) -> None:
        box = ctk.CTkFrame(self.results_frame, fg_color="#5a2a2a")
        box.pack(fill="x", padx=4, pady=(4, 8))
        ctk.CTkLabel(
            box,
            text="Some sites could not be read:",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))
        for name, message in errors:
            ctk.CTkLabel(
                box, text=f"• {name}: {message}", anchor="w", justify="left"
            ).pack(fill="x", padx=10, pady=1)
        box.pack_configure(pady=(4, 12))

    def _render_card(self, h: Hackathon) -> None:
        card = ctk.CTkFrame(self.results_frame)
        card.pack(fill="x", padx=4, pady=6)

        ctk.CTkLabel(
            card,
            text=h.name,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=620,
        ).pack(fill="x", padx=12, pady=(10, 2))

        lines = []
        if h.organizer:
            lines.append(h.organizer)
        lines.append(_date_range_text(h))
        lines.append(_location_text(h))
        if h.venue:
            lines.append(f"Venue: {h.venue}")
        if h.prize_amount:
            lines.append(f"Prize: {h.prize_amount}")
        lines.append(f"Source: {h.source}")

        for line in lines:
            ctk.CTkLabel(
                card, text=line, anchor="w", justify="left", wraplength=620
            ).pack(fill="x", padx=12, pady=0)

        button = ctk.CTkButton(
            card,
            text="Open registration / event page",
            width=240,
            command=lambda url=h.link: webbrowser.open(url) if url else None,
        )
        if not h.link:
            button.configure(state="disabled", text="No link available")
        button.pack(anchor="w", padx=12, pady=(6, 12))


def main() -> None:
    App().mainloop()
