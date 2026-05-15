"""Project resolver package."""

from devmemory.resolver.git_resolver import ProjectInfo, resolve_project_slug, slugify_remote_url

__all__ = ["ProjectInfo", "resolve_project_slug", "slugify_remote_url"]
