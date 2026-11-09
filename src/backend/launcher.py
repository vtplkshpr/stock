"""Start the browser diagram next to the terminal CLI (used by the plugin entry point, main.py).

The server runs as a child process with the module's own Python environment, so it works even when
the host application's interpreter lacks FastAPI/uvicorn, it ignores Ctrl+C pressed in the CLI, and
a failure only costs the browser view. It is stopped when the CLI exits. If a diagram server is
already running on the configured port (e.g. another CLI session), that one is reused.

Only the standard library is imported here, so importing this module never fails.
Set WEB_AUTOSTART=0 to keep the CLI from starting the server.
"""

import atexit
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import FRONTEND_DIST, MODULE_DIR, load_settings

SERVER_SCRIPT = MODULE_DIR / "src" / "backend" / "server.py"
READY_TIMEOUT = 10.0


@dataclass
class WebHandle:
    url: str | None
    message: str
    process: subprocess.Popen | None = None

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None


def _probe_host(host: str) -> str:
    return "127.0.0.1" if host in ("0.0.0.0", "::", "") else host


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _is_diagram(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=2) as response:
            return json.load(response).get("status") == "ok"
    except (OSError, ValueError):
        return False


def _python_with_packages() -> str | None:
    """The first interpreter (module venvs first, then the current one) that has FastAPI/uvicorn."""
    candidates = [MODULE_DIR / ".venv" / "bin" / "python", MODULE_DIR / "venv" / "bin" / "python",
                  MODULE_DIR.parent / "venv" / "bin" / "python", Path(sys.executable)]
    seen = set()
    for candidate in candidates:
        if not candidate.is_file() or str(candidate) in seen:
            continue
        seen.add(str(candidate))
        try:
            check = subprocess.run([str(candidate), "-c", "import fastapi, uvicorn, mysql.connector"],
                                   capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if check.returncode == 0:
            return str(candidate)
    return None


def _tail(path: Path, lines: int = 3) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except OSError:
        return ""
    return " | ".join(text[-lines:])


def start_web_in_background() -> WebHandle:
    """Start (or reuse) the diagram server; never raises."""
    try:
        return _start()
    except Exception as exc:  # the CLI must keep working whatever happens here
        return WebHandle(None, f"Browser view could not be started: {exc}")


def _start() -> WebHandle:
    if os.environ.get("WEB_AUTOSTART", "1").strip().lower() in ("0", "false", "no", "off"):
        return WebHandle(None, "")
    settings = load_settings()
    host, port = _probe_host(settings.web_host), settings.web_port
    url = settings.public_url

    if _port_open(host, port):
        if _is_diagram(host, port):
            return WebHandle(url, "")
        return WebHandle(None, f"Browser view not started: port {port} is used by another program "
                               "(set WEB_PORT to a free port).")

    python = _python_with_packages()
    if python is None:
        return WebHandle(None, "Browser view not started: its packages are missing; run "
                               "`bash scripts/setup_web.sh` in the stock module.")

    log_path = Path(tempfile.gettempdir()) / f"stock-diagram-{port}.log"
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [python, str(SERVER_SCRIPT), "--host", settings.web_host, "--port", str(port)],
        cwd=str(MODULE_DIR), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,  # Ctrl+C in the CLI must not stop the server
    )
    log.close()
    handle = WebHandle(url, "", process)
    atexit.register(handle.stop)

    deadline = time.monotonic() + READY_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            handle.process = None
            detail = _tail(log_path)
            return WebHandle(None, f"Browser view could not be started: {detail or 'server exited'} "
                                   f"(log: {log_path})")
        if _port_open(host, port):
            if not (FRONTEND_DIST / "index.html").is_file():
                handle.message = ("Browser view started, but its frontend is not built; run "
                                  "`bash scripts/setup_web.sh` in the stock module.")
            return handle
        time.sleep(0.15)
    handle.message = f"Browser view is still starting (log: {log_path})."
    return handle
