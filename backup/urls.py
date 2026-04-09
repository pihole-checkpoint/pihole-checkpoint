from django.urls import path

from . import views

urlpatterns = [
    # Overview / instance list (smart routing in view)
    path("", views.dashboard, name="dashboard"),
    # Instance management
    path("instances/<int:config_id>/", views.instance_dashboard, name="instance_dashboard"),
    path("instances/<int:config_id>/settings/", views.instance_settings, name="instance_settings"),
    # Per-instance API endpoints
    path("instances/<int:config_id>/backup/", views.create_backup, name="create_backup"),
    path("instances/<int:config_id>/test-connection/", views.test_connection, name="test_connection"),
    # Backup-level operations (resolve config via backup.config FK)
    path("backup/<int:backup_id>/delete/", views.delete_backup, name="delete_backup"),
    path("backup/<int:backup_id>/download/", views.download_backup, name="download_backup"),
    path("api/restore/<int:backup_id>/", views.restore_backup, name="restore_backup"),
    # Legacy redirect
    path("settings/", views.settings_redirect, name="settings"),
    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("health/", views.health_check, name="health_check"),
]
