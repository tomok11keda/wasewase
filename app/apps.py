import os

from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app"

    def ready(self) -> None:
        if not os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
            return
        from app.media_services import log_timelinepost_db_schema

        log_timelinepost_db_schema()
