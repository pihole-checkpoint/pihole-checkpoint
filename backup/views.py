import logging

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

logger = logging.getLogger(__name__)


def dashboard(request):
    """Main dashboard view showing backup status and history."""
    config = PiholeConfig.objects.first()
    backups = BackupRecord.objects.filter(config=config) if config else BackupRecord.objects.none()

    return render(
        request,
        "backup/dashboard.html",
        {
            "config": config,
            "backups": backups,
        },
    )


def settings_view(request):
    """Settings view for configuring backup schedule."""
    config = PiholeConfig.objects.first()

    if request.method == "POST":
        form = PiholeConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved successfully!")
            return redirect("settings")
    else:
        form = PiholeConfigForm(instance=config)

    # Get Pi-hole credential status from environment
    credential_status = CredentialService.get_status()

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
def test_connection(request):
    """AJAX endpoint to test Pi-hole connection using environment credentials."""
    try:
        creds = CredentialService.get_credentials()

        client = PiholeV6Client(
            creds["url"],
            creds["password"],
            creds["verify_ssl"],
        )
        version_info = client.test_connection()

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
def create_backup(request):
    """AJAX endpoint to create a manual backup."""
    config = PiholeConfig.objects.first()

    if not config:
        return JsonResponse({"success": False, "error": "No Pi-hole configured"})

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

    service = BackupService(config)
    filepath = service.get_backup_file(record)

    if not filepath:
        messages.error(request, "Backup file not found")
        return redirect("dashboard")

    return FileResponse(open(filepath, "rb"), as_attachment=True, filename=record.filename)


def login_view(request):
    """Login view for optional authentication."""
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["password"] == settings.APP_PASSWORD:
                request.session["authenticated"] = True
                return redirect("dashboard")
            else:
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
    import subprocess

    # Check if scheduler process is running
    result = subprocess.run(["pgrep", "-f", "runapscheduler"], capture_output=True)
    scheduler_running = result.returncode == 0

    status = {
        "web": "ok",
        "scheduler": "ok" if scheduler_running else "not running",
        "database": "ok",
    }

    if not scheduler_running:
        return JsonResponse(status, status=503)

    return JsonResponse(status)
