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

1. You enter a date range, a list of allowed countries, and whether a cash
   prize is required.
2. Each site's page content is fetched (the JavaScript sites are rendered in a
   headless browser first).
3. Claude reads each page and extracts structured data: name, organizer, dates,
   country, city, venue, prize, and link. If a field is missing or unclear it is
   left blank — the model does not guess.
4. The results are filtered **in code**, not by the prompt:
   - only upcoming events whose start date is inside your range,
   - only your allowed countries (online events are always included),
   - if you require a cash prize, only events with a real cash amount.
5. Duplicates that appear on more than one site are removed.
6. The matches are shown as cards.

If a site fails to respond or cannot be parsed, the others continue and the app
tells you which site failed.

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
the form). If you prefer, set it as an environment variable instead and the
field will be pre-filled from it:

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

Enter your search settings and click **Find hackathons**. The first run can take
a little while because the browser sites are rendered one by one.

## Project layout

```
main.py                     Launches the app
hackathon_finder/
  models.py                 Data types (Hackathon, Criteria)
  fetchers.py               Get page content (Devpost API + Playwright)
  extractor.py              Claude extracts structured data
  filtering.py              Deterministic filtering
  dedup.py                  Remove duplicates across sites
  pipeline.py               Runs the whole flow
  gui.py                    The CustomTkinter card view
```

## Notes

- The model used is `claude-opus-4-8`.
- Filtering is strict: events with no usable date, or (for non-online events) no
  matching country, are left out rather than guessed at.
- "Cash prize required" keeps only events whose prize is a clear money amount
  (for example `€10,000`). Swag, credits, or unspecified prizes do not count.

## License

MIT — see [LICENSE](LICENSE).
