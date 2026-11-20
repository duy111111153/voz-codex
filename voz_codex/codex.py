from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
import threading
import uuid
from typing import Callable


class CodexClient:
    def __init__(self, command: str, model: str = ""):
        self.command = shlex.split(command)
        self.model = model
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.next_id = 1
        self.thread_id: str | None = None

    def _send(self, method: str, params: dict, wait_id: int | None = None) -> dict | None:
        if not self.proc:
            self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
            self.proc.stdin.write(json.dumps({"method": "initialize", "id": 1, "params": {"clientInfo": {"name": "voz-codex", "title": "Voz Codex", "version": "0.1.0"}}}) + "\n")
            self.proc.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
            self.proc.stdin.flush()
        request_id = wait_id or self.next_id
        self.next_id = max(self.next_id, request_id + 1)
        self.proc.stdin.write(json.dumps({"method": method, "id": request_id, "params": params}) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("Codex App Server cerró la conexión")
            event = json.loads(line)
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
            params = {"model": self.model or "gpt-5.6-luna", "approvalPolicy": "on-request", "sandbox": "workspace-write"}
            if cwd:
                params["cwd"] = cwd
            result = self._send("thread/start", params) or {}
            self.thread_id = result.get("thread", {}).get("id") or result.get("threadId")
        if not self.thread_id:
            raise RuntimeError("Codex no devolvió threadId")
        return self.thread_id

    def resume(self, thread_id: str) -> str:
        with self.lock:
            result = self._send("thread/resume", {"threadId": thread_id}) or {}
            self.thread_id = result.get("thread", {}).get("id", thread_id)
        return self.thread_id

    def ask(self, text: str, on_delta: Callable[[str], None], cwd: str | None = None) -> tuple[str, str]:
        if not self.thread_id:
            try:
                self.start_thread(cwd)
            except Exception:
                return self._fallback(text, on_delta, cwd)
        if not self.thread_id:
            return self._fallback(text, on_delta, cwd)
        with self.lock:
            request_id = self.next_id
            self.next_id += 1
            params = {"threadId": self.thread_id, "input": [{"type": "text", "text": text}]}
            if self.model:
                params["model"] = self.model
            self.proc.stdin.write(json.dumps({"method": "turn/start", "id": request_id, "params": params}) + "\n")
            self.proc.stdin.flush()
            turn_id = ""
            result_text = []
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    raise RuntimeError("Codex App Server cerró la conexión durante la respuesta")
                event = json.loads(line)
                method = event.get("method", "")
                params_event = event.get("params", {})
                if method == "item/agentMessage/delta":
                    delta = params_event.get("delta", "")
                    if delta:
                        result_text.append(delta)
                        on_delta(delta)
                if method == "turn/started":
                    turn_id = params_event.get("turn", {}).get("id", turn_id)
                if method == "turn/completed":
                    turn_id = params_event.get("turnId", turn_id)
                    break
                if event.get("id") == request_id and event.get("error"):
                    raise RuntimeError(str(event["error"]))
            return turn_id, "".join(result_text)

    def _fallback(self, text: str, on_delta: Callable[[str], None], cwd: str | None = None) -> tuple[str, str]:
        """Use the authenticated non-interactive client if App Server is disabled."""
        command = [self.command[0], "exec", "--json", "--skip-git-repo-check", "--sandbox", "read-only", "--model", self.model or "gpt-5.6-luna", text]
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        answer = ""
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                answer = item.get("text", "")
        process.wait(timeout=120)
        if answer:
            on_delta(answer)
        return "", answer

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
