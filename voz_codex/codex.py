from __future__ import annotations

import json
import queue
import shlex
import subprocess
import threading
from pathlib import Path
from time import monotonic
from typing import Callable

from . import config


class TurnInterrupted(RuntimeError):
    pass


# This bridge is explicitly user-authorized to run unattended. Keep the
# permission profile in one place so thread and turn requests cannot drift.
APPROVAL_POLICY = "never"
SANDBOX_MODE = "danger-full-access"
SANDBOX_POLICY = {"type": "dangerFullAccess"}


class CodexClient:
    def __init__(self, command: str, model: str = "", effort: str = "low"):
        self.command = shlex.split(command)
        self.model = model
        self.effort = effort
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.next_id = 1
        self.thread_id: str | None = None
        self.loaded_thread_id: str | None = None
        self.retry_app_server_at = 0.0
        self.turn_lock = threading.Lock()
        self.active_turn = None
        self.cancel_requested = False
        self.shared = False

    def _send(self, method: str, params: dict) -> dict:
        if not self.proc or self.proc.poll() is not None:
            self.loaded_thread_id = None
            python = config.DATA_HOME / "tracker-venv/bin/python"
            self.shared = self.command[1:] == ["app-server", "--stdio"] and python.is_file() and config.CODEX_SOCKET.is_socket()
            command = ([str(python), str(Path(__file__).with_name("daemon_bridge.py")), str(config.CODEX_SOCKET)]
                       if self.shared else self.command)
            self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
            self.events = queue.Queue(maxsize=256)
            threading.Thread(target=self._read_events, args=(self.proc, self.events), daemon=True).start()
            self._request("initialize", {"clientInfo": {"name": "voz-codex", "title": "Voz Codex", "version": "0.1.0"}})
            self.proc.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
        return self._request(method, params)

    @staticmethod
    def _read_events(process, events) -> None:
        with process.stdout:
            for line in process.stdout:
                events.put(line)
        events.put(None)

    def _event(self, timeout: float) -> dict:
        try:
            line = self.events.get(timeout=max(timeout, 0))
        except queue.Empty as exc:
            raise RuntimeError("Codex App Server excedió el tiempo de espera") from exc
        if line is None:
            raise RuntimeError("Codex App Server cerró la conexión")
        return json.loads(line)

    def _request(self, method: str, params: dict) -> dict:
        request_id = self.next_id
        self.next_id += 1
        self.proc.stdin.write(json.dumps({"method": method, "id": request_id, "params": params}) + "\n")
        self.proc.stdin.flush()
        deadline = monotonic() + 5
        while True:
            event = self._event(deadline - monotonic())
            if event.get("id") == request_id:
                if "error" in event:
                    raise RuntimeError(str(event["error"]))
                return event.get("result", {})

    def list_threads(self, search: str = "") -> list[dict]:
        with self.lock:
            result = self._send("thread/list", {"limit": 50, "searchTerm": search})
        return result.get("data", []) if result else []

    def start_thread(self, cwd: str | None = None) -> str:
        with self.lock:
            params = {"model": self.model or "gpt-5.6-luna", "approvalPolicy": APPROVAL_POLICY, "sandbox": SANDBOX_MODE}
            if cwd:
                params["cwd"] = cwd
            result = self._send("thread/start", params) or {}
            self.thread_id = result.get("thread", {}).get("id") or result.get("threadId")
            self.loaded_thread_id = self.thread_id
        if not self.thread_id:
            raise RuntimeError("Codex no devolvió threadId")
        return self.thread_id

    def resume(self, thread_id: str) -> str:
        with self.lock:
            result = self._send("thread/resume", {"threadId": thread_id, "excludeTurns": True}) or {}
            self.thread_id = result.get("thread", {}).get("id", thread_id)
            self.loaded_thread_id = self.thread_id
        return self.thread_id

    def set_thread(self, thread_id: str | None) -> None:
        """Select a durable thread; the App Server connection is opened lazily."""
        with self.lock:
            self.thread_id = thread_id or None

    def ask(self, text: str, on_delta: Callable[[str], None], cwd: str | None = None,
            *, image: Path | None = None, on_progress=None) -> tuple[str, str]:
        try:
            return self._ask(text, on_delta, cwd, image, on_progress)
        finally:
            with self.turn_lock:
                self.active_turn = None
                self.cancel_requested = False

    def interrupt(self) -> None:
        with self.turn_lock:
            self.cancel_requested = True
            self._interrupt_active()

    def _interrupt_active(self) -> None:
        if self.active_turn and self.cancel_requested:
            thread_id, turn_id = self.active_turn
            packet = {"id": "voz-interrupt", "method": "turn/interrupt",
                      "params": {"threadId": thread_id, "turnId": turn_id}}
            self.proc.stdin.write(json.dumps(packet) + "\n")
            self.proc.stdin.flush()
            self.cancel_requested = False

    def _ask(self, text, on_delta, cwd, image, on_progress):
        if not self.thread_id:
            if monotonic() < self.retry_app_server_at:
                return self._fallback(text, cwd, image=image)
            try:
                self.start_thread(cwd)
            except (OSError, RuntimeError, ValueError):
                self.close()
                self.retry_app_server_at = monotonic() + 60
                return self._fallback(text, cwd, image=image)
        elif self.loaded_thread_id != self.thread_id or self._transport_closed():
            # A selected thread survives daemon restarts, but its transport does not.
            # Resume it before writing turn/start; never silently fork a new chat.
            selected = self.thread_id
            try:
                self.resume(selected)
            except (OSError, RuntimeError, ValueError) as error:
                self.close()
                if "thread not found" in str(error).casefold():
                    raise
                raise RuntimeError(f"No se pudo reanudar el chat {selected}")

        with self.lock:
            with self.turn_lock:
                if self.cancel_requested:
                    raise TurnInterrupted("Tarea cancelada.")
            request_id = self.next_id
            self.next_id += 1
            params = {"threadId": self.thread_id, "input": [{"type": "text", "text": text}],
                      "sandboxPolicy": SANDBOX_POLICY, "approvalPolicy": APPROVAL_POLICY,
                      "effort": self.effort}
            if image is not None:
                params["input"].append({"type": "localImage", "path": str(image)})
                params["effort"] = "low"
            if self.model:
                params["model"] = self.model
            self.proc.stdin.write(json.dumps({"method": "turn/start", "id": request_id, "params": params}) + "\n")
            self.proc.stdin.flush()
            turn_id = ""
            final_items = set()
            answer_parts = {}
            deadline = monotonic() + 105
            while True:
                event = self._event(deadline - monotonic())
                method = event.get("method", "")
                params_event = event.get("params", {})
                if event.get("id") == request_id and event.get("result"):
                    turn_id = event["result"].get("turn", {}).get("id", turn_id)
                    if turn_id:
                        with self.turn_lock:
                            self.active_turn = (self.thread_id, turn_id)
                            self._interrupt_active()
                        if on_progress:
                            on_progress("Codex está preparando la respuesta.")
                if params_event.get("threadId") != self.thread_id and method:
                    continue
                if method == "item/started" and params_event.get("turnId") == turn_id:
                    item = params_event.get("item", {})
                    stage = {"commandExecution": "Ejecutando un comando.", "webSearch": "Buscando información.",
                             "fileChange": "Aplicando cambios en archivos.", "mcpToolCall": "Consultando una herramienta.",
                             "dynamicToolCall": "Consultando una herramienta."}.get(item.get("type"))
                    if stage and on_progress:
                        on_progress(stage)
                    if item.get("type") == "agentMessage" and item.get("phase") == "final_answer":
                        final_items.add(item.get("id"))
                if method == "item/agentMessage/delta":
                    if params_event.get("turnId") != turn_id:
                        continue
                    delta = params_event.get("delta", "")
                    if delta and params_event.get("itemId") in final_items:
                        on_delta(delta)
                if method == "item/completed" and params_event.get("turnId") == turn_id:
                    item = params_event.get("item", {})
                    if item.get("type") == "agentMessage" and item.get("phase") == "commentary" and on_progress:
                        on_progress(item.get("text") or "Codex sigue trabajando.")
                if method == "item/completed" and params_event.get("turnId") == turn_id:
                    item = params_event.get("item", {})
                    if item.get("type") == "agentMessage" and item.get("phase") != "commentary":
                        answer_parts[item["id"]] = item.get("text", "")
                if method == "turn/completed":
                    turn = params_event.get("turn", {})
                    if turn.get("id") != turn_id:
                        continue
                    if turn.get("status") == "interrupted":
                        raise TurnInterrupted("Tarea cancelada.")
                    if turn.get("status") != "completed":
                        raise RuntimeError("Codex no completó el turno")
                    break
                if event.get("id") == request_id and event.get("error"):
                    raise RuntimeError(str(event["error"]))
            return turn_id, "\n\n".join(filter(None, answer_parts.values()))

    def _transport_closed(self) -> bool:
        """Treat test doubles and live transports consistently."""
        status = self.proc.poll() if self.proc is not None else 0
        return isinstance(status, int) and status is not None

    def _fallback(self, text: str, cwd: str | None = None,
                  *, image: Path | None = None) -> tuple[str, str]:
        """Use the authenticated non-interactive client if App Server is disabled."""
        command = [
            self.command[0], "exec", "--json", "--skip-git-repo-check",
            "--sandbox", SANDBOX_MODE, "--ask-for-approval", APPROVAL_POLICY,
            "--model", self.model or "gpt-5.6-luna",
            "-c", f"model_reasoning_effort={json.dumps('low' if image else self.effort)}",
        ]
        if image is not None:
            command.extend(["--image", str(image)])
        command.extend(["--", "-"])
        result = subprocess.run(command, cwd=cwd, input=text, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, timeout=110)
        if result.returncode:
            raise RuntimeError("Codex CLI no completó la consulta")
        answer_parts = []
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                self.thread_id = event.get("thread_id")
            item = event.get("item", {})
            if (event.get("type") == "item.completed" and item.get("type") == "agent_message"
                    and item.get("phase") != "commentary" and item.get("text")):
                answer_parts.append(item["text"])
        return "", "\n\n".join(answer_parts)

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None
        self.thread_id = None
        self.loaded_thread_id = None
