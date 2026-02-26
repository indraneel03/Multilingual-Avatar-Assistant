from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from core.views import avatar_query, history_session_detail, history_sessions, index, sarvam_webhook

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", index, name="index"),
    path("api/query/", avatar_query, name="avatar_query"),
    path("api/history/sessions/", history_sessions, name="history_sessions"),
    path("api/history/session/<str:session_id>/", history_session_detail, name="history_session_detail"),
    path("api/webhooks/sarvam/", sarvam_webhook, name="sarvam_webhook"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
