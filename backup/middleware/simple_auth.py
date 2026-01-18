"""Simple password-based authentication middleware."""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class SimpleAuthMiddleware:
    """
    Middleware for optional password-based authentication.

    Enabled via REQUIRE_AUTH=true environment variable.
    Uses APP_PASSWORD for the password.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip if auth is not required
        if not settings.REQUIRE_AUTH:
            return self.get_response(request)

        # Skip if no password is configured
        if not settings.APP_PASSWORD:
            return self.get_response(request)

        # Allow login, logout, and health check URLs
        allowed_paths = [
            reverse("login"),
            reverse("health_check"),
            "/admin/",
        ]

        if any(request.path.startswith(path) for path in allowed_paths):
            return self.get_response(request)

        # Check if user is authenticated
        if not request.session.get("authenticated"):
            return redirect("login")

        return self.get_response(request)
