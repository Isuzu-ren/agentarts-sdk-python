"""Server lifecycle management for agentarts-memory-server.

Provides start, stop, and status operations for the local adapter server
that serves Claude Code / Codex / OpenCode hook scripts over HTTP on
127.0.0.1:8719.

Process management uses a PID file at ~/.agentarts-memory/server.pid and
logs to ~/.agentarts-memory/server.log.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .utils import code_agent_source, confirm, expand, status_err, status_ok

PID_FILE = "~/.agentarts-memory/server.pid"
LOG_FILE = "~/.agentarts-memory/server.log"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8719
HEALTH_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/health"
STARTUP_WAIT_SECONDS = 2
STOP_TIMEOUT_SECONDS = 5


def _pid_path() -> Path:
    """Return the expanded path to the PID file."""
    return Path(expand(PID_FILE))


def _log_path() -> Path:
    """Return the expanded path to the log file."""
    return Path(expand(LOG_FILE))


def _read_pid() -> int | None:
    """Read the PID from the PID file, or None if missing/invalid."""
    p = _pid_path()
    if not p.exists():
        return None
    try:
        return int(p.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _write_pid(pid: int) -> None:
    """Write the PID to the PID file."""
    p = _pid_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(pid), encoding="utf-8")


def _remove_pid() -> None:
    """Remove the PID file if it exists."""
    _pid_path().unlink(missing_ok=True)


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is running (Unix signal-zero probe)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _is_running() -> bool:
    """Check if the server is running based on the PID file."""
    pid = _read_pid()
    if pid is None:
        return False
    if not _is_process_alive(pid):
        _remove_pid()
        return False
    return True


def _check_health() -> bool:
    """Check if the server health endpoint responds with HTTP 200."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _is_installed() -> bool:
    """Check if agentarts-memory-server console script is on PATH."""
    return shutil.which("agentarts-memory-server") is not None


def _install_server() -> bool:
    """Install agentarts-memory-code_agent via pip from local source."""
    source = code_agent_source()
    if not os.path.isdir(source):
        status_err("Install server", f"source not found: {source}")
        return False

    status_ok("Installing agentarts-memory-code_agent", source)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", source],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        status_err("Install server", "pip not available")
        return False

    if result.returncode != 0:
        status_err("Install server", result.stderr.strip() or "pip install failed")
        return False

    if not _is_installed():
        status_err(
            "Install server", "installed but agentarts-memory-server not on PATH; try 'hash -r'"
        )
        return False

    status_ok("Install server", "agentarts-memory-server ready")
    return True


def start() -> int:
    """Start the server in the background.

    If the server is not installed, installs agentarts-memory-code_agent first.
    Returns 0 on success, 1 on failure.
    """
    if _is_running():
        pid = _read_pid()
        status_ok("Server", f"already running (PID {pid})")
        return 0

    if not _is_installed():
        if not confirm(
            "Install agentarts-memory-server (agentarts-memory-code_agent)?", default=True
        ):
            print("Cancelled.")
            return 1
        if not _install_server():
            return 1

    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fp = open(log_path, "a", encoding="utf-8")

    proc = subprocess.Popen(
        ["agentarts-memory-server"],
        stdin=subprocess.DEVNULL,
        stdout=log_fp,
        stderr=log_fp,
        start_new_session=True,
    )
    log_fp.close()

    _write_pid(proc.pid)
    status_ok("Start server", f"PID {proc.pid}")

    time.sleep(STARTUP_WAIT_SECONDS)
    if proc.poll() is not None:
        _remove_pid()
        status_err("Start server", f"process exited immediately (code {proc.returncode})")
        status_err("Check logs", str(log_path))
        return 1

    if _check_health():
        status_ok("Health check", HEALTH_URL)
    else:
        status_ok("Server", f"started (PID {proc.pid}), health check pending...")
    return 0


def stop() -> int:
    """Stop the running server.

    Sends SIGTERM, waits, escalates to SIGKILL if needed.
    Returns 0 on success, 1 on failure.
    """
    pid = _read_pid()
    if pid is None:
        status_ok("Server", "not running")
        return 0

    if not _is_process_alive(pid):
        _remove_pid()
        status_ok("Server", "not running (stale PID removed)")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except PermissionError:
        status_err("Stop server", f"permission denied for PID {pid}")
        return 1

    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not _is_process_alive(pid):
            break
        time.sleep(0.3)

    if _is_process_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    _remove_pid()
    status_ok("Stop server", f"PID {pid} terminated")
    return 0


def status() -> int:
    """Check server status.

    Returns 0 if running and healthy, 1 otherwise.
    """
    pid = _read_pid()
    if pid is None:
        status_ok("Server", "not running")
        return 1

    if not _is_process_alive(pid):
        _remove_pid()
        status_ok("Server", "not running (stale PID removed)")
        return 1

    healthy = _check_health()
    health_label = "healthy" if healthy else "unresponsive"
    status_ok("Server", f"running (PID {pid}, {health_label})")
    return 0 if healthy else 1
