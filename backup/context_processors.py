"""Template context processors for Pi-hole Checkpoint."""

import functools
import importlib.metadata
import logging
import subprocess

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _get_app_info():
    """Get app version and git commit hash (cached for process lifetime)."""
    try:
        version = importlib.metadata.version("pihole-checkpoint")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"

    try:
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            .decode()
            .strip()
        )
    except Exception:
        commit = ""

    return {"version": version, "commit": commit}


def app_info(request):
    """Add app version and git commit to template context."""
    info = _get_app_info()
    return {
        "app_version": info["version"],
        "git_commit": info["commit"],
    }
