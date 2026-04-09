from django.urls import path

from . import views

urlpatterns = [
    # Root
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("health/", views.health_check, name="health_check"),
    # Instance-scoped
    path("instances/<int:pk>/", views.instance_dashboard, name="instance_dashboard"),
    path("instances/<int:pk>/settings/", views.instance_settings, name="instance_settings"),
    path("instances/<int:pk>/api/test-connection/", views.test_connection, name="test_connection"),
    path("instances/<int:pk>/api/backup/", views.create_backup, name="create_backup"),
    path(
        "instances/<int:pk>/backup/<int:backup_id>/delete/",
        views.delete_backup,
        name="delete_backup",
    ),
    path(
        "instances/<int:pk>/backup/<int:backup_id>/download/",
        views.download_backup,
        name="download_backup",
    ),
    path(
        "instances/<int:pk>/api/restore/<int:backup_id>/",
        views.restore_backup,
        name="restore_backup",
    ),
]
