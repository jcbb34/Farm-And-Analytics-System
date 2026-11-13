"""Run the farm on this computer and show a phone-ready link for the current LAN."""

import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "Jorros Backend"
FRONTEND = ROOT / "Jorros Frontend"

# Shared discovery is lightweight and does not import database settings.
sys.path.insert(0, str(BACKEND))
from app.services.phone_access import lan_addresses, phone_links, stable_phone_hostname


def show_phone_link(addresses, port, hostname=None):
    links = phone_links(addresses, port, hostname)
    if not links:
        print("No LAN IPv4 address found. Connect the computer and phone to the same Wi-Fi or LAN.", flush=True)
        return
    for link in links:
        print(f"{link['label']}: {link['url']}", flush=True)
    print("Open the dashboard and click the QR button beside This Month to scan the phone link.\n", flush=True)


def start_backend(port, frontend_port=3000):
    environment = os.environ.copy()
    environment["FARM_FRONTEND_PORT"] = str(frontend_port)
    environment["JOROSS_LAUNCHER_CONTROL"] = "1"
    return subprocess.Popen(
        [sys.executable, str(BACKEND / "scripts" / "serve_farm.py"), "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND,
        env=environment,
        **child_process_options(),
    )


def start_frontend(port, backend_port, production, phone_hostname=None):
    executable = shutil.which("node")
    if not executable:
        raise RuntimeError("Node.js is unavailable. Install Node.js and run npm ci in Jorros Frontend.")
    environment = os.environ.copy()
    environment["JOROSS_LAUNCHER_CONTROL"] = "1"
    # The proxy always talks to the backend on this computer, even if an old
    # frontend .env.local contains the IP of a previous Wi-Fi network.
    environment["BACKEND_API_ORIGIN"] = f"http://127.0.0.1:{backend_port}"
    if phone_hostname:
        environment["NEXT_ALLOWED_DEV_ORIGINS"] = ",".join(
            filter(None, [environment.get("NEXT_ALLOWED_DEV_ORIGINS"), phone_hostname])
        )
    return subprocess.Popen(
        [executable, str(FRONTEND / "scripts" / "serve-farm.cjs"), "start" if production else "dev", "-H", "0.0.0.0", "-p", str(port)],
        cwd=FRONTEND,
        env=environment,
        **child_process_options(),
    )


def child_process_options():
    # Only the launcher receives the terminal's Ctrl+C. It can then stop the
    # HTTP listener, finish its live proxy responses, and stop the API in order.
    options = {"stdin": subprocess.PIPE, "text": True, "encoding": "utf-8"}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return options


def send_control(process, command):
    if process is None or process.poll() is not None or process.stdin is None:
        return False
    try:
        process.stdin.write(command + "\n")
        process.stdin.flush()
        return True
    except (OSError, ValueError):
        # The child may have exited between poll() and the write.
        return False


def request_process_stop(process):
    if process is None or process.poll() is not None:
        return
    if send_control(process, "stop"):
        return
    try:
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        # An unavailable console or a child exiting concurrently falls back
        # to the bounded wait/termination below.
        pass


def wait_process_stopped(process, label, timeout=20):
    if process is None:
        return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"{label} did not finish stopping; closing its remaining processes.", flush=True)
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False, timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    finally:
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass


def stop_frontend(frontend, backend):
    request_process_stop(frontend)
    # Next.js stops accepting new requests first. The API remains available
    # while existing responses finish; ending SSE produces a complete HTTP
    # response instead of a reset in Next's proxy.
    send_control(backend, "drain")
    wait_process_stopped(frontend, "Frontend")


def stop_farm(frontend, backend):
    try:
        stop_frontend(frontend, backend)
    finally:
        request_process_stop(backend)
        wait_process_stopped(backend, "Backend")


def ensure_port_available(port, label):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if sys.platform != "win32":
            # Match the servers' Unix bind behavior: a completed graceful
            # close may leave TIME_WAIT sockets, but no live listener.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise RuntimeError(f"{label} port {port} is already in use. Stop the old farm server before starting this updated source.") from None


