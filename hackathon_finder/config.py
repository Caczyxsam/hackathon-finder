"""Store small user settings (the API key) in a per-user config file.

The file lives in the user's own config area:
  - Windows: %APPDATA%\\HackathonFinder\\config.json
  - other:   ~/.config/hackathon-finder/config.json

The key is saved in plain text in your user profile. Delete the file to
remove it (see README).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from .models import Hackathon


def _config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "HackathonFinder"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "hackathon-finder"


def _config_file() -> Path:
    return _config_dir() / "config.json"


def _cache_file() -> Path:
    return _config_dir() / "hackathons.json"


def load_config() -> dict:
    try:
        return json.loads(_config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(data: dict) -> None:
    directory = _config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = _config_file()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Best effort: restrict to the owner on systems that support it.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_api_key() -> str:
    return str(load_config().get("api_key", ""))


def save_api_key(key: str) -> None:
    data = load_config()
    if key:
        data["api_key"] = key
    else:
        data.pop("api_key", None)
    save_config(data)


def save_hackathons(items: list[Hackathon]) -> None:
    """Save the loaded hackathons so they show again next time."""
    directory = _config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "saved_at": datetime.now().isoformat(timespec="minutes"),
        "hackathons": [asdict(h) for h in items],
    }
    _cache_file().write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_hackathons() -> tuple[list[Hackathon], str]:
    """Load previously saved hackathons. Returns (items, saved_at_text)."""
    try:
        data = json.loads(_cache_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], ""
    valid = {f.name for f in fields(Hackathon)}
    items = [
        Hackathon(**{k: v for k, v in record.items() if k in valid})
        for record in data.get("hackathons", [])
        if isinstance(record, dict)
    ]
    return items, str(data.get("saved_at", ""))
