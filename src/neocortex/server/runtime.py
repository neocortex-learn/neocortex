"""Runtime files: port / pid / token in the data dir (config.get_data_dir()).

Clients (SwiftUI, future CLI fallback) discover the running server by reading
these files. Token file is 0600 so other local users can't grab it.
"""

from __future__ import annotations

import os
import secrets
import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerSecrets:
    """In-memory snapshot of what was written to runtime files."""
    port: int
    token: str
    pid: int


def _pid_file() -> Path:
    from neocortex.config import get_data_dir
    return get_data_dir() / "server.pid"


def _port_file() -> Path:
    from neocortex.config import get_data_dir
    return get_data_dir() / "server.port"


def _token_file() -> Path:
    from neocortex.config import get_data_dir
    return get_data_dir() / "server-token"


def allocate_free_port() -> int:
    """Bind to 127.0.0.1:0 to get an OS-assigned free port, then close.

    Tiny race window before uvicorn rebinds, acceptable for local use.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def provision_runtime(port: int | None = None) -> ServerSecrets:
    """Generate token, allocate port if needed, write runtime files.

    If an existing pid file points to a dead process (previous `serve` got
    SIGKILL'd or the OS crashed), wipe the stale files first so any in-flight
    discover() callers see "nothing here" rather than a moment of mixed state
    where pid/port came from old run and token came from new.
    """
    if _pid_file().exists():
        old = read_pid()
        if old is not None and not _pid_alive(old):
            cleanup_runtime()

    if port is None:
        port = allocate_free_port()
    token = secrets.token_urlsafe(32)
    pid = os.getpid()

    _port_file().write_text(str(port), encoding="utf-8")
    _pid_file().write_text(str(pid), encoding="utf-8")

    # Token: create with 0600 from the first syscall so there is no brief
    # world-readable window between write_text() and chmod().
    token_path = _token_file()
    if token_path.exists():
        os.chmod(token_path, 0o600)
    fd = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)

    return ServerSecrets(port=port, token=token, pid=pid)


def read_token() -> str | None:
    """Read the running server's token (used by CLI HTTP fallback later)."""
    try:
        return _token_file().read_text(encoding="utf-8").strip()
    except (OSError, FileNotFoundError):
        return None


def read_port() -> int | None:
    try:
        return int(_port_file().read_text(encoding="utf-8").strip())
    except (OSError, FileNotFoundError, ValueError):
        return None


def read_pid() -> int | None:
    try:
        return int(_pid_file().read_text(encoding="utf-8").strip())
    except (OSError, FileNotFoundError, ValueError):
        return None


def cleanup_runtime() -> None:
    """Remove runtime files; safe to call multiple times."""
    for p in (_pid_file(), _port_file(), _token_file()):
        try:
            p.unlink()
        except (OSError, FileNotFoundError):
            pass


def _pid_alive(pid: int) -> bool:
    """Signal 0 liveness check — doesn't actually send a signal."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def is_server_alive() -> bool:
    """Best-effort: is there a PID file pointing to a live process?"""
    pid = read_pid()
    return pid is not None and _pid_alive(pid)
