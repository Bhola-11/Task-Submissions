from django.urls import path
from . import views

app_name = 'submissions'

urlpatterns = [
    # Phase 1: Student Submission Routes
    path('', views.submit_view, name='submit'),
    path('success/<int:submission_id>/', views.success_view, name='success'),

    # Phase 2: Custom Admin Dashboard & Zip Management Routes
    path('admin/login/', views.admin_login_view, name='admin_login'),
    path('admin/logout/', views.admin_logout_view, name='admin_logout'),
    path('admin/dashboard/', views.dashboard_view, name='dashboard'),
    path('admin/submissions/<int:submission_id>/', views.submission_detail_view, name='submission_detail'),
    path('admin/submissions/<int:submission_id>/status/', views.mark_reviewed_view, name='mark_reviewed'),
    path('admin/submissions/<int:submission_id>/download/', views.download_submission_zip_view, name='download_submission_zip'),
    path('admin/download-all/', views.download_all_zips_view, name='download_all_zips'),

    # Google Drive API Routes
    path('admin/submissions/<int:submission_id>/gdrive/', views.save_to_google_drive_view, name='save_to_google_drive'),
    path('admin/save-all-gdrive/', views.save_all_to_google_drive_view, name='save_all_to_google_drive'),

    # Google OAuth 2.0 Authorization & Callback Routes
    path('google/oauth2/authorize/', views.google_oauth_authorize_view, name='google_oauth_authorize'),
    path('google/oauth2/callback/', views.google_oauth_callback_view, name='google_oauth_callback'),

    # Render Health Check Route
    path('health/', views.health_check_view, name='health_check'),
]
