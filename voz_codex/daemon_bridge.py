"""Bridge the shared Codex Unix WebSocket to the existing JSON-line client."""

import socket
import sys
import threading

import websocket


def main():
    local = socket.socket(socket.AF_UNIX)
    local.connect(sys.argv[1])
    remote = websocket.create_connection(
        "ws://localhost/", socket=local, timeout=5, suppress_origin=True,
    )
    remote.settimeout(None)

    def forward():
        try:
            for line in sys.stdin:
                remote.send(line.rstrip("\n"))
        finally:
            remote.shutdown()

    threading.Thread(target=forward, daemon=True).start()
    try:
        while message := remote.recv():
            print(message, flush=True)
    finally:
        remote.shutdown()


if __name__ == "__main__":
    main()
