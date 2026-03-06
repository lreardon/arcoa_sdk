import json
import os
from pathlib import Path

from .exceptions import ArcoaConfigError

DEFAULT_CONFIG_DIR = Path.home() / ".arcoa"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"


def _resolve_path(path: str | None) -> Path:
    if path is not None:
        return Path(path)
    return DEFAULT_CONFIG_PATH


def config_exists(path: str | None = None) -> bool:
    return _resolve_path(path).exists()


def load_config(path: str | None = None) -> dict:
    config_path = _resolve_path(path)
    if not config_path.exists():
        raise ArcoaConfigError(f"Config not found at {config_path}. Run 'arcoa init' first.")
    with open(config_path) as f:
        return json.load(f)


def save_config(config: dict, path: str | None = None) -> None:
    config_path = _resolve_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(config_path.parent, 0o700)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    os.chmod(config_path, 0o600)
