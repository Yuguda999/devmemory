"""Tests for the git resolver — URL slugification and project detection."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from devmemory.resolver.git_resolver import (
    ProjectInfo,
    _find_git_root,
    _slugify_name,
    _slugify_path_segments,
    resolve_project_slug,
    slugify_remote_url,
)


# ── URL Slugification ─────────────────────────────────────────


class TestSlugifyRemoteUrl:
    """Tests for converting git remote URLs to project slugs."""

    def test_https_with_git_suffix(self):
        assert slugify_remote_url("https://github.com/Yuguda999/devmemory.git") == "yuguda999-devmemory"

    def test_https_without_git_suffix(self):
        assert slugify_remote_url("https://github.com/Yuguda999/devmemory") == "yuguda999-devmemory"

    def test_ssh_format(self):
        assert slugify_remote_url("git@github.com:Yuguda999/devmemory.git") == "yuguda999-devmemory"

    def test_ssh_without_git_suffix(self):
        assert slugify_remote_url("git@github.com:Yuguda999/devmemory") == "yuguda999-devmemory"

    def test_gitlab_https(self):
        assert slugify_remote_url("https://gitlab.com/myorg/myproject.git") == "myorg-myproject"

    def test_bitbucket_ssh(self):
        assert slugify_remote_url("git@bitbucket.org:team/repo-name.git") == "team-repo-name"

    def test_trailing_slash(self):
        assert slugify_remote_url("https://github.com/user/repo/") == "user-repo"

    def test_nested_path_takes_last_two(self):
        """GitLab supports nested groups — we take owner/repo (last 2 segments)."""
        assert slugify_remote_url("git@gitlab.com:org/subgroup/repo.git") == "subgroup-repo"

    def test_whitespace_stripped(self):
        assert slugify_remote_url("  https://github.com/user/repo.git  ") == "user-repo"

    def test_uppercase_normalized(self):
        assert slugify_remote_url("https://github.com/User/Repo.git") == "user-repo"

    def test_special_chars_in_repo_name(self):
        assert slugify_remote_url("https://github.com/user/my_project.git") == "user-my-project"

    def test_single_segment_path(self):
        """Bare host with single path segment."""
        assert slugify_remote_url("https://example.com/repo") == "repo"


# ── Slug Helper ────────────────────────────────────────────────


class TestSlugifyName:
    """Tests for the internal _slugify_name helper."""

    def test_basic_name(self):
        assert _slugify_name("my-project") == "my-project"

    def test_spaces_replaced(self):
        assert _slugify_name("My Cool Project") == "my-cool-project"

    def test_special_chars_stripped(self):
        assert _slugify_name("project@v2!") == "project-v2"

    def test_consecutive_hyphens_collapsed(self):
        assert _slugify_name("a---b") == "a-b"

    def test_leading_trailing_hyphens_stripped(self):
        assert _slugify_name("-project-") == "project"

    def test_empty_string(self):
        assert _slugify_name("") == "unnamed"

    def test_all_special_chars(self):
        assert _slugify_name("@#$%") == "unnamed"


# ── Path Segments ──────────────────────────────────────────────


class TestSlugifyPathSegments:
    """Tests for the _slugify_path_segments helper."""

    def test_two_segments(self):
        assert _slugify_path_segments("owner/repo") == "owner-repo"

    def test_three_segments(self):
        assert _slugify_path_segments("org/group/repo") == "group-repo"

    def test_single_segment(self):
        assert _slugify_path_segments("solo-repo") == "solo-repo"

    def test_empty(self):
        assert _slugify_path_segments("") == "unnamed"


# ── Find Git Root ──────────────────────────────────────────────


class TestFindGitRoot:
    """Tests for the _find_git_root filesystem walker."""

    def test_finds_devmemory_root(self):
        """Use the devmemory project itself as a test fixture."""
        src_dir = Path(__file__).resolve().parent.parent / "src" / "devmemory"
        root = _find_git_root(src_dir)
        assert root is not None
        assert (root / ".git").exists()
        assert root.name == "devmemory"

    def test_returns_none_for_tmp(self, tmp_path):
        """A temp directory with no .git should return None."""
        result = _find_git_root(tmp_path)
        assert result is None

    def test_finds_root_from_nested_dir(self, tmp_path):
        """Create a fake .git dir and verify it's found from a subdirectory."""
        (tmp_path / ".git").mkdir()
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        root = _find_git_root(nested)
        assert root == tmp_path


# ── Full Resolver ──────────────────────────────────────────────


class TestResolveProjectSlug:
    """Tests for the full resolve_project_slug function."""

    async def test_explicit_project_overrides_git(self):
        """Explicit project name always wins."""
        info = await resolve_project_slug("/any/path", explicit_project="My Custom Project")
        assert info.slug == "my-custom-project"
        assert info.name == "My Custom Project"
        assert info.remote_url is None

    async def test_resolves_from_git_remote(self):
        """Use the real devmemory project to test git remote resolution."""
        project_dir = str(Path(__file__).resolve().parent.parent)
        info = await resolve_project_slug(project_dir)
        assert info.slug == "yuguda999-devmemory"
        assert info.name == "devmemory"
        assert info.remote_url is not None
        assert "devmemory" in info.remote_url

    async def test_fallback_to_dir_name_no_remote(self, tmp_path):
        """Git repo without a remote should use the directory name."""
        (tmp_path / ".git").mkdir()
        info = await resolve_project_slug(str(tmp_path))
        assert info.slug == _slugify_name(tmp_path.name)
        assert info.name == tmp_path.name
        assert info.remote_url is None

    async def test_fallback_to_basename_no_git(self, tmp_path):
        """Non-git directory should use the basename."""
        project = tmp_path / "my-cool-app"
        project.mkdir()
        info = await resolve_project_slug(str(project))
        assert info.slug == "my-cool-app"
        assert info.name == "my-cool-app"
        assert info.remote_url is None

    async def test_nonexistent_dir_uses_basename(self):
        """Non-existent path should still resolve from the basename."""
        info = await resolve_project_slug("/nonexistent/fake-project")
        assert info.slug == "fake-project"
        assert info.name == "fake-project"
