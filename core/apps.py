import os
import threading

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Only auto-preload in the main runserver process, not in the reloader child check
        if os.environ.get("RUN_MAIN") != "true":
            return
        from django.conf import settings
        if not getattr(settings, "AUTO_MODEL_WARMUP", False):
            return

        def _auto_preload():
            import time
            time.sleep(2)  # Let server finish binding
            try:
                from core.views import _kickoff_model_warmup
                _kickoff_model_warmup()
                print("[AutoPreload] Model warmup triggered on server start.")
            except Exception as exc:
                print(f"[AutoPreload] Warmup failed: {exc}")

        threading.Thread(target=_auto_preload, daemon=True).start()