def verify_archive_api(*, local=False, port=8000):
    command = [sys.executable, str(BACKEND / "scripts" / "check_archive_api.py")]
    command += ["--local"] if local else ["--url", f"http://127.0.0.1:{port}", "--wait", "30"]
    if subprocess.run(command, cwd=BACKEND, check=False).returncode:
        raise RuntimeError("Archive API verification failed. Apply both application folders and restart the backend from this project. The frontend was not started.")


def verify_event_planning_api(*, local=False, port=8000):
    command = [sys.executable, str(BACKEND / "scripts" / "check_event_planning_api.py")]
    command += ["--local"] if local else ["--url", f"http://127.0.0.1:{port}", "--wait", "30"]
    if subprocess.run(command, cwd=BACKEND, check=False).returncode:
        raise RuntimeError("Event/location API verification failed. Apply both application folders and restart the backend from this project. The frontend was not started.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", action="store_true", help="Use an existing npm run build instead of the dev server")
    parser.add_argument("--port", type=int, default=3000, help="Phone-facing Next.js port (default: 3000)")
    parser.add_argument("--backend-port", type=int, default=8000, help="Local backend port (default: 8000)")
    args = parser.parse_args()
    if not all(1 <= port <= 65535 for port in (args.port, args.backend_port)):
        parser.error("Ports must be between 1 and 65535.")

    if not BACKEND.is_dir() or not (FRONTEND / "package.json").is_file():
        parser.error("Run the launcher from the complete project ZIP.")
    try:
        import qrcode  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as error:
        parser.error(f"Backend dependency missing ({error.name}); install Jorros Backend/requirements.txt in its .venv first.")
    if not (FRONTEND / "node_modules" / "next").exists():
        parser.error("Frontend dependencies missing; run npm ci inside Jorros Frontend first.")
    if args.production and not (FRONTEND / ".next" / "BUILD_ID").exists():
        parser.error("Production build missing; run npm run build inside Jorros Frontend first.")

    ensure_port_available(args.backend_port, "Backend")
    ensure_port_available(args.port, "Frontend")
    verify_archive_api(local=True)
    verify_event_planning_api(local=True)

    backend = None
    frontend = None
    try:
        backend = start_backend(args.backend_port, args.port)
        verify_archive_api(port=args.backend_port)
        verify_event_planning_api(port=args.backend_port)
        if backend.poll() is not None:
            raise RuntimeError("The updated backend exited during startup. Check its error above before starting the frontend.")
        phone_hostname = stable_phone_hostname()
        frontend = start_frontend(args.port, args.backend_port, args.production, phone_hostname)
        previous_network = None
        print("Joross Farm is starting. Leave this window open; press Ctrl+C to stop it.", flush=True)
        while True:
            if backend.poll() is not None:
                raise RuntimeError(f"Backend exited ({backend.returncode}). Check its error above and confirm port {args.backend_port} is free.")
            if frontend.poll() is not None:
                raise RuntimeError(f"Frontend exited ({frontend.returncode}). Check its error above and confirm port {args.port} is free.")

            addresses = lan_addresses()
            phone_hostname = stable_phone_hostname()
            network = (addresses, phone_hostname)
            if network != previous_network:
                if previous_network is not None and not args.production:
                    # Next.js dev checks allowed origins at startup. Refresh
                    # that list when the computer changes networks.
                    print("Network changed; restarting the frontend for the new address.", flush=True)
                    try:
                        stop_frontend(frontend, backend)
                    finally:
                        send_control(backend, "resume")
                    frontend = start_frontend(args.port, args.backend_port, False, phone_hostname)
                show_phone_link(addresses, args.port, phone_hostname)
                previous_network = network
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping Joross Farm...", flush=True)
    finally:
        # Repeated Ctrl+C must not interrupt cleanup and leave a child running.
        previous_interrupt = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            stop_farm(frontend, backend)
        finally:
            signal.signal(signal.SIGINT, previous_interrupt)
        if frontend is not None or backend is not None:
            print("Joross Farm stopped.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from None
