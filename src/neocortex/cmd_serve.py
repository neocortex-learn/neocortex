"""`neocortex serve` command — boot the local HTTP server (Sprint 0 S0-2)."""

from __future__ import annotations

import atexit
import signal

import typer

from neocortex.cli import _get_lang, app, console


@app.command()
def serve(
    port: int = typer.Option(
        0,
        "--port",
        "-p",
        help="Bind port (0 = pick a random free port; default).",
    ),
    show_token: bool = typer.Option(
        False,
        "--show-token",
        help="Print the bearer token at startup (useful for curl testing).",
    ),
) -> None:
    """Run the local HTTP server on 127.0.0.1 with token auth.

    Writes runtime files to ~/.neocortex/:
        - server.pid    — this process's PID
        - server.port   — bound port
        - server-token  — bearer token (0600)

    GUI clients (SwiftUI, future iPhone) read these to discover the server.
    """
    import uvicorn

    from neocortex.server.app import create_app
    from neocortex.server.runtime import cleanup_runtime, provision_runtime

    lang = _get_lang()  # noqa: F841 — kept for future i18n strings

    secrets = provision_runtime(port=port or None)
    atexit.register(cleanup_runtime)

    def _on_signal(signum, _frame):
        cleanup_runtime()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    console.print()
    console.print(f"  [green]Neocortex server[/green] listening on http://127.0.0.1:{secrets.port}")
    console.print(f"  [dim]pid:[/dim] {secrets.pid}")
    console.print(f"  [dim]token file:[/dim] ~/.neocortex/server-token (0600)")
    if show_token:
        console.print(f"  [yellow]token:[/yellow] {secrets.token}")
    console.print(f"  [dim]healthz:[/dim] curl http://127.0.0.1:{secrets.port}/healthz")
    console.print()

    fastapi_app = create_app(token=secrets.token, port=secrets.port)
    uvicorn.run(
        fastapi_app,
        host="127.0.0.1",
        port=secrets.port,
        log_level="info",
        access_log=False,
    )
