from __future__ import annotations

import os
import json
import re
import subprocess
import shlex
import shutil
import signal
import threading
from contextlib import contextmanager
from itertools import cycle
from pathlib import Path
from time import monotonic

from .config import DATA_HOME

KOKORO_VOICES = {"alex": "em_alex", "dora": "ef_dora", "kokoro": "ef_dora"}

EMOJI = re.compile(
    r"[0-9#*]\ufe0f?\u20e3|"
    r"[\U0001f000-\U0001faff\U000e0020-\U000e007f"
    r"\u2600-\u27bf\ufe0e\ufe0f\u200d]|"
    r"(?<!\w):[a-z][a-z0-9_+-]*:(?!\w)",
    re.IGNORECASE,
)

_UNITS = {
    "°c": "grados Celsius", "c": "grados Celsius",
    "°f": "grados Fahrenheit", "f": "grados Fahrenheit",
    "%": "por ciento", "ms": "milisegundos", "s": "segundos",
    "min": "minutos", "h": "horas", "km": "kilómetros",
    "km/h": "kilómetros por hora", "m": "metros", "cm": "centímetros",
    "mm": "milímetros", "kg": "kilogramos", "g": "gramos",
    "mb": "megabytes", "gb": "gigabytes", "tb": "terabytes",
    "mhz": "megahercios", "ghz": "gigahercios", "hz": "hercios",
    "v": "voltios", "w": "vatios",
}


