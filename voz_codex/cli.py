from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
from pathlib import Path

from . import config
from .history import History
from .rag import refresh
from .service import Service


def call(command: str, **payload):
    config.ensure_dirs()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(120); sock.connect(str(config.SOCKET_FILE))
        sock.sendall(json.dumps({"command": command, **payload}).encode())
        return json.loads(sock.recv(1024 * 128).decode())


def main() -> int:
    parser = argparse.ArgumentParser(prog="voz-codex")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve"); sub.add_parser("toggle"); sub.add_parser("status"); sub.add_parser("doctor")
    cancel = sub.add_parser("cancel"); cancel.add_argument("--task-id")
    follow = sub.add_parser("follow"); follow.add_argument("task_id")
    ask = sub.add_parser("ask"); ask.add_argument("text")
    search = sub.add_parser("chat-search"); search.add_argument("term")
    sub.add_parser("chat-sync")
    select = sub.add_parser("chat-select"); select.add_argument("thread_id")
    route = sub.add_parser("chat-route"); route.add_argument("text"); route.add_argument("--dry-run", action="store_true")
    sub.add_parser("chat-current")
    new_topic = sub.add_parser("chat-new"); new_topic.add_argument("topic")
    sub.add_parser("topic-list")
    alias = sub.add_parser("topic-alias"); alias.add_argument("topic_id"); alias.add_argument("alias")
    sub.add_parser("graph-export")
    proj = sub.add_parser("index"); proj.add_argument("project"); proj.add_argument("root", type=Path); proj.add_argument("--description", default="")
    args = parser.parse_args()
    if args.command == "serve": Service().serve(); return 0
    if args.command == "doctor":
        config.ensure_dirs(); print(json.dumps({"python": sys.version.split()[0], "socket": str(config.SOCKET_FILE), "handy": bool(__import__('shutil').which('handy')), "codex": bool(__import__('shutil').which('codex')), "notify": bool(__import__('shutil').which('notify-send'))}, ensure_ascii=False)); return 0
    if args.command == "index":
        history = History(config.DB_FILE); print(json.dumps({"chunks": refresh(history, args.project, args.root, args.description)})); return 0
    if args.command == "toggle": print(json.dumps(call("toggle"), ensure_ascii=False)); return 0
    if args.command == "cancel": print(json.dumps(call("cancel", task_id=args.task_id), ensure_ascii=False)); return 0
    if args.command == "follow":
        task = json.loads(config.TASK_FILE.read_text(encoding="utf-8"))
        thread_id = task.get("thread_id") or ""
        if task.get("id") != args.task_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", thread_id):
            return 2
        command = ["omarchy", "launch", "terminal", "codex", "resume"]
        if task.get("shared"):
            command += ["--remote", f"unix://{config.CODEX_SOCKET}"]
        return subprocess.call([*command, thread_id])
    if args.command == "status": print(json.dumps(call("status"), ensure_ascii=False)); return 0
    if args.command == "ask": print(json.dumps(call("ingest", text=args.text), ensure_ascii=False)); return 0
    if args.command == "chat-search": print(json.dumps(call("chat_search", term=args.term), ensure_ascii=False)); return 0
    if args.command == "chat-sync": print(json.dumps(call("chat_sync"), ensure_ascii=False)); return 0
    if args.command == "chat-select": print(json.dumps(call("chat_select", thread_id=args.thread_id), ensure_ascii=False)); return 0
    if args.command == "chat-route": print(json.dumps(call("chat_route", text=args.text), ensure_ascii=False)); return 0
    if args.command == "chat-current":
        print(json.dumps(call("status"), ensure_ascii=False)); return 0
    if args.command == "chat-new":
        history = History(config.DB_FILE)
        topic_id = "topic-" + re.sub(r"[^a-z0-9]+", "-", args.topic.casefold()).strip("-")[:48]
        history.topic(topic_id, args.topic); print(json.dumps({"topic_id": topic_id, "topic": args.topic}, ensure_ascii=False)); return 0
    if args.command == "topic-list": print(json.dumps(call("topic_list"), ensure_ascii=False)); return 0
    if args.command == "topic-alias": print(json.dumps(call("topic_alias", topic_id=args.topic_id, alias=args.alias), ensure_ascii=False)); return 0
    if args.command == "graph-export": print(json.dumps(call("graph_export"), ensure_ascii=False)); return 0
    parser.print_help(); return 2


if __name__ == "__main__":
    raise SystemExit(main())
