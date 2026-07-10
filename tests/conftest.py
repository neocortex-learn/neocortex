"""Global test isolation: no test may touch the real vault or data dir.

Root cause (2026-07-10 incident): append_log() / NoteIndex resolve paths via
config.get_notes_dir() / get_data_dir() at call time. Test files that forgot
to monkeypatch these silently wrote into the developer's real vault
(vault/log.md test-entry pollution) and real data/neocortex.sqlite
(note_sources garbage rows). This autouse fixture makes isolation the
default instead of every file's responsibility.

Tests that exercise the real path-resolution logic itself can opt out with
``@pytest.mark.real_paths`` — they must then do their own sandboxing
(patching _config_path / _layout_root / Path.home as needed).
"""

from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_paths: opt out of global path isolation to test real path resolution",
    )


@pytest.fixture(autouse=True)
def _global_path_isolation(request, tmp_path, monkeypatch):
    if request.node.get_closest_marker("real_paths"):
        yield
        return
    data_dir = tmp_path / "_iso_data"
    notes_dir = tmp_path / "_iso_vault"
    data_dir.mkdir(exist_ok=True)
    notes_dir.mkdir(exist_ok=True)
    monkeypatch.setattr("neocortex.config.get_data_dir", lambda: data_dir)
    monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: notes_dir)
    yield
