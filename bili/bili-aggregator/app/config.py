from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
BASE_CONFIG_PATH = ROOT_DIR / "config.yaml"
LOCAL_CONFIG_PATH = ROOT_DIR / "config.local.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(f"{path.name} must contain a YAML mapping at top level")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    base = _read_yaml(BASE_CONFIG_PATH)
    local = _read_yaml(LOCAL_CONFIG_PATH)
    return deep_merge(base, local)
