"""
URL configuration for Student Task Submission Portal.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('submissions.urls', namespace='submissions')),
]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom error handlers
handler400 = 'submissions.views.error_400_view'
handler403 = 'submissions.views.error_403_view'
handler404 = 'submissions.views.error_404_view'
handler500 = 'submissions.views.error_500_view'
