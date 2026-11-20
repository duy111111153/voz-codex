"""Synthesize and play one phrase at a time with Kokoro."""

import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import onnxruntime as ort
from kokoro_onnx import Kokoro

from pronunciation import NAMES


ENGLISH = set(
    "the this that these those you your it it's is are was were will would could should "
    "please thanks thank hello good morning welcome today tomorrow how what where when "
    "open close check click save restart run install download update works ready "
    "and or with from for into on of a an our have has can not all next first "
    "step settings file browser website name example test".split()
)
SPANISH = set(
    "el la los las un una de del en con por para que esto esta está y o si sí "
    "abre revisa funciona gracias puedes una es al pero tu su se lo".split()
)


def bilingual_phonemes(text, phonemize):
    fragments = re.split(r'([,;:!?“”"–—]|\s+\by\b\s+)', text)
    result = []
    for fragment in fragments:
        words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", fragment.casefold())
        english = sum(word in ENGLISH for word in words)
        spanish = sum(word in SPANISH for word in words)
        if english >= 2 and english > spanish:
            result.append(phonemize(fragment, "en-us"))
        elif not any(char.isalnum() for char in fragment):
            result.append(fragment.strip())
        else:
            start = 0
            for name in NAMES.finditer(fragment):
                if fragment[start:name.start()].strip():
                    result.append(phonemize(fragment[start:name.start()], "es"))
                result.append(phonemize(name[0], "en-us"))
                start = name.end()
            if fragment[start:].strip():
                result.append(phonemize(fragment[start:], "es"))
    return re.sub(r"\s+([,;:.!?])", r"\1", " ".join(filter(None, result))).strip()


def phrases(text):
    for line in text.splitlines():
        parts = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", line) if part.strip()]
        for index, part in enumerate(parts):
            if len(part) > 95:
                boundary = re.search(r"[,;:]\s+", part[28:95])
                if boundary:
                    end = 28 + boundary.end()
                    yield part[:end].strip(), 0.10
                    part = part[end:]
            yield part, 0.22 if index == len(parts) - 1 else 0.13


def load_voice(models: Path):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    session = ort.InferenceSession(
        str(models / "kokoro-v1.0.int8.onnx"), options, providers=["CPUExecutionProvider"]
    )
    return Kokoro.from_session(session, str(models / "voices-v1.0.bin"))


def make_synthesizer(tts, voice):
    @lru_cache(maxsize=16)
    def cached(phrase):
        return synthesize(phrase)

    def synthesize(phrase):
        phonemes = bilingual_phonemes(phrase, tts.tokenizer.phonemize)
        phonemes = "".join(char for char in phonemes if char in tts.tokenizer.vocab)
        if not any(char.isalpha() for char in phonemes):
            return b"", 24000
        audio, rate = tts.create(phonemes, voice=voice, speed=1.04, is_phonemes=True)
        pcm = np.rint(np.clip(audio, -1, 1) * 29490).astype("<i2").tobytes()
        return pcm, rate

    return lambda phrase: cached(phrase) if len(phrase) <= 48 else synthesize(phrase)


def audio_chunks(tts, text, voice, synthesize=None):
    synthesize = synthesize or make_synthesizer(tts, voice)
    pause = 0
    for phrase, next_pause in phrases(text):
        pcm, rate = synthesize(phrase)
        if not pcm:
            continue
        yield bytes(round(rate * pause) * 2) + pcm, rate
        pause = next_pause


def render(text: str, models: Path, voice: str) -> tuple[bytes, int]:
    chunks = list(audio_chunks(load_voice(models), text, voice))
    return (b"".join(pcm for pcm, _ in chunks), chunks[0][1]) if chunks else (b"", 24000)


def play(chunks, on_first=None) -> int:
    chunks = iter(chunks)
    first = next(chunks, None)
    if first is None:
        return 0
    pcm, rate = first
    if on_first:
        on_first()
    with subprocess.Popen(
        ["pw-play", "--raw", "--format", "s16", "--channels", "1",
         "--rate", str(rate), "--latency", "150ms", "-"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
    ) as player:
        try:
            with player.stdin as stream:
                stream.write(pcm)
                stream.flush()
                for pcm, _ in chunks:
                    stream.write(pcm)
                    stream.flush()
        except BrokenPipeError:
            return player.wait() or 1
        return player.wait()


def main() -> int:
    models, voice = Path(sys.argv[1]), sys.argv[2]
    if "--serve" in sys.argv[3:]:
        tts = load_voice(models)
        synthesize = make_synthesizer(tts, voice)
        synthesize("Hola.")
        print("ready", flush=True)
        for line in sys.stdin:
            try:
                result = play(
                    audio_chunks(tts, json.loads(line), voice, synthesize),
                    on_first=lambda: print("audio", flush=True),
                )
            except Exception as error:
                print(f"Kokoro: {error}", file=sys.stderr)
                result = 1
            print(f"done {result}", flush=True)
        return 0
    text = sys.stdin.read().strip()
    return play(audio_chunks(load_voice(models), text, voice)) if text else 0


if __name__ == "__main__":
    raise SystemExit(main())
