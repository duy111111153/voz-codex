"""On-demand capture of the focused Hyprland monitor."""

import json
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unicodedata import normalize


def wants_screen(text: str) -> bool:
    text = "".join(char for char in normalize("NFD", text.casefold()) if char.isascii())
    if re.search(r"\bno\s+(?:mira|mires|veas|revises|leas|analices|describas)\b", text):
        return False
    return bool(re.search(
        r"\b(?:"
        r"(?:ves|veas|se ve|aparece|hay|dice|muestra)\s+(?:(?:en|mi|la|el|este|esta)\s+)*"
        r"|(?:mira|mirar|revisa|revisar|describe|describir|lee|leer|analiza|analizar)"
        r"\s+(?:(?:lo que ves en|lo que hay en|por favor|mi|la|el|este|esta)\s+)*"
        r")(?:pantalla|monitor|escritorio)\b",
        text,
    ))


class ScreenCaptureError(RuntimeError):
    pass


@contextmanager
def screen_image():
    with TemporaryDirectory(prefix="voz-pantalla-") as folder:
        path = Path(folder) / "pantalla.jpg"
        try:
            info = subprocess.check_output(
                ["hyprctl", "-j", "monitors"], timeout=2, stderr=subprocess.DEVNULL,
            )
            monitor = next(item for item in json.loads(info) if item.get("focused"))
            logical_long_edge = max(monitor["width"], monitor["height"]) / monitor["scale"]
            scale = min(monitor["scale"], 1280 / logical_long_edge)
            subprocess.run(
                ["grim", "-o", monitor["name"], "-s", f"{scale:.4f}", "-t", "jpeg",
                 "-q", "82", str(path)],
                check=True, timeout=3, stderr=subprocess.DEVNULL,
            )
            if not path.stat().st_size:
                raise ValueError("Captura vacía")
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, StopIteration,
                ZeroDivisionError) as error:
            raise ScreenCaptureError("No pude capturar el monitor activo de Hyprland.") from error
        yield path
