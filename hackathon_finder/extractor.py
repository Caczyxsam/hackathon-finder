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
- prize_amount: fill this ONLY with a concrete cash prize amount including its \
currency, for example "€10,000" or "$5,000". If the prize is non-cash (swag, \
credits, hardware) or not stated, leave prize_amount blank and put any prize \
description in prize_text.
- is_online: true only if the event is fully online / virtual / remote with no \
physical location.
- country, city, venue: the physical location, if stated.
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


def _parse_json(text: str) -> dict:
    """Parse JSON, tolerating code fences or stray text around the object."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _call(client: "anthropic.Anthropic", user: str):
    """Call the model, preferring schema-validated output, with a plain fallback."""
    base = dict(
        model=MODEL,
        max_tokens=8000,
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


def extract(source: str, content: str) -> list[Hackathon]:
    """Extract hackathons from one source's page content."""
    if not content or not content.strip():
        return []

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
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
