from __future__ import annotations

import html
import re
import subprocess
import threading


def plain_text(text: str) -> str:
    text = re.sub(r"\[([^\]\n]+)\]\(https?://[^)\s]+\)", r"\1", text)
    return re.sub(r"\*\*|__|`", "", text).strip()


class Overlay:
    """Send only the latest pending update and reuse the server's card ID."""

    def __init__(self) -> None:
        self.ready = threading.Condition()
        self.pending: tuple[str, str, int] | None = None
        threading.Thread(target=self._run, daemon=True).start()

    def show(self, title: str, text: str, timeout: int = 4) -> None:
        with self.ready:
            self.pending = (title, plain_text(text)[:3000], timeout)
            self.ready.notify()

    def _run(self) -> None:
        notification_id = 0
        last = None
        while True:
            with self.ready:
                self.ready.wait_for(lambda: self.pending is not None)
                update = self.pending
                self.pending = None
            if update == last:
                continue
            title, body, timeout = update
            command = [
                "notify-send", "--print-id", "--app-name=Voz Codex",
                f"--expire-time={timeout * 1000}", f"--replace-id={notification_id}",
                "--", title, html.escape(body, quote=False),
            ]
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=True)
                notification_id = int(result.stdout.strip())
                last = update
            except (OSError, ValueError, subprocess.SubprocessError):
                continue
