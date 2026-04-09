import logging
import os
from pathlib import Path

from django.conf import settings
from django.contrib import messages
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


def dashboard(request):
    """Main dashboard view with smart routing based on config count.

    - 0 configs: show instance list with add prompt
    - 1 config: show full dashboard directly (backward compat)
    - 2+ configs: show instance card grid
    """
    configs = PiholeConfig.objects.all()
    count = configs.count()

    if count == 1:
        config = configs.first()
        backups = BackupRecord.objects.filter(config=config)
        credential_status = CredentialService.get_status(config)
        credentials_configured = CredentialService.is_configured(config)
        return render(
            request,
            "backup/instance_dashboard.html",
            {
                "config": config,
                "backups": backups,
                "credential_status": credential_status,
                "credentials_configured": credentials_configured,
                "single_instance": True,
            },
        )

    # 0 or 2+ configs: show instance list
    config_data = []
    for config in configs:
        config_data.append(
            {
                "config": config,
                "credential_status": CredentialService.get_status(config),
                "credentials_configured": CredentialService.is_configured(config),
            }
        )
    return render(
        request,
        "backup/instance_list.html",
        {
            "configs": configs,
            "config_data": config_data,
        },
    )


def instance_dashboard(request, config_id):
    """Per-instance dashboard showing backup status and history."""
    config = get_object_or_404(PiholeConfig, id=config_id)
    backups = BackupRecord.objects.filter(config=config)
    credential_status = CredentialService.get_status(config)
    credentials_configured = CredentialService.is_configured(config)

    return render(
        request,
        "backup/instance_dashboard.html",
        {
            "config": config,
            "backups": backups,
            "credential_status": credential_status,
            "credentials_configured": credentials_configured,
            "single_instance": False,
        },
    )


def instance_settings(request, config_id):
    """Per-instance settings view."""
    config = get_object_or_404(PiholeConfig, id=config_id)

    if request.method == "POST":
        form = PiholeConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved successfully!")
            return redirect("instance_settings", config_id=config.id)
    else:
        form = PiholeConfigForm(instance=config)

    credential_status = CredentialService.get_status(config)

    return render(
        request,
        "backup/settings.html",
        {
            "form": form,
            "config": config,
            "credential_status": credential_status,
            "is_new": False,
        },
    )


def add_instance(request):
    """Add a new Pi-hole instance."""
    if request.method == "POST":
        form = PiholeConfigForm(request.POST)
        if form.is_valid():
            config = form.save()
            messages.success(request, f"Instance '{config.name}' created successfully!")
            return redirect("instance_settings", config_id=config.id)
    else:
        form = PiholeConfigForm()

    return render(
        request,
        "backup/settings.html",
        {
            "form": form,
            "config": None,
            "credential_status": None,
            "is_new": True,
        },
    )


@require_POST
def delete_instance(request, config_id):
    """Delete a Pi-hole instance and all its backups."""
    config = get_object_or_404(PiholeConfig, id=config_id)

    # Delete backup files from disk
    for record in config.backups.all():
        if record.file_path:
            filepath = Path(record.file_path)
            if filepath.exists():
                try:
                    filepath.unlink()
                except OSError as e:
                    logger.error(f"Failed to delete backup file {filepath}: {e}")

    name = config.name
    config.delete()  # Cascade deletes BackupRecord rows
    messages.success(request, f"Instance '{name}' deleted.")
    return redirect("dashboard")


def settings_redirect(request):
    """Legacy /settings/ redirect to instance settings or add instance."""
    config = PiholeConfig.objects.first()
    if config:
        return redirect("instance_settings", config_id=config.id)
    return redirect("add_instance")


@require_POST
def test_connection(request, config_id):
    """AJAX endpoint to test Pi-hole connection using environment credentials."""
    config = get_object_or_404(PiholeConfig, id=config_id)

    try:
        creds = CredentialService.get_credentials(config)

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
def create_backup(request, config_id):
    """AJAX endpoint to create a manual backup."""
    config = get_object_or_404(PiholeConfig, id=config_id)

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
def delete_backup(request, backup_id):
    """AJAX endpoint to delete a backup."""
    record = get_object_or_404(BackupRecord, id=backup_id)
    config = record.config

    # Handle orphaned backup records (config was deleted)
    if not config:
        logger.warning(f"Deleting orphaned backup record: {record.filename}")
        if record.file_path:
            filepath = Path(record.file_path)
            if filepath.exists():
                try:
                    filepath.unlink()
                except OSError as e:
                    logger.error(f"Failed to delete orphaned file: {e}")
        record.delete()
        return JsonResponse({"success": True})

    try:
        service = BackupService(config)
        service.delete_backup(record)
        return JsonResponse({"success": True})
    except Exception as e:
        logger.exception("Backup deletion error")
        return JsonResponse({"success": False, "error": str(e)})


@require_POST
def restore_backup(request, backup_id):
    """AJAX endpoint to restore a backup to Pi-hole."""
    record = get_object_or_404(BackupRecord, id=backup_id)
    config = record.config

    if not config:
        return JsonResponse({"success": False, "error": "Cannot restore: Pi-hole configuration no longer exists"})

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


def download_backup(request, backup_id):
    """Download a backup file."""
    record = get_object_or_404(BackupRecord, id=backup_id)
    config = record.config

    if not config:
        messages.error(request, "Pi-hole configuration no longer exists")
        return redirect("dashboard")

    service = BackupService(config)
    filepath = service.get_backup_file(record)

    if not filepath:
        messages.error(request, "Backup file not found")
        return redirect("dashboard")

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
                return redirect("dashboard")
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
