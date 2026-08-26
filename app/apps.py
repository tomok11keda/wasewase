import os
import sys

from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app"

    def ready(self) -> None:
        if not os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
            return
        # manage.py（collectstatic / migrate 等）では CreateModel 系 ensure を走らせない。
        # そうしないと migration の CreateModel より先にテーブルが作られ競合する。
        if any(os.path.basename(arg) == "manage.py" for arg in sys.argv):
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
        from app.dm_request_services import ensure_user_direct_message_request_table
        from app.chat_schema_services import (
            ensure_chatroom_group_chat_schema,
            ensure_chatroom_invitation_table,
            ensure_course_talk_schema,
        )
        from app.product_trade_schema_services import ensure_product_trade_schema
        from app.timetable_services import ensure_timetable_slot_table
        from app.calendar_services import ensure_calendar_event_table
        from app.course_calendar_exception_services import (
            ensure_course_calendar_exception_table,
        )
        from app.course_attendance_services import (
            ensure_course_attendance_record_table,
        )
        from app.course_meeting_services import ensure_course_meeting_table

        ensure_userprofile_avatar_column()
        ensure_userprofile_terms_accepted_column()
        ensure_userprofile_is_timetable_public_column()
        ensure_timelinepost_author_nullable()
        ensure_dm_read_state_table()
        ensure_dm_message_is_read_column()
        ensure_user_direct_message_request_table()
        ensure_chatroom_group_chat_schema()
        ensure_chatroom_invitation_table()
        ensure_course_talk_schema()
        ensure_timetable_slot_table()
        ensure_calendar_event_table()
        ensure_course_calendar_exception_table()
        ensure_course_attendance_record_table()
        ensure_course_meeting_table()
        ensure_product_trade_schema()
        log_timelinepost_db_schema()
        log_userprofile_db_schema()
