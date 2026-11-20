import subprocess
import threading
import unittest
from unittest.mock import patch

from voz_codex.overlay import Overlay


class OverlayTests(unittest.TestCase):
    def test_replaces_card_and_skips_identical_final(self):
        calls = []
        arrived = threading.Condition()

        def send(command, **kwargs):
            with arrived:
                calls.append(command)
                arrived.notify_all()
            return subprocess.CompletedProcess(command, 0, stdout="42\n")

        def wait_for(count):
            with arrived:
                self.assertTrue(arrived.wait_for(lambda: len(calls) >= count, timeout=2))

        with patch("voz_codex.overlay.subprocess.run", side_effect=send):
            overlay = Overlay()
            overlay.show("Codex", "Respondiendo")
            wait_for(1)
            overlay.show("Codex", "**Hola** <mundo>")
            wait_for(2)
            overlay.show("Codex", "**Hola** <mundo>")
            overlay.show("Codex", "Siguiente")
            wait_for(3)
        self.assertEqual(len(calls), 3)
        self.assertIn("--replace-id=0", calls[0])
        self.assertIn("--replace-id=42", calls[1])
        self.assertEqual(calls[1][-1], "Hola &lt;mundo&gt;")
