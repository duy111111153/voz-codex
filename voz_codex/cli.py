from __future__ import annotations

import argparse
import json
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
    sub.add_parser("serve"); sub.add_parser("toggle"); sub.add_parser("cancel"); sub.add_parser("status"); sub.add_parser("doctor")
    ask = sub.add_parser("ask"); ask.add_argument("text")
    search = sub.add_parser("chat-search"); search.add_argument("term")
    select = sub.add_parser("chat-select"); select.add_argument("thread_id")
    proj = sub.add_parser("index"); proj.add_argument("project"); proj.add_argument("root", type=Path); proj.add_argument("--description", default="")
    args = parser.parse_args()
    if args.command == "serve": Service().serve(); return 0
    if args.command == "doctor":
        config.ensure_dirs(); print(json.dumps({"python": sys.version.split()[0], "socket": str(config.SOCKET_FILE), "handy": bool(__import__('shutil').which('handy')), "codex": bool(__import__('shutil').which('codex')), "notify": bool(__import__('shutil').which('notify-send'))}, ensure_ascii=False)); return 0
    if args.command == "index":
        history = History(config.DB_FILE); print(json.dumps({"chunks": refresh(history, args.project, args.root, args.description)})); return 0
    if args.command == "toggle": print(json.dumps(call("toggle"), ensure_ascii=False)); return 0
    if args.command == "cancel": print(json.dumps(call("cancel"), ensure_ascii=False)); return 0
    if args.command == "status": print(json.dumps(call("status"), ensure_ascii=False)); return 0
    if args.command == "ask": print(json.dumps(call("ingest", text=args.text), ensure_ascii=False)); return 0
    if args.command == "chat-search": print(json.dumps(call("chat_search", term=args.term), ensure_ascii=False)); return 0
    if args.command == "chat-select": print(json.dumps(call("chat_select", thread_id=args.thread_id), ensure_ascii=False)); return 0
    parser.print_help(); return 2


if __name__ == "__main__":
    raise SystemExit(main())
