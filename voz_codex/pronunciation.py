"""Pronunciations for common names in otherwise Spanish speech."""
import re


PHONEMES = {
    "youtube": "jˈuːtˌuːb",
    "nvidia": "ɛn vˈɪdiə",
    "github": "ɡˈɪthʌb",
    "python": "pˈaɪθən",
    "openai": "ˈoʊpən eɪ ˈaɪ",
    "windows": "wˈɪndoʊz",
    "codex": "kˈoʊdɛks",
    "linux": "lˈɪnʊks",
    "docker": "dˈɑkər",
    "javascript": "dʒˈævəskrɪpt",
    "typescript": "tˈaɪpskrɪpt",
    "google": "ɡˈuːɡəl",
    "chatgpt": "tʃˈæt dʒiː pˈiː tˈiː",
    "api": "eɪ pˈiː ˈaɪ",
    "cpu": "sˈiː pˈiː jˈuː",
    "gpu": "dʒˈiː pˈiː jˈuː",
    "json": "dʒˈeɪsən",
    "sql": "ˈɛs kjuː ˈɛl",
    "ubuntu": "ʊbˈʊntuː",
}
NAMES = re.compile(r"\b(?:" + "|".join(re.escape(name) for name in PHONEMES) + r")\b", re.IGNORECASE)


def piper_sentences(text, phoneme_map):
    # Keep phoneme overrides inside one sentence so Piper cannot join adjacent sentences.
    # A lowercase sentence after punctuation is common in dictated text, so do
    # not require an uppercase letter here.
    paragraphs = re.split(r"\n+", text)
    for paragraph in paragraphs:
        for sentence in re.split(r"(?<=[.!?…])\s+(?=[¿¡A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9])", paragraph):
            sentence = sentence.strip().replace("[[", "[").replace("]]", "]")
            if not sentence:
                continue

            def replace(match):
                sounds = PHONEMES[match[0].lower()]
                return f"[[{sounds}]]" if all(sound in phoneme_map for sound in sounds) else match[0]

            yield NAMES.sub(replace, sentence)
