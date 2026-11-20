"""Synthesize ahead of playback so slow sentences have time to finish."""
import queue
import subprocess
import sys
import threading
import wave
import shutil
from pathlib import Path

from piper import PiperVoice, SynthesisConfig
from pronunciation import piper_sentences


SETTINGS = SynthesisConfig(length_scale=1.03, volume=0.96)
CUES = {
    "momento": "Un momento.",
    "segundo": "Dame un segundo.",
    "revisar": "Déjame revisar eso.",
    "investigar": "Déjame investigar un momento.",
}


def cache_cues(voice, target: Path) -> None:
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, phrase in CUES.items():
        temporary = target / f"{name}.wav.tmp"
        with wave.open(str(temporary), "wb") as stream:
            stream.setparams((1, 2, voice.config.sample_rate, 0, "NONE", "not compressed"))
            for chunk in voice.synthesize(phrase, syn_config=SETTINGS):
                stream.writeframes(chunk.audio_int16_bytes)
        temporary.replace(target / f"{name}.wav")


def audio_chunks(voice, text: str):
    sentences = list(piper_sentences(text, voice.config.phoneme_id_map))
    for index, sentence in enumerate(sentences):
        for chunk in voice.synthesize(sentence, syn_config=SETTINGS):
            yield chunk.audio_int16_bytes
        # A small, fixed boundary prevents adjacent synthesized sentences from
        # running together while keeping commas and natural intra-sentence
        # phrasing under Piper's control.
        if index < len(sentences) - 1:
            yield b"\x00" * int(voice.config.sample_rate * 0.14) * 2


def play(voice, text: str) -> int:
    chunks = queue.Queue(maxsize=12)

    def synthesize():
        try:
            for chunk in audio_chunks(voice, text):
                chunks.put(chunk)
        except Exception as error:
            chunks.put(error)
        finally:
            chunks.put(None)

    def next_chunk():
        chunk = chunks.get()
        if isinstance(chunk, Exception):
            raise chunk
        return chunk

    threading.Thread(target=synthesize, daemon=True).start()
    rate = voice.config.sample_rate
    audio = bytearray()
    while len(audio) < rate * 5:
        chunk = next_chunk()
        if chunk is None:
            break
        audio.extend(chunk)
    if not audio:
        return 0

    # A very small downward pitch shift gives the male voice a little body
    # without making words muddy. Tempo is restored so pauses stay natural.
    pitch = 0.96
    ffmpeg = shutil.which("ffmpeg")
    processor = None
    if ffmpeg:
        processor = subprocess.Popen(
            [ffmpeg, "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "-",
             "-af", f"asetrate={rate * pitch:.2f},aresample={rate},atempo={1 / pitch:.6f}",
             "-f", "s16le", "-ac", "1", "-ar", str(rate), "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        player_input = processor.stdin
    else:
        player_input = None
    with subprocess.Popen(
        ["pw-play", "--raw", "--format", "s16", "--channels", "1",
         "--rate", str(rate), "--latency", "150ms", "-"],
        stdin=subprocess.PIPE,
    ) as player:
        if processor:
            def forward():
                try:
                    while True:
                        data = processor.stdout.read(8192)
                        if not data:
                            break
                        player.stdin.write(data)
                        player.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    try:
                        player.stdin.close()
                    except OSError:
                        pass
            threading.Thread(target=forward, daemon=True).start()
            player_input = processor.stdin
        else:
            player_input = player.stdin
        try:
            with player_input as stream:
                stream.write(audio)
                stream.flush()
                while chunk is not None:
                    chunk = next_chunk()
                    if chunk is None:
                        break
                    stream.write(chunk)
                    stream.flush()
                # Let the sink consume its final buffer before EOF.
                # s16le frames are two bytes; keep the drain buffer frame-aligned.
                stream.write(bytes((rate // 2) * 2))
        except BrokenPipeError:
            if processor:
                processor.kill()
            return player.wait() or 1
        if processor:
            processor.wait()
        return player.wait()


def main() -> int:
    voice = PiperVoice.load(sys.argv[1])
    if len(sys.argv) == 4 and sys.argv[2] == "--cache-cues":
        cache_cues(voice, Path(sys.argv[3]))
        return 0
    text = sys.stdin.read().strip()
    if text and len(sys.argv) == 4 and sys.argv[2] == "--wav":
        with wave.open(sys.argv[3], "wb") as stream:
            stream.setparams((1, 2, voice.config.sample_rate, 0, "NONE", "not compressed"))
            for chunk in audio_chunks(voice, text):
                stream.writeframes(chunk)
        return 0
    return play(voice, text) if text else 0


if __name__ == "__main__":
    raise SystemExit(main())
