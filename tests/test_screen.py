import unittest

from voz_codex.screen import wants_screen


class ScreenIntentTests(unittest.TestCase):
    def test_explicit_requests(self):
        for text in (
            "¿Qué ves en pantalla?",
            "¿Qué me puedes decir de lo que ves en pantalla?",
            "Mira mi pantalla y explícame el error.",
            "Lee lo que hay en mi pantalla.",
        ):
            with self.subTest(text=text):
                self.assertTrue(wants_screen(text))

    def test_other_requests(self):
        for text in (
            "Hola.",
            "¿Hay una forma de bloquear la pantalla?",
            "Por favor no mires mi pantalla.",
            "Explícame qué es una pantalla OLED.",
        ):
            with self.subTest(text=text):
                self.assertFalse(wants_screen(text))
