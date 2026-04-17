"""Simple password-based authentication middleware."""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class SimpleAuthMiddleware:
    """
    Middleware for optional password-based authentication.

    Enabled via REQUIRE_AUTH=true environment variable.
    Uses APP_PASSWORD_HASH (hashed at startup from APP_PASSWORD env var).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip if auth is not required
        if not settings.REQUIRE_AUTH:
            return self.get_response(request)

        # Skip if no password is configured
        if not settings.APP_PASSWORD_HASH:
            return self.get_response(request)

        # Allow login, logout, health check, and metrics URLs
        allowed_paths = [
            reverse("login"),
            reverse("health_check"),
            reverse("metrics"),
        ]

        # Prometheus's default metrics_path is /metrics (no trailing slash);
        # match with or without the slash so scrapers don't get redirected.
        request_path = request.path if request.path.endswith("/") else request.path + "/"
        if any(request_path.startswith(path) for path in allowed_paths):
            return self.get_response(request)

        # Check if user is authenticated
        if not request.session.get("authenticated"):
            return redirect("login")

        return self.get_response(request)
