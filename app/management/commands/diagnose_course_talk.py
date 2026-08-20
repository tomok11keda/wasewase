"""本番/ローカルで Course Talk スキーマ・migration・孤児 FK を点検する。"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from app.models import ChatRoom, CourseOffering


class Command(BaseCommand):
    help = "Diagnose Course Talk schema, migrations, and dangling chat_room FKs"

    def handle(self, *args, **options):
        needed = ("0047_course_talk", "0048_chat_message_reply_delete")
        applied = set(
            MigrationRecorder.Migration.objects.filter(
                app="app", name__in=needed
            ).values_list("name", flat=True)
        )
        self.stdout.write(f"vendor={connection.vendor}")
        self.stdout.write(f"migrations_applied={sorted(applied)}")
        for name in needed:
            mark = "yes" if name in applied else "NO"
            self.stdout.write(f"  {name}: {mark}")

        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
            offering_cols = set()
            message_cols = set()
            room_cols = set()
            if "app_courseoffering" in tables:
                offering_cols = {
                    c.name
                    for c in connection.introspection.get_table_description(
                        cursor, "app_courseoffering"
                    )
                }
            if "app_chatmessage" in tables:
                message_cols = {
                    c.name
                    for c in connection.introspection.get_table_description(
                        cursor, "app_chatmessage"
                    )
                }
            if "app_chatroom" in tables:
                room_cols = {
                    c.name
                    for c in connection.introspection.get_table_description(
                        cursor, "app_chatroom"
                    )
                }

        checks = {
            "CourseOffering.chat_room_id": "chat_room_id" in offering_cols,
            "ChatMessage.is_hidden": "is_hidden" in message_cols,
            "ChatMessage.reply_to_id": "reply_to_id" in message_cols,
            "ChatMessage.deleted_at": "deleted_at" in message_cols,
            "ChatRoom.kind": "kind" in room_cols,
            "ChatRoom.name": "name" in room_cols,
            "ChatRoom.created_by_id": "created_by_id" in room_cols,
        }
        for label, ok in checks.items():
            self.stdout.write(f"column {label}: {'ok' if ok else 'MISSING'}")

        dangling = 0
        if checks["CourseOffering.chat_room_id"]:
            dangling = (
                CourseOffering.objects.filter(chat_room_id__isnull=False)
                .exclude(
                    chat_room_id__in=ChatRoom.objects.values_list("pk", flat=True)
                )
                .count()
            )
        course_rooms = ChatRoom.objects.filter(kind=ChatRoom.Kind.COURSE).count()
        linked = CourseOffering.objects.filter(chat_room_id__isnull=False).count()
        orphan_rooms = (
            ChatRoom.objects.filter(kind=ChatRoom.Kind.COURSE)
            .exclude(
                pk__in=CourseOffering.objects.filter(
                    chat_room_id__isnull=False
                ).values_list("chat_room_id", flat=True)
            )
            .count()
        )
        self.stdout.write(f"dangling_offering_chat_room_fk={dangling}")
        self.stdout.write(f"course_kind_rooms={course_rooms}")
        self.stdout.write(f"offerings_with_chat_room={linked}")
        self.stdout.write(f"orphan_course_rooms_unlinked={orphan_rooms}")
