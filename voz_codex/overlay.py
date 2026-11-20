from __future__ import annotations

import subprocess


def show(title: str, text: str, timeout: int = 4) -> None:
    body = text.strip()[:3000]
    try:
        subprocess.Popen(["notify-send", "-a", "Voz Codex", "-t", str(timeout * 1000), title, body], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
