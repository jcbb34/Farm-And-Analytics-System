"""Run the API with graceful, launcher-owned process control."""
import argparse
import os
from pathlib import Path
import sys
from threading import Thread

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.server_lifecycle import drain_streams, resume_streams


class FarmServer(uvicorn.Server):
    def handle_exit(self, sig, frame):
        # Uvicorn waits for streaming responses *before* lifespan shutdown.
        # Finish them here so a live browser cannot keep shutdown open forever.
        drain_streams()
        super().handle_exit(sig, frame)


def receive_control(server, stream):
    for line in stream:
        command = line.strip()
        if command == "drain":
            drain_streams()
        elif command == "resume":
            resume_streams()
        elif command == "stop":
            break
    # A closed pipe also means the launcher has exited. Release the API port
    # and run normal Uvicorn/lifespan cleanup rather than orphaning the server.
    drain_streams()
    server.should_exit = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    resume_streams()
    server = FarmServer(uvicorn.Config(
        "app.main:app", host=args.host, port=args.port,
        timeout_graceful_shutdown=15,
    ))
    if os.environ.get("JOROSS_LAUNCHER_CONTROL") == "1":
        Thread(target=receive_control, args=(server, sys.stdin), daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
