import unittest

from voz_codex.speech import spoken_metrics, spoken_text
from voz_codex.pronunciation import PHONEMES, piper_sentences


class SpokenTextTests(unittest.TestCase):
    def test_metrics_are_spoken_in_spanish(self):
        self.assertEqual(
            spoken_metrics("Quito está a 19 °C y la GPU usa 80% a 3.5 GHz."),
            "Quito está a diecinueve grados Celsius y la GPU usa ochenta por ciento a tres punto cinco gigahercios.",
        )

    def test_large_numbers_and_negative_temperature(self):
        self.assertEqual(spoken_metrics("Hay 125 archivos y -2 °C."), "Hay ciento veinticinco archivos y menos dos grados Celsius.")

    def test_screen_decorations_are_not_spoken(self):
        self.assertEqual(
            spoken_text("¡Hola! 😊 👩🏽‍💻 🇪🇨 1️⃣ :smile: **Quito** está a 19 °C."),
            "¡Hola! Quito está a 19 grados Celsius.",
        )

    def test_links_code_and_punctuation(self):
        self.assertEqual(spoken_text("[Pronóstico](https://example.com)."), "Pronóstico.")
        self.assertEqual(spoken_text("Texto. https://example.com"), "Texto.")
        self.assertEqual(spoken_text("👋 🧑‍💻"), "")
        self.assertEqual(spoken_text("Bien.\n```python\nprint(1)"), "Bien.")

    def test_wraps_are_joined_and_lists_keep_boundaries(self):
        self.assertEqual(
            spoken_text("Mira el video\nen YouTube.\n\n- Revisa NVIDIA\n- ¿Todo listo?"),
            "Mira el video en YouTube.\nRevisa NVIDIA.\n¿Todo listo?",
        )

    def test_names_get_phonemes_without_joining_sentences(self):
        supported = set("".join(PHONEMES.values()))
        self.assertEqual(
            list(piper_sentences("Mira YouTube. ¿Y NVIDIA?", supported)),
            [f"Mira [[{PHONEMES['youtube']}]].", f"¿Y [[{PHONEMES['nvidia']}]]?"],
        )
        self.assertEqual(list(piper_sentences("YouTube.", set())), ["YouTube."])
