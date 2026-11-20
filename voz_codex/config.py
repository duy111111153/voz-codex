from __future__ import annotations

import os
from pathlib import Path


def xdg(name: str, fallback: str) -> Path:
    return Path(os.environ.get(name, fallback)).expanduser()


CONFIG_HOME = xdg("XDG_CONFIG_HOME", "~/.config") / "voz-codex"
DATA_HOME = xdg("XDG_DATA_HOME", "~/.local/share") / "voz-codex"
RUNTIME_HOME = xdg("XDG_RUNTIME_DIR", "/tmp") / "voz-codex"
CONFIG_FILE = CONFIG_HOME / "config.toml"
DB_FILE = DATA_HOME / "voz-codex.sqlite3"
SOCKET_FILE = RUNTIME_HOME / "control.sock"


def ensure_dirs() -> None:
    for path in (CONFIG_HOME, DATA_HOME, RUNTIME_HOME):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass


def load() -> dict:
    ensure_dirs()
    data = {
        "codex_command": "codex app-server --stdio",
        "model": "gpt-5.6-luna",
        "overlay_corner": "top-right",
        "speech_command": "",
        "project": "default",
    }
    if CONFIG_FILE.exists():
        try:
            import tomllib
            parsed = tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for section in parsed.values():
                if isinstance(section, dict):
                    data.update(section)
            data.update({k: v for k, v in parsed.items() if not isinstance(v, dict)})
        except (OSError, ValueError):
            pass
    return data