def _under_hundred(value: int) -> str:
    ones = ("cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve")
    special = {10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
               16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
               20: "veinte", 21: "veintiuno", 22: "veintidós", 23: "veintitrés",
               24: "veinticuatro", 25: "veinticinco", 26: "veintiséis", 27: "veintisiete",
               28: "veintiocho", 29: "veintinueve"}
    tens = ("", "", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa")
    if value < 10:
        return ones[value]
    if value in special:
        return special[value]
    if value < 20:
        return "dieci" + ones[value - 10]
    ten, unit = divmod(value, 10)
    return tens[ten] if not unit else f"{tens[ten]} y {ones[unit]}"


def _spanish_integer(value: int) -> str:
    if value < 100:
        return _under_hundred(value)
    if value < 1000:
        hundreds = ("", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos",
                    "seiscientos", "setecientos", "ochocientos", "novecientos")
        hundred, rest = divmod(value, 100)
        if value == 100:
            return "cien"
        return hundreds[hundred] if not rest else f"{hundreds[hundred]} {_under_hundred(rest)}"
    if value < 1_000_000:
        thousand, rest = divmod(value, 1000)
        prefix = "mil" if thousand == 1 else f"{_spanish_integer(thousand)} mil"
        return prefix if not rest else f"{prefix} {_spanish_integer(rest)}"
    return str(value)


def _number_words(match: re.Match[str]) -> str:
    raw = match.groupdict().get("number") or match.group(0)
    normalized = raw.replace(".", "").replace(",", "")
    try:
        value = int(normalized)
    except ValueError:
        return raw
    return ("menos " if value < 0 else "") + _spanish_integer(abs(value))


def spoken_metrics(text: str) -> str:
    """Make numeric prose unambiguous for Spanish TTS without changing display text."""
    def unit_replace(match: re.Match[str]) -> str:
        number = _number_words(match)
        if match.group("decimal"):
            number += f" punto {_spanish_integer(int(match.group('decimal')))}"
        unit = _UNITS.get(match.group("unit").casefold().replace(" ", ""), match.group("unit"))
        return f"{number} {unit}"

    pattern = r"(?P<number>-?\d{1,9})(?:[.,](?P<decimal>\d{1,3}))?\s*(?P<unit>°\s*[CF]|%|km/h|ms|mhz|ghz|hz|gb|mb|tb|kg|cm|mm|km|m|g|v|w|s|min|h)(?![A-Za-z])"
    text = re.sub(pattern, unit_replace, text, flags=re.I)

    def number_replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        if match.string[max(0, match.start() - 1):match.start()].isalnum() or match.string[match.end():match.end() + 1].isalnum():
            return raw
        if "." in raw or "," in raw:
            whole, decimal = re.split(r"[.,]", raw, maxsplit=1)
            return f"{_number_words(re.match(r'-?\d+', whole))} punto {_spanish_integer(int(decimal))}"
        return _number_words(match)

    return re.sub(r"-?\d{1,9}(?:[.,]\d{1,3})?", number_replace, text)


def spoken_text(text: str) -> str:
    text = EMOJI.sub("", text)
    text = re.sub(r"```.*?(?:```|\Z)", " ", text, flags=re.S)
    text = re.sub(r"\[([^\]\n]+)\]\(https?://[^)\s]+\)", r"\1", text)
    text = re.sub(r"https?://[^\s)\]]+?(?=[.,;:!?]*(?:\s|$|[)\]]))", "", text)
    text = re.sub(r"(?m)^[ \t]*(?:[-*+]|\d+[.)]|#{1,6})[ \t]+(.+)$",
                  lambda m: "\n\n" + m[1].rstrip().rstrip(".") +
                  ("" if m[1].rstrip().endswith(("?", "!", ":", "…")) else ".") + "\n\n",
                  text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"(?<=\d)\s*[–—]\s*(?=\d)", " a ", text)
    text = re.sub(r"\b(\d+)\s*°\s*C\b", r"\1 grados Celsius", text, flags=re.I)
    # Markdown and model output often omit the space after punctuation. Piper
    # interprets that as one word, which produces rushed and muddy prosody.
    text = re.sub(r"(?<=[,;:!?])(?=[A-Za-zÁÉÍÓÚÜÑáéíóúüñ¿¡])", " ", text)
    text = re.sub(r"\.{2,}", "…", text)
    # Symbols are clearer when spoken in Spanish and do not interrupt English
    # names with an unnatural literal reading.
    text = text.replace("&", " y ").replace("+", " más ")
    text = re.sub(r"[ \t]+([.,!?;:])", r"\1", text)
    text = re.sub(r"[*_`#]", "", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


class Speech:
    def __init__(self, configured: str = "", voice: str = "claude"):
        self.configured = configured
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.cues = cycle(("momento", "segundo", "revisar", "investigar"))
        self.voice = voice
        self.kokoro_process: subprocess.Popen | None = None
        self.kokoro_busy = False
        self.kokoro_started = 0.0
        self.first_audio_ms: int | None = None

    def _kokoro_command(self, voice: str) -> list[str] | None:
        python = DATA_HOME / "piper-venv/bin/python"
        models = DATA_HOME / "voices/kokoro"
        if not (python.is_file() and shutil.which("pw-play") and all(
            (models / asset).is_file()
            for asset in ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
        )):
            return None
        worker = Path(__file__).with_name("kokoro_play.py")
        return [str(python), str(worker), str(models), voice]

    def _watch_kokoro(self, process) -> None:
        with process.stdout:
            for line in process.stdout:
                with self.lock:
                    if self.kokoro_process is process:
                        if line.strip() == "audio":
                            self.first_audio_ms = round((monotonic() - self.kokoro_started) * 1000)
                        elif line.startswith("done "):
                            self.kokoro_busy = False
        process.wait()
        with self.lock:
            if self.kokoro_process is process:
                self.kokoro_process = None
                self.kokoro_busy = False
            process.stdin.close()

    def _start_kokoro(self, command):
        if self.kokoro_process is None or self.kokoro_process.poll() is not None:
            process = subprocess.Popen(
                [*command, "--serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                start_new_session=True, text=True, encoding="utf-8",
            )
            self.kokoro_process = process
            threading.Thread(target=self._watch_kokoro, args=(process,), daemon=True).start()
        return self.kokoro_process

    def prewarm(self) -> None:
        if self.configured or self.voice not in KOKORO_VOICES:
            return
        command = self._kokoro_command(KOKORO_VOICES[self.voice])
        if command:
            with self.lock:
                self._start_kokoro(command)

    @staticmethod
    def _send_kokoro(process, text: str) -> None:
        try:
            process.stdin.write(json.dumps(text, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (OSError, ValueError):
            pass

    def piper_model(self) -> Path | None:
        voices = ("es_MX-ald-medium", "es_MX-claude-high", "es_AR-daniela-high")
        if self.voice in {"daniela", "female"}:
            voices = ("es_AR-daniela-high", "es_MX-claude-high", "es_MX-ald-medium")
        elif self.voice in {"claude"}:
            voices = ("es_MX-claude-high", "es_MX-ald-medium", "es_AR-daniela-high")
        for name in voices:
            model = DATA_HOME / "voices" / f"{name}.onnx"
            if model.is_file() and model.with_suffix(".onnx.json").is_file():
                return model
        return None

    @contextmanager
    def waiting(self, enabled: bool = True, reason: str = ""):
        """Play a short spoken progress cue only for work likely to take time.

        The service decides whether it is warranted; keeping the timers here
        means the audio process is still cancelled immediately when Codex
        answers.
        """
        if not enabled:
            yield
            return
        guard = threading.Lock()
        ended = False
        cue = None
        cue_names = ("investigar", "segundo") if reason == "investigate" else ("momento", "segundo")
        cue_index = 0

        def play():
            nonlocal cue
            with guard, self.lock:
                if ended or self.kokoro_busy or (self.process and self.process.poll() is None):
                    return
                nonlocal cue_index
                clip = DATA_HOME / "voices/cues" / f"{cue_names[min(cue_index, len(cue_names) - 1)]}.wav"
                cue_index += 1
                if self.voice in KOKORO_VOICES and not self.configured:
                    clip = clip.parent / KOKORO_VOICES[self.voice] / clip.name
                model = self.piper_model() if not self.configured and self.voice not in KOKORO_VOICES else None
                if model and (clip.parent / model.stem / clip.name).is_file():
                    clip = clip.parent / model.stem / clip.name
                if clip.is_file() and shutil.which("pw-play"):
                    try:
                        cue = self.process = subprocess.Popen(
                            ["pw-play", str(clip)], stdout=subprocess.DEVNULL, start_new_session=True
                        )
                    except OSError:
                        return
                    threading.Thread(target=cue.wait, daemon=True).start()

        timers = [threading.Timer(delay, play) for delay in (1.5, 12)]
        for timer in timers:
            timer.daemon = True
            timer.start()
        try:
            yield
        finally:
            with guard:
                ended = True
                for timer in timers:
                    timer.cancel()
                if cue is not None and self.process is cue:
                    self.stop()

    def stop(self) -> None:
        with self.lock:
            if self.kokoro_busy and self.kokoro_process:
                try:
                    os.killpg(self.kokoro_process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                self.kokoro_process = None
                self.kokoro_busy = False
            if self.process and self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            self.process = None

    def speak(self, text: str) -> None:
        clean = spoken_metrics(spoken_text(text))
        if not clean:
            return
        if not self.configured and self.voice in KOKORO_VOICES:
            command = self._kokoro_command(KOKORO_VOICES[self.voice])
            if command:
                self.stop()
                with self.lock:
                    process = self._start_kokoro(command)
                    self.kokoro_busy = True
                    self.kokoro_started = monotonic()
                    self.first_audio_ms = None
                    threading.Thread(
                        target=self._send_kokoro, args=(process, clean), daemon=True,
                    ).start()
                return
        python = DATA_HOME / "piper-venv/bin/python"
        voice = DATA_HOME / "voices/es_MX-ald-medium.onnx"
        model = self.piper_model()
        kokoro = DATA_HOME / "voices/kokoro"
        player_available = python.is_file() and shutil.which("pw-play")
        kokoro_ready = player_available and all(
            (kokoro / asset).is_file() for asset in ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
        )
        if self.configured:
            command = shlex.split(self.configured) + [clean]
            input_text = None
        elif player_available and model:
            worker = Path(__file__).with_name("piper_play.py")
            command = [str(python), str(worker), str(model)]
            input_text = clean
        elif kokoro_ready:
            worker = Path(__file__).with_name("kokoro_play.py")
            command = [str(python), str(worker), str(kokoro), "ef_dora"]
            input_text = clean
        elif (
            player_available and voice.is_file() and voice.with_suffix(".onnx.json").is_file()
        ):
            worker = Path(__file__).with_name("piper_play.py")
            command = [str(python), str(worker), str(voice)]
            input_text = clean
        elif shutil.which("espeak-ng"):
            command = ["espeak-ng", "-v", os.environ.get("VOZ_CODEX_VOICE", "es"), "-s", "175", "--stdin"]
            input_text = clean
        else:
            return
        self.stop()
        with self.lock:
            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, start_new_session=True, text=True, encoding="utf-8",
            )
            threading.Thread(target=self.process.communicate, args=(input_text,), daemon=True).start()
