import logging
import os

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Sum
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import LoginForm, PiholeConfigForm
from .models import BackupRecord, PiholeConfig
from .services.backup_service import BackupService
from .services.credential_service import CredentialService
from .services.pihole_client import PiholeV6Client
from .services.restore_service import RestoreService
from .services.system_service import is_scheduler_running

logger = logging.getLogger(__name__)


def home(request):
    """Home page showing all Pi-hole instances as cards.

    Smart routing:
    - 0 instances: show empty state
    - 1 instance: auto-redirect to its dashboard
    - 2+ instances: show card grid
    """
    configs = PiholeConfig.objects.annotate(
        backup_count=Count("backups"),
        total_size=Sum("backups__file_size"),
    ).order_by("name")

    if configs.count() == 1:
        return redirect("instance_dashboard", pk=configs.first().pk)

    # Add credential status to each config for display
    configs_with_status = []
    for config in configs:
        configs_with_status.append(
            {
                "config": config,
                "credentials_configured": CredentialService.is_configured(config.env_prefix),
            }
        )

    return render(
        request,
        "backup/home.html",
        {"configs_with_status": configs_with_status},
    )


def instance_dashboard(request, pk):
    """Instance dashboard showing backup status and history."""
    config = get_object_or_404(PiholeConfig, pk=pk)
    backups = BackupRecord.objects.filter(config=config)

    credential_status = CredentialService.get_status(config.env_prefix)
    credentials_configured = CredentialService.is_configured(config.env_prefix)

    return render(
        request,
        "backup/dashboard.html",
        {
            "config": config,
            "backups": backups,
            "credential_status": credential_status,
            "credentials_configured": credentials_configured,
        },
    )


def instance_settings(request, pk):
    """Settings view for configuring backup schedule for a specific instance."""
    config = get_object_or_404(PiholeConfig, pk=pk)

    if request.method == "POST":
        form = PiholeConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved successfully!")
            return redirect("instance_settings", pk=pk)
    else:
        form = PiholeConfigForm(instance=config)

    credential_status = CredentialService.get_status(config.env_prefix)

    return render(
        request,
        "backup/settings.html",
        {
            "form": form,
            "config": config,
            "credential_status": credential_status,
        },
    )


@require_POST
def test_connection(request, pk):
    """AJAX endpoint to test Pi-hole connection for a specific instance."""
    config = get_object_or_404(PiholeConfig, pk=pk)

    try:
        creds = CredentialService.get_credentials(config.env_prefix)

        client = PiholeV6Client(
            base_url=creds["url"],
            password=creds["password"],
            verify_ssl=creds["verify_ssl"],
        )
        try:
            version_info = client.test_connection()
        finally:
            client.close()

        version = version_info.get("version", {}).get("core", {}).get("local", {}).get("version", "unknown")

        return JsonResponse({"success": True, "version": version})

    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)})
    except ConnectionError as e:
        return JsonResponse({"success": False, "error": str(e)})
    except Exception as e:
        logger.exception("Test connection error")
        return JsonResponse({"success": False, "error": str(e)})


@require_POST
def create_backup(request, pk):
    """AJAX endpoint to create a manual backup for a specific instance."""
    config = get_object_or_404(PiholeConfig, pk=pk)

    try:
        service = BackupService(config)
        record = service.create_backup(is_manual=True)
        return JsonResponse(
            {
                "success": True,
                "backup": {
                    "id": record.id,
                    "filename": record.filename,
                    "file_size": record.file_size,
                    "status": record.status,
                    "is_manual": record.is_manual,
                    "created_at": record.created_at.isoformat(),
                    "created_at_display": record.created_at.strftime("%b %d, %Y %H:%M"),
                },
            }
        )
    except Exception as e:
        logger.exception("Backup creation error")
        return JsonResponse({"success": False, "error": str(e)})


@require_POST
def delete_backup(request, pk, backup_id):
    """AJAX endpoint to delete a backup."""

    record = get_object_or_404(BackupRecord, id=backup_id, config_id=pk)
    config = record.config

    try:
        service = BackupService(config)
        service.delete_backup(record)
        return JsonResponse({"success": True})
    except Exception as e:
        logger.exception("Backup deletion error")
        return JsonResponse({"success": False, "error": str(e)})


@require_POST
def restore_backup(request, pk, backup_id):
    """AJAX endpoint to restore a backup to Pi-hole."""
    record = get_object_or_404(BackupRecord, id=backup_id, config_id=pk)
    config = record.config

    try:
        service = RestoreService(config)
        service.restore_backup(record)
        return JsonResponse(
            {
                "success": True,
                "message": "Backup restored successfully",
            }
        )
    except FileNotFoundError as e:
        return JsonResponse({"success": False, "error": str(e)})
    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)})
    except Exception as e:
        logger.exception("Restore error")
        return JsonResponse({"success": False, "error": str(e)})


def download_backup(request, pk, backup_id):
    """Download a backup file."""
    record = get_object_or_404(BackupRecord, id=backup_id, config_id=pk)
    config = record.config

    service = BackupService(config)
    filepath = service.get_backup_file(record)

    if not filepath:
        messages.error(request, "Backup file not found")
        return redirect("instance_dashboard", pk=pk)

    # Use Path.open() which FileResponse will properly close
    # FileResponse takes ownership of the file object and closes it when done
    f = filepath.open("rb")
    response = FileResponse(
        f,
        as_attachment=True,
        filename=record.filename,
    )
    # Set content length from open fd to avoid TOCTOU race with retention cleanup
    response["Content-Length"] = os.fstat(f.fileno()).st_size
    return response


def _get_client_ip(request):
    """Get client IP from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def login_view(request):
    """Login view for optional authentication with rate limiting."""
    from django.core.cache import cache
    from django.http import HttpResponse

    if request.method == "POST":
        client_ip = _get_client_ip(request)
        cache_key = f"login_attempts_{client_ip}"

        # Check rate limit: 5 attempts per minute
        attempts = cache.get(cache_key, 0)
        if attempts >= 5:
            return HttpResponse(
                "Too many login attempts. Please wait a minute.",
                status=429,
                content_type="text/plain",
            )

        form = LoginForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["password"] == settings.APP_PASSWORD:
                # Clear attempts on success
                cache.delete(cache_key)
                request.session["authenticated"] = True
                return redirect("home")
            else:
                # Increment failed attempts
                cache.set(cache_key, attempts + 1, timeout=60)
                return render(request, "backup/login.html", {"error": "Invalid password"})
    else:
        form = LoginForm()

    return render(request, "backup/login.html", {"form": form})


def logout_view(request):
    """Logout view."""
    request.session.flush()
    return redirect("login")


def health_check(request):
    """Health check endpoint for container orchestration."""
    scheduler_running = is_scheduler_running()

    status = {
        "web": "ok",
        "scheduler": "ok" if scheduler_running else "not running",
        "database": "ok",
    }

    if not scheduler_running:
        return JsonResponse(status, status=503)

    return JsonResponse(status)
