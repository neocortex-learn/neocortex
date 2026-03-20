"""GitHub remote repository scanner — list repos, clone, scan, cleanup."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

_GITHUB_API = "https://api.github.com"


async def list_user_repos(
    username: str, token: str | None = None
) -> list[dict]:
    """List repositories for a GitHub user.

    If *token* is provided, fetches the authenticated user's own repos
    (including private ones when the username matches the token owner).
    Otherwise falls back to the public endpoint.

    Returns a list of dicts with keys:
        name, full_name, clone_url, language, size, description
    """
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repos: list[dict] = []
    page = 1

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        while True:
            if token:
                url = f"{_GITHUB_API}/user/repos"
                params = {
                    "per_page": "100",
                    "sort": "updated",
                    "affiliation": "owner",
                    "page": str(page),
                }
            else:
                url = f"{_GITHUB_API}/users/{username}/repos"
                params = {
                    "per_page": "100",
                    "sort": "updated",
                    "page": str(page),
                }

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            if not data:
                break

            for repo in data:
                if token and repo.get("owner", {}).get("login", "").lower() != username.lower():
                    continue
                repos.append({
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "clone_url": repo["clone_url"],
                    "language": repo.get("language"),
                    "size": repo.get("size", 0),
                    "description": repo.get("description") or "",
                })

            if len(data) < 100:
                break
            page += 1

    return repos


async def get_single_repo(
    owner: str, repo: str, token: str | None = None
) -> dict:
    """Fetch metadata for a single repository.

    Returns a dict with keys:
        name, full_name, clone_url, language, size, description
    """
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        resp = await client.get(f"{_GITHUB_API}/repos/{owner}/{repo}")
        resp.raise_for_status()
        data = resp.json()

    return {
        "name": data["name"],
        "full_name": data["full_name"],
        "clone_url": data["clone_url"],
        "language": data.get("language"),
        "size": data.get("size", 0),
        "description": data.get("description") or "",
    }


async def clone_repo(clone_url: str, token: str | None = None) -> Path:
    """Shallow-clone a repository into a temporary directory.

    If *token* is provided, it is injected into the HTTPS URL for
    authentication (works for private repos).

    Returns the Path to the cloned directory.
    """
    url = clone_url
    if token and url.startswith("https://"):
        url = url.replace("https://", f"https://{token}@", 1)

    tmp_dir = Path(tempfile.mkdtemp(prefix="neocortex-gh-"))

    def _do_clone() -> None:
        subprocess.run(
            [
                "git", "clone",
                "--depth", "1",
                "--single-branch",
                url,
                str(tmp_dir / "repo"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    await asyncio.to_thread(_do_clone)
    return tmp_dir / "repo"


def cleanup_repo(path: Path) -> None:
    """Remove a previously cloned temporary repository directory."""
    parent = path.parent if path.name == "repo" else path
    if parent.exists() and str(parent).startswith(tempfile.gettempdir()):
        shutil.rmtree(parent, ignore_errors=True)
