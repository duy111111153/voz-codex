from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading


class Speech:
    def __init__(self, configured: str = ""):
        self.configured = configured
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def stop(self) -> None:
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
            self.process = None

    def speak(self, text: str) -> None:
        clean = re.sub(r"```.*?```", " código omitido ", text, flags=re.S)
        clean = re.sub(r"https?://\S+", " enlace ", clean)
        clean = re.sub(r"[*_`#]", "", clean).strip()
        if not clean:
            return
        self.stop()
        if self.configured:
            command = self.configured.split() + [clean]
        elif shutil_which("espeak-ng"):
            command = ["espeak-ng", "-v", os.environ.get("VOZ_CODEX_VOICE", "es"), "-s", "175", clean]
        else:
            return
        with self.lock:
            self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)
