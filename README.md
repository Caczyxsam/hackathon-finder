# Hackathon Finder

Collect upcoming hackathons from five websites, filter them by your criteria,
and show them as cards in a simple desktop app. An LLM (the Anthropic API)
reads each page and extracts the data; all filtering is done in plain Python.

## Sources

| Site | How the data is read |
| --- | --- |
| https://devpost.com/hackathons | Public JSON API (no browser needed) |
| https://hackathonhub.eu/events | Public Supabase JSON API (no browser needed) |
| https://taikai.network/hackathons | Headless browser (JavaScript page) |
| https://www.hackjunction.com/events | Headless browser (JavaScript page) |
| https://ultrahack.org/hackathons | Headless browser (JavaScript page) |

Two sites expose a clean JSON API, which is read directly. The other three are
JavaScript single-page apps whose content does not exist in the raw HTML, so a
headless browser (Playwright) renders the page before the content can be read.
(Hackathon Hub looks like a JavaScript page, but its events never appear in the
rendered HTML — they load from a public Supabase API, which the app reads
directly instead.)

## How it works

1. You click **Load hackathons**. Every site's content is fetched (the
   JavaScript sites are rendered in a headless browser first).
2. Claude reads each page and extracts structured data: name, organizer, dates,
   country, city, venue, prize, and link. If a field is missing or unclear it is
   left blank — the model does not guess.
3. Duplicates that appear on more than one site are removed.
4. **All** hackathons are shown as cards.
5. You then narrow them down with live filters (no re-loading needed):
   - **Cash prize**: any / yes / no,
   - **Online**: any / yes / no,
   - **Countries**: a list of accepted countries (online events always pass),
   - **Date**: a from/to range.
6. You can sort the cards by date (soonest or latest) or prize money (highest or
   lowest).

Filtering and sorting happen **in code**, not in the prompt. If a site fails to
respond or cannot be parsed, the others continue and the app tells you which
site failed.

## Requirements

- Python 3.10 or newer
- An Anthropic API key

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

### API key

You can enter your Anthropic API key directly in the app (there is a field on
the form). After you load hackathons, the key is saved on this computer so you
do not have to type it again next time.

It is stored in plain text in your user profile:

- Windows: `%APPDATA%\HackathonFinder\config.json`
- macOS / Linux: `~/.config/hackathon-finder/config.json`

To remove the saved key, clear the field and load again, or delete that file.

If you prefer, you can set the key as an environment variable instead; the field
is pre-filled from it when present:

```bash
# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "your-key-here"

# macOS / Linux
export ANTHROPIC_API_KEY="your-key-here"
```

## Run

```bash
python main.py
```

Click **Load hackathons**. The first load can take a little while because the
browser sites are rendered one by one. After they appear, use the filter and
**Sort by** controls at the top to narrow and order the cards — this is instant
and never re-loads. Click **Reload hackathons** to fetch fresh data.

## Project layout

```
main.py                     Launches the app
hackathon_finder/
  models.py                 Data types (Hackathon, Filters)
  config.py                 Saves the API key between runs
  fetchers.py               Get content (Devpost + Hackathon Hub APIs, Playwright)
  extractor.py              Claude extracts structured data
  filtering.py              Live, in-code filtering and prize parsing
  dedup.py                  Remove duplicates across sites
  pipeline.py               Loads all hackathons (fetch + extract + dedup)
  gui.py                    The CustomTkinter card view
```

## Notes

- The model used is `claude-opus-4-8`.
- Hackathons whose start date is already in the past are never shown, even with
  no date filter set. Events with no readable start date are still shown.
- Filters are strict when active: when you set a date range, events with no
  usable date are hidden; when you set countries, in-person events with no
  matching country are hidden (online events always pass the country filter).
- The cash-prize filter uses the extracted prize amount: swag, credits, or
  unspecified prizes count as "no cash prize".

## License

MIT — see [LICENSE](LICENSE).
