from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('settings/', views.settings_view, name='settings'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('health/', views.health_check, name='health_check'),

    # API endpoints
    path('api/test-connection/', views.test_connection, name='test_connection'),
    path('api/backup/', views.create_backup, name='create_backup'),
    path('backup/<int:backup_id>/delete/', views.delete_backup, name='delete_backup'),
    path('backup/<int:backup_id>/download/', views.download_backup, name='download_backup'),
]
