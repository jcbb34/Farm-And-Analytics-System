"""Check controlled shutdown without opening the configured farm database."""
import asyncio
import importlib.util
import io
import os
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-at-least-32-bytes-long")

from app.core import server_lifecycle as lifecycle
from app.routers import events

ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = load_module("shutdown_launcher", ROOT / "run_farm.py")
server_runner = load_module("shutdown_api_runner", ROOT / "Jorros Backend/scripts/serve_farm.py")


@pytest.fixture(autouse=True)
def reset_drain():
    lifecycle.resume_streams()
    yield
    lifecycle.resume_streams()


def child():
    process = Mock(pid=1234, stdin=Mock())
    process.poll.return_value = None
    return process


@pytest.mark.parametrize("production,command", [(True, "start"), (False, "dev")])
def test_windows_starts_node_directly_in_an_isolated_controlled_group(production, command):
    with patch.object(launcher.sys, "platform", "win32"), \
         patch.object(launcher.shutil, "which", return_value="node.exe"), \
         patch.object(launcher.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True), \
         patch.object(launcher.subprocess, "Popen") as popen:
        launcher.start_frontend(3105, 8123, production, "farm.local")
    args, options = popen.call_args
    assert args[0] == ["node.exe", str(ROOT / "Jorros Frontend/scripts/serve-farm.cjs"),
                       command, "-H", "0.0.0.0", "-p", "3105"]
    assert options["creationflags"] == 512
    assert options["stdin"] == subprocess.PIPE
    assert options["env"]["JOROSS_LAUNCHER_CONTROL"] == "1"
    assert options["env"]["BACKEND_API_ORIGIN"] == "http://127.0.0.1:8123"
    assert "farm.local" in options["env"]["NEXT_ALLOWED_DEV_ORIGINS"]
    assert not options.get("shell")


def test_backend_receives_control_pipe_and_actual_frontend_port():
    with patch.object(launcher.sys, "platform", "linux"), \
         patch.object(launcher.subprocess, "Popen") as popen:
        launcher.start_backend(8123, 3105)
    args, options = popen.call_args
    assert str(ROOT / "Jorros Backend/scripts/serve_farm.py") in args[0]
    assert options["env"]["FARM_FRONTEND_PORT"] == "3105"
    assert options["env"]["JOROSS_LAUNCHER_CONTROL"] == "1"
    assert options["stdin"] == subprocess.PIPE and options["start_new_session"]


def test_shutdown_drains_proxy_before_stopping_api():
    frontend, backend = child(), child()
    order = []
    frontend.stdin.write.side_effect = lambda value: order.append(("frontend", value.strip()))
    backend.stdin.write.side_effect = lambda value: order.append(("backend", value.strip()))
    frontend.wait.side_effect = lambda **_: order.append(("frontend", "exited"))
    backend.wait.side_effect = lambda **_: order.append(("backend", "exited"))
    launcher.stop_farm(frontend, backend)
    assert order == [("frontend", "stop"), ("backend", "drain"),
                     ("frontend", "exited"), ("backend", "stop"), ("backend", "exited")]
    frontend.kill.assert_not_called()
    backend.kill.assert_not_called()


def test_api_cleanup_runs_even_if_frontend_wait_fails():
    frontend, backend = child(), child()
    frontend.wait.side_effect = OSError("already reaped")
    with pytest.raises(OSError):
        launcher.stop_farm(frontend, backend)
    backend.stdin.write.assert_any_call("stop\n")
    backend.wait.assert_called_once()


def test_failed_control_write_uses_windows_break_signal_without_taskkill():
    process = child()
    process.stdin.write.side_effect = BrokenPipeError
    with patch.object(launcher.sys, "platform", "win32"), \
         patch.object(launcher.signal, "CTRL_BREAK_EVENT", 999, create=True), \
         patch.object(launcher.subprocess, "run") as run:
        launcher.request_process_stop(process)
    process.send_signal.assert_called_once_with(999)
    run.assert_not_called()


def test_windows_force_termination_is_only_a_bounded_fallback():
    process = child()
    process.wait.side_effect = [subprocess.TimeoutExpired("node", 20), 0]
    process.stdin.close.side_effect = BrokenPipeError
    with patch.object(launcher.sys, "platform", "win32"), \
         patch.object(launcher.subprocess, "run", side_effect=OSError("taskkill unavailable")) as run:
        launcher.wait_process_stopped(process, "Frontend")
    assert process.wait.call_args_list[0].kwargs == {"timeout": 20}
    assert run.call_args.args[0] == ["taskkill", "/PID", "1234", "/T", "/F"]
    process.kill.assert_called_once()
    assert process.wait.call_args_list[-1].kwargs == {"timeout": 5}


def test_none_and_already_stopped_children_are_safe():
    launcher.stop_farm(None, None)
    process = child()
    process.poll.return_value = 0
    launcher.stop_farm(process, None)
    process.stdin.write.assert_not_called()
    process.kill.assert_not_called()


@pytest.mark.parametrize("commands", ["stop\n", "", "unknown\n"])
def test_backend_stop_or_pipe_eof_drains_streams_and_requests_exit(commands):
    server = SimpleNamespace(should_exit=False)
    server_runner.receive_control(server, io.StringIO(commands))
    assert lifecycle.streams_draining()
    assert server.should_exit


def test_backend_drain_can_resume_for_a_frontend_network_restart():
    server = SimpleNamespace(should_exit=False)

    def commands():
        yield "drain\n"
        assert lifecycle.streams_draining() and not server.should_exit
        yield "resume\n"
        assert not lifecycle.streams_draining() and not server.should_exit
        yield "stop\n"

    server_runner.receive_control(server, commands())
    assert lifecycle.streams_draining() and server.should_exit


def test_backend_signal_drains_before_uvicorn_waits_for_connections():
    server = server_runner.FarmServer(server_runner.uvicorn.Config("unused:app"))
    server.handle_exit(signal.SIGTERM, None)
    assert lifecycle.streams_draining() and server.should_exit


def stream_arguments():
    request = Mock()

    async def connected():
        return False

    request.is_disconnected = connected
    db = Mock()
    db.scalar.side_effect = [None, 0]
    return dict(request=request, since=None, last_event_id=None, db=db,
                user=SimpleNamespace(id=1))


def test_draining_stream_rejects_new_connections_without_reading_database():
    args = stream_arguments()
    lifecycle.drain_streams()
    with pytest.raises(HTTPException) as error:
        asyncio.run(events.stream_changes(**args))
    assert error.value.status_code == 503
    assert error.value.headers["Retry-After"] == "5"
    args["db"].scalar.assert_not_called()


def test_open_stream_finishes_normally_during_drain():
    async def exercise():
        response = await events.stream_changes(**stream_arguments())
        body = response.body_iterator
        assert await anext(body) == ": connected\n\n"
        assert "event: ready" in await anext(body)
        lifecycle.drain_streams()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(body), 0.5)
    asyncio.run(exercise())


def test_drain_during_poll_finishes_without_more_event_data():
    async def exercise():
        async def poll(*_):
            lifecycle.drain_streams()
            return [{"id": 1}], 1

        with patch.object(events, "run_in_threadpool", poll):
            response = await events.stream_changes(**stream_arguments())
            parts = [part async for part in response.body_iterator]
        assert len(parts) == 2 and all("event: change" not in part for part in parts)
    asyncio.run(exercise())
