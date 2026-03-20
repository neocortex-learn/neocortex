from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from neocortex.scanner.github import (
    cleanup_repo,
    clone_repo,
    get_single_repo,
    list_user_repos,
)


def _make_httpx_response(json_data, status_code: int = 200) -> httpx.Response:
    """Build a fake httpx.Response with the given JSON body."""
    request = httpx.Request("GET", "https://api.github.com/test")
    response = httpx.Response(
        status_code=status_code,
        json=json_data,
        request=request,
    )
    return response


# ---------------------------------------------------------------------------
# list_user_repos
# ---------------------------------------------------------------------------


class TestListUserRepos:
    @pytest.mark.asyncio
    async def test_list_public_repos_no_token(self):
        repos_payload = [
            {
                "name": "alpha",
                "full_name": "octocat/alpha",
                "clone_url": "https://github.com/octocat/alpha.git",
                "language": "Python",
                "size": 1234,
                "description": "First repo",
                "owner": {"login": "octocat"},
            },
            {
                "name": "beta",
                "full_name": "octocat/beta",
                "clone_url": "https://github.com/octocat/beta.git",
                "language": "Go",
                "size": 567,
                "description": None,
                "owner": {"login": "octocat"},
            },
        ]

        mock_resp = _make_httpx_response(repos_payload)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("neocortex.scanner.github.httpx.AsyncClient", return_value=mock_client):
            repos = await list_user_repos("octocat")

        assert len(repos) == 2
        assert repos[0]["name"] == "alpha"
        assert repos[0]["full_name"] == "octocat/alpha"
        assert repos[0]["clone_url"] == "https://github.com/octocat/alpha.git"
        assert repos[0]["language"] == "Python"
        assert repos[0]["size"] == 1234
        assert repos[1]["name"] == "beta"
        assert repos[1]["description"] == ""

        call_args = mock_client.get.call_args
        assert "/users/octocat/repos" in call_args[0][0]
        assert "Authorization" not in mock_client.get.call_args_list[0]

    @pytest.mark.asyncio
    async def test_list_repos_with_token_self(self):
        user_resp = _make_httpx_response({"login": "myuser"})
        repos_payload = [
            {
                "name": "private-proj",
                "full_name": "myuser/private-proj",
                "clone_url": "https://github.com/myuser/private-proj.git",
                "language": "TypeScript",
                "size": 999,
                "description": "Secret stuff",
            },
        ]
        repos_resp = _make_httpx_response(repos_payload)
        empty_resp = _make_httpx_response([])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[user_resp, repos_resp, empty_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("neocortex.scanner.github.httpx.AsyncClient", return_value=mock_client):
            repos = await list_user_repos("myuser", token="ghp_test123")

        assert len(repos) == 1
        assert repos[0]["name"] == "private-proj"
        calls = mock_client.get.call_args_list
        assert "/user" == calls[0][0][0].split("api.github.com")[1]
        assert "/user/repos" in calls[1][0][0]

    @pytest.mark.asyncio
    async def test_list_repos_with_token_other_user(self):
        user_resp = _make_httpx_response({"login": "me"})
        repos_payload = [
            {
                "name": "public-proj",
                "full_name": "other/public-proj",
                "clone_url": "https://github.com/other/public-proj.git",
                "language": "Python",
                "size": 100,
                "description": "",
            },
        ]
        repos_resp = _make_httpx_response(repos_payload)
        empty_resp = _make_httpx_response([])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[user_resp, repos_resp, empty_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("neocortex.scanner.github.httpx.AsyncClient", return_value=mock_client):
            repos = await list_user_repos("other", token="ghp_xxx")

        assert len(repos) == 1
        assert repos[0]["full_name"] == "other/public-proj"
        calls = mock_client.get.call_args_list
        assert "/users/other/repos" in calls[1][0][0]

    @pytest.mark.asyncio
    async def test_list_repos_empty_response(self):
        mock_resp = _make_httpx_response([])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("neocortex.scanner.github.httpx.AsyncClient", return_value=mock_client):
            repos = await list_user_repos("nobody")

        assert repos == []


# ---------------------------------------------------------------------------
# get_single_repo
# ---------------------------------------------------------------------------


class TestGetSingleRepo:
    @pytest.mark.asyncio
    async def test_get_single_repo(self):
        repo_payload = {
            "name": "cool-project",
            "full_name": "octocat/cool-project",
            "clone_url": "https://github.com/octocat/cool-project.git",
            "language": "Rust",
            "size": 4321,
            "description": "A cool project",
        }

        mock_resp = _make_httpx_response(repo_payload)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("neocortex.scanner.github.httpx.AsyncClient", return_value=mock_client):
            info = await get_single_repo("octocat", "cool-project", token="ghp_abc")

        assert info["name"] == "cool-project"
        assert info["full_name"] == "octocat/cool-project"
        assert info["language"] == "Rust"
        assert info["size"] == 4321

        call_args = mock_client.get.call_args
        assert "/repos/octocat/cool-project" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_single_repo_no_token(self):
        repo_payload = {
            "name": "pub-repo",
            "full_name": "user/pub-repo",
            "clone_url": "https://github.com/user/pub-repo.git",
            "language": None,
            "size": 0,
            "description": None,
        }

        mock_resp = _make_httpx_response(repo_payload)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("neocortex.scanner.github.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            info = await get_single_repo("user", "pub-repo")

        assert info["language"] is None
        assert info["description"] == ""

        init_kwargs = mock_cls.call_args[1]
        assert "Authorization" not in init_kwargs["headers"]


# ---------------------------------------------------------------------------
# clone_repo
# ---------------------------------------------------------------------------


class TestCloneRepo:
    @pytest.mark.asyncio
    async def test_clone_repo_without_token(self):
        with patch("neocortex.scanner.github.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = await clone_repo("https://github.com/octocat/hello.git")

        assert result.name == "repo"
        assert str(result.parent).startswith(tempfile.gettempdir())

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "git"
        assert call_args[1] == "clone"
        assert "--depth" in call_args
        assert "1" in call_args
        assert "--single-branch" in call_args
        assert call_args[5] == "https://github.com/octocat/hello.git"

        cleanup_repo(result)

    @pytest.mark.asyncio
    async def test_clone_repo_with_token_uses_askpass(self):
        with patch("neocortex.scanner.github.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = await clone_repo(
                "https://github.com/octocat/private.git",
                token="ghp_secret123",
            )

        call_args = mock_run.call_args[0][0]
        assert call_args[5] == "https://github.com/octocat/private.git"
        env = mock_run.call_args[1]["env"]
        assert "GIT_ASKPASS" in env
        assert "GIT_TERMINAL_PROMPT" in env
        assert env["GIT_TERMINAL_PROMPT"] == "0"

        cleanup_repo(result)

    @pytest.mark.asyncio
    async def test_clone_repo_failure_raises(self):
        with patch("neocortex.scanner.github.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                128, "git", stderr="fatal: repo not found"
            )
            with pytest.raises(subprocess.CalledProcessError):
                await clone_repo("https://github.com/octocat/nonexistent.git")


# ---------------------------------------------------------------------------
# cleanup_repo
# ---------------------------------------------------------------------------


class TestCleanupRepo:
    def test_cleanup_removes_temp_directory(self):
        tmp_dir = Path(tempfile.mkdtemp(prefix="neocortex-gh-"))
        repo_dir = tmp_dir / "repo"
        repo_dir.mkdir()
        (repo_dir / "test.txt").write_text("hello")

        assert tmp_dir.exists()
        assert repo_dir.exists()

        cleanup_repo(repo_dir)

        assert not tmp_dir.exists()
        assert not repo_dir.exists()

    def test_cleanup_nonexistent_path_no_error(self):
        fake_path = Path(tempfile.gettempdir()) / "neocortex-gh-nonexistent" / "repo"
        cleanup_repo(fake_path)

    def test_cleanup_refuses_non_temp_path(self):
        non_temp = Path("/Users/fake/not-temp/repo")
        cleanup_repo(non_temp)
