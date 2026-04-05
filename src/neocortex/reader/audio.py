"""Audio transcription — convert audio files to text for the read pipeline."""

from __future__ import annotations

from pathlib import Path


_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".ogg", ".flac", ".webm", ".mpeg", ".mpga"}


def is_audio_file(path: str) -> bool:
    """Check if a file path has an audio extension."""
    return Path(path).suffix.lower() in _AUDIO_EXTENSIONS


async def transcribe_audio(path: str, api_key: str | None = None) -> str:
    """Transcribe an audio file to text.

    Tries in order:
    1. OpenAI Whisper API (if openai is installed and api_key available)
    2. Local whisper CLI (if whisper binary is on PATH)

    Returns the transcribed text.
    """
    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    # Try OpenAI Whisper API
    text = await _transcribe_openai(audio_path, api_key)
    if text is not None:
        return text

    # Try local whisper CLI
    text = _transcribe_local(audio_path)
    if text is not None:
        return text

    raise RuntimeError(
        "No transcription backend available. Install one of:\n"
        "  - openai SDK: pip install openai  (uses Whisper API, ~$0.006/min)\n"
        "  - whisper CLI: pip install openai-whisper  (local, free, slower)"
    )


async def _transcribe_openai(audio_path: Path, api_key: str | None) -> str | None:
    """Transcribe using OpenAI Whisper API."""
    try:
        import openai
    except ImportError:
        return None

    # Resolve API key: explicit > env > config
    if not api_key:
        import os
        api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        try:
            from neocortex.config import load_config
            cfg = load_config()
            if cfg.provider == "openai" and cfg.api_key:
                api_key = cfg.api_key
        except Exception:
            pass

    if not api_key:
        return None

    client = openai.OpenAI(api_key=api_key)

    # Whisper API has a 25MB limit; chunk if needed
    file_size = audio_path.stat().st_size
    if file_size > 25 * 1024 * 1024:
        return await _transcribe_openai_chunked(audio_path, client)

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )

    return response if isinstance(response, str) else str(response)


async def _transcribe_openai_chunked(audio_path: Path, client) -> str:
    """Transcribe a large audio file by splitting into chunks."""
    import subprocess
    import tempfile

    # Check if ffmpeg is available
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError(
            f"Audio file is too large ({audio_path.stat().st_size // 1024 // 1024}MB, "
            f"limit 25MB). Install ffmpeg to enable automatic chunking."
        )

    # Split into 10-minute chunks
    segments: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        chunk_pattern = Path(tmpdir) / "chunk_%03d.mp3"
        subprocess.run(
            [
                "ffmpeg", "-i", str(audio_path),
                "-f", "segment", "-segment_time", "600",
                "-c:a", "libmp3lame", "-q:a", "4",
                str(chunk_pattern),
            ],
            capture_output=True,
            check=True,
        )

        chunks = sorted(Path(tmpdir).glob("chunk_*.mp3"))
        for chunk in chunks:
            with open(chunk, "rb") as f:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="text",
                )
                text = response if isinstance(response, str) else str(response)
                segments.append(text)

    return "\n\n".join(segments)


def _transcribe_local(audio_path: Path) -> str | None:
    """Transcribe using local whisper CLI."""
    import subprocess

    try:
        result = subprocess.run(
            ["whisper", str(audio_path), "--output_format", "txt", "--output_dir", str(audio_path.parent)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            return None
    except (OSError, subprocess.TimeoutExpired):
        return None

    # whisper outputs to {stem}.txt
    txt_path = audio_path.with_suffix(".txt")
    if txt_path.exists():
        text = txt_path.read_text(encoding="utf-8")
        txt_path.unlink()  # Clean up
        return text

    return None
