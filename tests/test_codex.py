import json
import unittest
from unittest.mock import Mock

from voz_codex.codex import CodexClient


class CodexTests(unittest.TestCase):
    def test_answer_keeps_all_parts_and_ignores_commentary(self):
        client = CodexClient("codex app-server")
        client.thread_id = "chat"
        client.loaded_thread_id = "chat"
        client.proc = Mock()

        def notice(method, **params):
            return {"method": method, "params": {"threadId": "chat", **params}}

        def message(item_id, phase, text):
            return notice("item/completed", turnId="turn", item={
                "id": item_id, "type": "agentMessage", "phase": phase, "text": text,
            })

        client._event = Mock(side_effect=[
            {"id": 1, "result": {"turn": {"id": "turn"}}},
            notice("item/agentMessage/delta", turnId="turn", itemId="2", delta="Voy a consultar otros chats."),
            message("1", "partial_answer", "Primera parte."),
            message("2", "commentary", "Estoy revisando."),
            notice("item/started", turnId="turn", item={"id": "3", "type": "agentMessage", "phase": "final_answer"}),
            notice("item/agentMessage/delta", turnId="turn", itemId="3", delta="Última frase."),
            message("3", "final_answer", "Última frase."),
            notice("turn/completed", turn={"id": "turn", "status": "completed"}),
        ])
        preview = []
        self.assertEqual(
            client.ask("Prueba", preview.append),
            ("turn", "Primera parte.\n\nÚltima frase."),
        )
        self.assertEqual(preview, ["Última frase."])
        params = json.loads(client.proc.stdin.write.call_args.args[0])["params"]
        self.assertEqual(params["effort"], "low")
