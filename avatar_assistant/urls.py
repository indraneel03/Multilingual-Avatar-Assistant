from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from core.views import (
    avatar_query,
    bootstrap_avatar,
    history_session_detail,
    history_sessions,
    index,
    musetalk_preload,
    musetalk_preload_status,
    sarvam_webhook,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", index, name="index"),
    path("api/bootstrap/", bootstrap_avatar, name="bootstrap_avatar"),
    path("api/query/", avatar_query, name="avatar_query"),
    path("api/musetalk/preload/", musetalk_preload, name="musetalk_preload"),
    path("api/musetalk/preload/status/", musetalk_preload_status, name="musetalk_preload_status"),
    path("api/history/sessions/", history_sessions, name="history_sessions"),
    path("api/history/session/<str:session_id>/", history_session_detail, name="history_session_detail"),
    path("api/webhooks/sarvam/", sarvam_webhook, name="sarvam_webhook"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
