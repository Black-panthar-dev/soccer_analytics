"""Load the local JSON configuration with clear fatal errors."""

from __future__ import annotations

import json
from pathlib import Path


class ConfigError(ValueError):
    """Raised when configuration cannot be read safely."""


def load_config(path: Path) -> dict[str, object]:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Required configuration file not found: {config_path}")
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Could not read configuration {config_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"Configuration root must be an object: {config_path}")
    return value
