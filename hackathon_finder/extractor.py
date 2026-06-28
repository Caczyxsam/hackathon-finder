"""Turn raw page content into structured hackathon records using Claude.

The model only extracts facts that are present in the content. It never
guesses or filters: all filtering happens later in plain Python.
"""

from __future__ import annotations

import json
import re
from datetime import date

import anthropic

from .models import Hackathon

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """You extract hackathon and tech-event listings from web page \
content into structured data.

Find every distinct hackathon or tech event in the content and return one record \
for each. Follow these rules strictly:

- Use only information that is explicitly present in the content. Never guess or \
invent a value.
- If a field is missing or unclear, return an empty string "".
- Dates must be ISO format YYYY-MM-DD. If only a partial date is given and you \
cannot determine the full date from the content, leave it blank.
- prize_amount: fill this ONLY with a concrete cash prize amount, for example \
"€10,000" or "$5,000". If a numeric prize value is given without a currency (for \
example a prize_money field of 50000), still put that number in prize_amount and \
add the currency only if you can tell what it is. If the prize is non-cash (swag, \
credits, hardware) or not stated, leave prize_amount blank and put any prize \
description in prize_text.
- is_online: true only if the event is fully online / virtual / remote with no \
physical location.
- country, city, venue: the physical location, if stated. If the country is \
given as a 2-letter ISO code (for example DE, FI, NL), convert it to the full \
English country name (Germany, Finland, Netherlands).
- If the content has a location_type field, treat "online" as is_online true and \
"onsite"/"hybrid" as a physical event (is_online false).
- link: the registration page or event page URL.
- Ignore navigation, ads, and anything that is not an event.

Return ONLY a JSON object of the form {"hackathons": [ ... ]} and nothing else."""

# JSON schema for structured outputs. Every field is required; unknown values
# are returned as empty strings (or false for is_online).
SCHEMA = {
    "type": "object",
    "properties": {
        "hackathons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "organizer": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "country": {"type": "string"},
                    "city": {"type": "string"},
                    "venue": {"type": "string"},
                    "prize_amount": {"type": "string"},
                    "prize_text": {"type": "string"},
                    "link": {"type": "string"},
                    "is_online": {"type": "boolean"},
                },
                "required": [
                    "name", "organizer", "start_date", "end_date", "country",
                    "city", "venue", "prize_amount", "prize_text", "link",
                    "is_online",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hackathons"],
    "additionalProperties": False,
}


def _salvage(text: str) -> dict:
    """Recover as many complete {...} records as possible from broken JSON.

    Used when the model output is cut off (truncated array), so a single
    truncation does not lose every record from a source.
    """
    objects: list[dict] = []
    start = text.find("[")
    if start == -1:
        return {"hackathons": []}
    depth = 0
    obj_start: int | None = None
    for i in range(start, len(text)):
        char = text[i]
        if char == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                try:
                    objects.append(json.loads(text[obj_start : i + 1]))
                except json.JSONDecodeError:
                    pass
                obj_start = None
    return {"hackathons": objects}


def _parse_json(text: str) -> dict:
    """Parse JSON, tolerating code fences, stray text, or a truncated array."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    inner = text[start : end + 1] if start != -1 and end != -1 else text
    try:
        return json.loads(inner)
    except json.JSONDecodeError:
        return _salvage(text)


def _call(client: "anthropic.Anthropic", user: str):
    """Call the model, preferring schema-validated output, with a plain fallback."""
    base = dict(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
    )
    try:
        return client.messages.create(
            **base,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
    except (TypeError, anthropic.BadRequestError):
        # Older SDK or unsupported parameter: rely on the prompt for JSON.
        return client.messages.create(**base)


# How many API records to send to the model per call. Keeping this small means
# the JSON the model writes back stays well under max_tokens and is never cut off.
_BATCH_SIZE = 30


def _client(api_key: str | None) -> "anthropic.Anthropic":
    # api_key=None makes the client fall back to ANTHROPIC_API_KEY.
    return anthropic.Anthropic(api_key=api_key or None)


def _extract_content(client: "anthropic.Anthropic", source: str, content: str) -> list[Hackathon]:
    """Run one extraction call over a single block of content."""
    today = date.today().isoformat()
    user = (
        f"Today's date: {today}\n"
        f"Source website: {source}\n\n"
        f"Page content:\n{content}"
    )
    response = _call(client, user)
    text = next((b.text for b in response.content if b.type == "text"), "")
    data = _parse_json(text)

    results: list[Hackathon] = []
    for item in data.get("hackathons", []):
        if not isinstance(item, dict):
            continue
        results.append(
            Hackathon(
                name=str(item.get("name", "")).strip(),
                organizer=str(item.get("organizer", "")).strip(),
                start_date=str(item.get("start_date", "")).strip(),
                end_date=str(item.get("end_date", "")).strip(),
                country=str(item.get("country", "")).strip(),
                city=str(item.get("city", "")).strip(),
                venue=str(item.get("venue", "")).strip(),
                prize_amount=str(item.get("prize_amount", "")).strip(),
                prize_text=str(item.get("prize_text", "")).strip(),
                link=str(item.get("link", "")).strip(),
                is_online=bool(item.get("is_online", False)),
                source=source,
            )
        )
    return results


def extract_text(source: str, content: str, api_key: str | None = None) -> list[Hackathon]:
    """Extract hackathons from rendered page text (one call)."""
    if not content or not content.strip():
        return []
    return _extract_content(_client(api_key), source, content)


def extract_items(
    source: str, items: list[dict], api_key: str | None = None
) -> list[Hackathon]:
    """Extract hackathons from a list of API records, in small batches.

    Batching keeps each model response short enough that it is never truncated.
    """
    if not items:
        return []
    client = _client(api_key)
    results: list[Hackathon] = []
    for start in range(0, len(items), _BATCH_SIZE):
        batch = items[start : start + _BATCH_SIZE]
        content = json.dumps(batch, ensure_ascii=False)
        results += _extract_content(client, source, content)
    return results
