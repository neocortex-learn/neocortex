"""Guard against command-registration regressions.

Engine-level tests import functions directly, so a command silently dropped
from the CLI (e.g. a lost ``@learn_app.command()`` decorator during the
27-command → command-group refactor, which unregistered ``learn growth`` and
``learn converge`` for months) passes the whole suite unnoticed. This test
pins the full expected command surface.
"""

from __future__ import annotations

import neocortex.cli as cli


def _command_names(typer_app) -> set[str]:
    names = set()
    for cmd in typer_app.registered_commands:
        names.add(cmd.name or cmd.callback.__name__.replace("_", "-"))
    return names


def test_top_level_commands_registered():
    expected = {"clip", "inbox", "daily", "read", "ask", "review", "search", "serve"}
    assert expected <= _command_names(cli.app)


def test_kb_commands_registered():
    expected = {"compile", "notes", "card", "lint", "verify", "map"}
    assert expected <= _command_names(cli.kb_app)


def test_discover_commands_registered():
    expected = {"explore", "feed", "research"}
    assert expected <= _command_names(cli.discover_app)


def test_learn_commands_registered():
    expected = {"recommend", "opportunities", "digest", "growth", "converge"}
    assert expected <= _command_names(cli.learn_app)


def test_profile_commands_registered():
    expected = {"init", "config", "scan", "import"}
    assert expected <= _command_names(cli.profile_app)
