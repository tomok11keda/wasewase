import os

from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app"

    def ready(self) -> None:
        if not os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
            return
        from app.media_services import (
            ensure_timelinepost_author_nullable,
            ensure_userprofile_avatar_column,
            ensure_userprofile_is_timetable_public_column,
            ensure_userprofile_terms_accepted_column,
            log_timelinepost_db_schema,
            log_userprofile_db_schema,
        )
        from app.dm_services import ensure_dm_read_state_table, ensure_dm_message_is_read_column
        from app.chat_schema_services import ensure_chatroom_group_chat_schema
        from app.timetable_services import ensure_timetable_slot_table

        ensure_userprofile_avatar_column()
        ensure_userprofile_terms_accepted_column()
        ensure_userprofile_is_timetable_public_column()
        ensure_timelinepost_author_nullable()
        ensure_dm_read_state_table()
        ensure_dm_message_is_read_column()
        ensure_chatroom_group_chat_schema()
        ensure_timetable_slot_table()
        log_timelinepost_db_schema()
        log_userprofile_db_schema()
