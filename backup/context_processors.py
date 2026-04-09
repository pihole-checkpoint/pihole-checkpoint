"""Template context processors for Pi-hole Checkpoint."""

import functools
import importlib.metadata
import os
import subprocess


@functools.lru_cache(maxsize=1)
def _get_app_info():
    """Get app version and git commit hash (cached for process lifetime)."""
    try:
        version = importlib.metadata.version("pihole-checkpoint")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"

    # Prefer GIT_COMMIT env var (set at Docker build time), fall back to git CLI
    commit = os.environ.get("GIT_COMMIT", "")
    if not commit:
        try:
            commit = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                .decode()
                .strip()
            )
        except Exception:
            commit = ""

    # Use short hash for display
    if len(commit) > 7:
        commit = commit[:7]

    return {"version": version, "commit": commit}


def app_info(request):
    """Add app version and git commit to template context."""
    info = _get_app_info()
    return {
        "app_version": info["version"],
        "git_commit": info["commit"],
    }
