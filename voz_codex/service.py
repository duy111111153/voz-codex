from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path

from . import config
from .codex import CodexClient
from .history import History
from .overlay import show
from .speech import Speech


class Service:
    def __init__(self):
        self.settings = config.load()
        self.history = History(config.DB_FILE)
        self.history.project(self.settings["project"])
        self.codex = CodexClient(self.settings["codex_command"], self.settings.get("model", ""))
        self.speech = Speech(self.settings.get("speech_command", ""))
        self.capture = False
        self.lock = threading.Lock()

    def notify(self, title: str, text: str) -> None:
        show(title, text)

    def toggle(self) -> dict:
        with self.lock:
            self.capture = not self.capture
            state = "Escuchando" if self.capture else "Procesando transcripción"
        self.notify("Voz Codex", state)
        os.spawnlp(os.P_NOWAIT, "handy", "handy", "--toggle-transcription")
        return {"state": state}

    def ingest(self, text: str) -> dict:
        with self.lock:
            self.capture = False
        text = text.strip()
        if not text:
            self.notify("Voz Codex", "No se detectó texto")
            return {"state": "empty"}
        self.notify("Tú", text)
        thread_id = self.codex.thread_id or "local-exec"
        self.history.thread(thread_id, self.settings["project"], source="codex-exec" if thread_id == "local-exec" else "codex")
        self.history.message(thread_id, None, "user", text)
        response = []
        self.notify("Codex", "Respondiendo…")
        def delta(value: str) -> None:
            response.append(value)
            if len("".join(response)) <= 360:
                show("Codex", "".join(response))
        turn_id, answer = self.codex.ask(text, delta, os.getcwd())
        thread_id = self.codex.thread_id or thread_id
        self.history.thread(thread_id, self.settings["project"], source="codex" if self.codex.thread_id else "codex-exec")
        self.history.message(thread_id, turn_id, "assistant", answer)
        if answer:
            self.speech.speak(answer)
            self.notify("Codex", answer)
        return {"state": "done", "thread_id": thread_id, "turn_id": turn_id, "answer": answer}

    def cancel(self) -> dict:
        self.speech.stop()
        try:
            self.codex.close()
        except Exception:
            pass
        self.notify("Voz Codex", "Cancelado")
        return {"state": "cancelled"}

    def handle(self, request: dict) -> dict:
        command = request.get("command")
        if command == "toggle": return self.toggle()
        if command == "ingest": return self.ingest(str(request.get("text", "")))
        if command == "cancel": return self.cancel()
        if command == "status": return {"capture": self.capture, "thread_id": self.codex.thread_id, "project": self.settings["project"]}
        if command == "chat_search": return {"threads": self.history.search_threads(str(request.get("term", "")))}
        if command == "chat_select": return {"thread_id": self.codex.resume(str(request["thread_id"]))}
        return {"error": f"unknown command: {command}"}

    def serve(self) -> None:
        config.ensure_dirs()
        if config.SOCKET_FILE.exists(): config.SOCKET_FILE.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(config.SOCKET_FILE)); config.SOCKET_FILE.chmod(0o600); server.listen(8)
        self.notify("Voz Codex", "Listo")
        while True:
            conn, _ = server.accept()
            with conn:
                data = conn.recv(1024 * 64)
                try: result = self.handle(json.loads(data.decode()))
                except Exception as error:
                    result = {"error": str(error)}; self.notify("Voz Codex", str(error))
                conn.sendall(json.dumps(result, ensure_ascii=False).encode())
