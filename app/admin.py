from django.contrib import admin, messages
from django.contrib.admin.actions import delete_selected as django_delete_selected
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    User,
    ChatMessage,
    ChatMessageModerationAppeal,
    ChatReadState,
    ChatRoom,
    ChatRoomMembership,
    Comment,
    Community,
    CommunityThread,
    CommunityThreadReply,
    ContentReport,
    Course,
    CourseAttendanceRecord,
    CourseEnrollment,
    CourseMeeting,
    CourseOffering,
    CourseReview,
    DevicePushToken,
    UserDirectMessage,
    UserDirectMessageRoom,
    CourseThread,
    Like,
    Message,
    Notification,
    Product,
    Review,
    ThreadPost,
    ThreadTip,
    TimelinePost,
    TimelineLike,
    TimetableSlot,
    CalendarEvent,
    CourseCalendarException,
    TradeMessage,
    Follow,
    FollowRequest,
    UserBlock,
    UserProfile,
)


@admin.action(description="運営削除（フィードから非表示）")
def mark_as_removed(modeladmin, request, queryset):
    queryset.filter(is_removed=False).update(
        is_removed=True,
        removed_at=timezone.now(),
        removed_by=request.user,
    )


@admin.action(description="運営削除を解除")
def restore_removed(modeladmin, request, queryset):
    queryset.filter(is_removed=True).update(
        is_removed=False,
        removed_at=None,
        removed_by=None,
    )


_SUPERUSER_ADMIN_DELETE_DENIED = (
    "管理者アカウント（スーパーユーザー）は削除できません。"
    "削除する場合は、先に管理者権限を解除してください。"
)
_SUPERUSER_BULK_DELETE_DENIED = (
    "管理者アカウント（スーパーユーザー）が含まれているため、"
    "一括削除を中止しました。先に管理者権限を解除してください。"
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "email",
        "username",
        "date_joined",
        "last_login",
        "is_staff",
        "is_active",
    )
    search_fields = ("email", "username")
    ordering = ("-date_joined",)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and getattr(obj, "is_superuser", False):
            return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        if getattr(obj, "is_superuser", False):
            raise PermissionDenied(_SUPERUSER_ADMIN_DELETE_DENIED)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        if queryset.filter(is_superuser=True).exists():
            self.message_user(
                request,
                _SUPERUSER_BULK_DELETE_DENIED,
                level=messages.ERROR,
            )
            return
        super().delete_queryset(request, queryset)

    def get_actions(self, request):
        actions = super().get_actions(request)
        delete_action = actions.get("delete_selected")
        if delete_action:
            _func, name, description = delete_action
            actions["delete_selected"] = (
                type(self).delete_selected_without_superusers,
                name,
                description,
            )
        return actions

    @admin.action(description="選択された ユーザー を削除")
    def delete_selected_without_superusers(self, request, queryset):
        if queryset.filter(is_superuser=True).exists():
            self.message_user(
                request,
                _SUPERUSER_BULK_DELETE_DENIED,
                level=messages.ERROR,
            )
            return None
        return django_delete_selected(self, request, queryset)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "プロフィール",
            {"fields": ("username", "first_name", "last_name", "stripe_connect_account_id")},
        ),
        (
            "権限",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("日時", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(TimelinePost)
class TimelinePostAdmin(admin.ModelAdmin):
    list_display = (
        "course_name",
        "author",
        "quoted_post",
        "like_count",
        "has_image",
        "is_removed",
        "created_at",
    )
    actions = [mark_as_removed, restore_removed]
    list_filter = ("is_removed", "faculty", "created_at")

    @admin.display(boolean=True, description="画像")
    def has_image(self, obj):
        return bool(obj.image)
    search_fields = ("body", "course_name", "professor_name")


@admin.register(TimelineLike)
class TimelineLikeAdmin(admin.ModelAdmin):
    list_display = ("timeline_post", "user", "created_at")


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "category",
        "faculty",
        "is_active",
        "sort_order",
        "latest_activity_at",
    )
    list_filter = ("category", "faculty", "is_active")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CommunityThread)
class CommunityThreadAdmin(admin.ModelAdmin):
    list_display = ("title", "community", "author", "created_at", "is_removed")
    list_filter = ("community", "is_removed", "created_at")
    search_fields = ("title", "body", "author__username")


@admin.register(CommunityThreadReply)
class CommunityThreadReplyAdmin(admin.ModelAdmin):
    list_display = ("thread", "author", "created_at", "is_removed")
    list_filter = ("is_removed", "created_at")
    search_fields = ("body", "author__username", "thread__title")


@admin.register(CourseThread)
class CourseThreadAdmin(admin.ModelAdmin):
    list_display = (
        "course_name",
        "professor_name",
        "faculty",
        "tip_total",
        "last_activity",
    )
    list_filter = ("faculty",)
    search_fields = ("course_name", "professor_name")


@admin.register(ThreadPost)
class ThreadPostAdmin(admin.ModelAdmin):
    list_display = ("thread", "author", "created_at")


@admin.register(ThreadTip)
class ThreadTipAdmin(admin.ModelAdmin):
    list_display = ("thread", "user", "amount", "created_at")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "name",
        "department",
        "grade",
        "has_avatar",
        "is_timetable_public",
        "is_private",
        "onboarding_step",
        "onboarding_completed_at",
        "onboarding_exempt",
    )
    list_filter = (
        "department",
        "grade",
        "is_timetable_public",
        "is_private",
        "onboarding_step",
        "onboarding_exempt",
    )
    search_fields = ("user__username", "user__email", "name")

    @admin.display(boolean=True, description="画像あり")
    def has_avatar(self, obj):
        return bool(obj.avatar)


@admin.register(TimetableSlot)
class TimetableSlotAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "slot_key",
        "name",
        "offering",
        "room",
        "credits",
        "updated_at",
    )
    list_filter = ("slot_key",)
    search_fields = ("user__username", "user__email", "name", "slot_key", "room")
    raw_id_fields = ("user", "offering")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "title_normalized", "updated_at")
    search_fields = ("title", "title_normalized")


@admin.action(description="選択した開講を非表示にする")
def hide_selected_offerings(modeladmin, request, queryset):
    from django.contrib import messages

    updated = queryset.filter(status=CourseOffering.Status.ACTIVE).update(
        status=CourseOffering.Status.HIDDEN
    )
    messages.success(request, f"{updated} 件の開講を非表示にしました。")


@admin.action(description="選択した開講を1件目へ統合（残り→1件目）")
def merge_selected_offerings(modeladmin, request, queryset):
    from django.contrib import messages

    from .course_services import merge_offerings

    active = list(
        queryset.filter(status=CourseOffering.Status.ACTIVE).order_by("pk")
    )
    if len(active) < 2:
        messages.error(request, "統合には有効な開講が2件以上必要です。")
        return
    target = active[0]
    for source in active[1:]:
        try:
            merge_offerings(source, target)
        except ValueError as exc:
            messages.error(request, f"統合失敗 ({source.pk}): {exc}")
            return
    messages.success(
        request,
        f"{len(active) - 1} 件を Offering #{target.pk} へ統合しました。",
    )


class CourseMeetingInline(admin.TabularInline):
    model = CourseMeeting
    extra = 1


@admin.register(CourseOffering)
class CourseOfferingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "instructor",
        "academic_year",
        "semester",
        "day_of_week",
        "period_kind",
        "period",
        "status",
        "source",
        "updated_at",
    )
    list_filter = ("status", "semester", "academic_year", "period_kind", "source")
    search_fields = (
        "title",
        "instructor",
        "title_normalized",
        "instructor_normalized",
        "room",
    )
    raw_id_fields = ("course", "created_by", "merged_into")
    inlines = [CourseMeetingInline]
    actions = [merge_selected_offerings, hide_selected_offerings]


@admin.register(CourseMeeting)
class CourseMeetingAdmin(admin.ModelAdmin):
    list_display = (
        "offering",
        "day_of_week",
        "period_kind",
        "period",
        "updated_at",
    )
    list_filter = ("period_kind", "day_of_week")
    raw_id_fields = ("offering",)
    search_fields = ("offering__title", "offering__instructor")


@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "offering", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email", "offering__title")
    raw_id_fields = ("user", "offering")


@admin.action(description="選択したレビューを非表示にする")
def hide_selected_reviews(modeladmin, request, queryset):
    from django.contrib import messages

    updated = queryset.filter(is_hidden=False).update(is_hidden=True)
    messages.success(request, f"{updated} 件のレビューを非表示にしました。")


@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    list_display = (
        "offering",
        "user",
        "overall_rating",
        "difficulty_rating",
        "is_hidden",
        "updated_at",
    )
    list_filter = ("overall_rating", "is_hidden")
    search_fields = ("offering__title", "user__username", "user__email", "comment")
    raw_id_fields = ("user", "offering")
    actions = [hide_selected_reviews]


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "date",
        "start_time",
        "title",
        "category",
        "updated_at",
    )
    list_filter = ("category", "date")
    search_fields = ("user__username", "user__email", "title", "memo")
    raw_id_fields = ("user",)
    date_hierarchy = "date"


@admin.register(CourseCalendarException)
class CourseCalendarExceptionAdmin(admin.ModelAdmin):
    list_display = ("user", "offering", "date", "status", "updated_at")
    list_filter = ("status", "date")
    search_fields = (
        "user__username",
        "user__email",
        "offering__title",
        "offering__instructor",
    )
    raw_id_fields = ("user", "offering")
    date_hierarchy = "date"


@admin.register(CourseAttendanceRecord)
class CourseAttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "offering", "date", "status", "updated_at")
    list_filter = ("status", "date")
    search_fields = (
        "user__username",
        "user__email",
        "offering__title",
        "offering__instructor",
    )
    raw_id_fields = ("user", "offering")
    date_hierarchy = "date"


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "following", "created_at")
    raw_id_fields = ("follower", "following")


@admin.register(FollowRequest)
class FollowRequestAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "created_at")
    raw_id_fields = ("from_user", "to_user")


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = (
        "target_link",
        "target_type",
        "target_id",
        "reason",
        "reporter",
        "handled_at",
        "created_at",
    )
    list_filter = ("target_type", "reason", "created_at", "handled_at")
    search_fields = ("target_id", "reporter__email", "reporter__username", "detail")
    readonly_fields = ("created_at", "handled_at", "handled_by", "target_link")
    raw_id_fields = ("reporter", "handled_by")
    actions = ["moderate_reported_content"]

    @admin.display(description="対象")
    def target_link(self, obj):
        if obj.target_type == ContentReport.TargetType.CHAT_MESSAGE:
            url = reverse("admin:app_chatmessage_change", args=[obj.target_id])
            return format_html('<a href="{}">ChatMessage #{}</a>', url, obj.target_id)
        return f"{obj.target_type}:{obj.target_id}"

    @admin.action(description="通報対象を運営削除（ユーザー通報は対象外）")
    def moderate_reported_content(self, request, queryset):
        from .ugc_services import soft_remove_content

        removed = 0
        for report in queryset:
            if report.target_type == ContentReport.TargetType.USER:
                continue
            if soft_remove_content(
                target_type=report.target_type,
                target_id=report.target_id,
                moderator=request.user,
            ):
                removed += 1
        self.message_user(request, f"{removed} 件のコンテンツを非表示にしました。")


@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")
    search_fields = ("blocker__email", "blocked__email")
    raw_id_fields = ("blocker", "blocked")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "seller",
        "price",
        "handover_campus",
        "status",
        "category",
        "is_removed",
        "created_at",
    )
    list_filter = ("status", "handover_campus", "category", "is_removed", "created_at")
    actions = [mark_as_removed, restore_removed]
    search_fields = (
        "name",
        "description",
        "category",
        "course_name",
        "professor_name",
        "seller__username",
    )
    fields = (
        "seller",
        "name",
        "price",
        "description",
        "faculty",
        "handover_campus",
        "course_name",
        "professor_name",
        "category",
        "status",
        "image",
        "image_url",
        "created_at",
    )
    readonly_fields = ("created_at",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "reviewer", "reviewee", "rating", "created_at")
    list_filter = ("rating", "created_at")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("product", "timeline_post", "author", "is_removed", "created_at")
    list_filter = ("is_removed", "created_at")
    search_fields = ("body", "product__name")
    actions = [mark_as_removed, restore_removed]


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    list_filter = ("created_at",)


@admin.register(DevicePushToken)
class DevicePushTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "token_preview", "updated_at")
    list_filter = ("platform", "updated_at")
    search_fields = ("user__email", "user__username", "token")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="トークン")
    def token_preview(self, obj):
        if len(obj.token) <= 24:
            return obj.token
        return f"{obj.token[:12]}…{obj.token[-8:]}"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "message", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("message", "recipient__username")


@admin.register(TradeMessage)
class TradeMessageAdmin(admin.ModelAdmin):
    list_display = ("product", "sender", "body", "is_preset", "created_at")
    list_filter = ("is_preset", "created_at")


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ("kind", "name", "product", "buyer", "created_by", "updated_at", "created_at")
    list_filter = ("kind", "created_at", "updated_at")
    search_fields = ("name", "product__name", "buyer__username")


@admin.register(ChatRoomMembership)
class ChatRoomMembershipAdmin(admin.ModelAdmin):
    list_display = ("room", "user", "role", "joined_at")
    list_filter = ("role", "joined_at")
    search_fields = ("room__name", "user__username")


@admin.register(ChatMessage)
class GroupChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "room",
        "sender",
        "body_preview",
        "is_hidden",
        "deleted_at",
        "created_at",
    )
    list_filter = ("is_hidden", "created_at")
    search_fields = ("body", "sender__username", "sender__email", "room__name")
    raw_id_fields = ("room", "sender", "reply_to", "removed_by")
    readonly_fields = (
        "created_at",
        "is_hidden",
        "removed_at",
        "removed_by",
        "deleted_at",
    )
    fields = (
        "room",
        "sender",
        "body",
        "reply_to",
        "created_at",
        "is_hidden",
        "removed_at",
        "removed_by",
        "removal_reason",
        "deleted_at",
    )
    actions = ["hide_selected_chat_messages", "restore_selected_chat_messages"]

    @admin.display(description="本文")
    def body_preview(self, obj):
        text = obj.body or ""
        return text if len(text) <= 40 else f"{text[:40]}…"

    @admin.action(description="運営により非表示（チャットに痕跡を残す）")
    def hide_selected_chat_messages(self, request, queryset):
        from .moderation_services import hide_chat_message

        count = 0
        for message in queryset:
            if not message.is_hidden:
                hide_chat_message(
                    message=message,
                    moderator=request.user,
                    reason=message.removal_reason or "運営による非表示",
                )
                count += 1
        self.message_user(request, f"{count} 件を運営削除（プレースホルダ表示）にしました。")

    @admin.action(description="運営削除を解除して復元")
    def restore_selected_chat_messages(self, request, queryset):
        from .moderation_services import restore_chat_message

        count = 0
        for message in queryset:
            if message.is_hidden:
                restore_chat_message(message=message, moderator=request.user)
                count += 1
        self.message_user(request, f"{count} 件を通常表示に戻しました。")


@admin.register(ChatMessageModerationAppeal)
class ChatMessageModerationAppealAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "appellant", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = (
        "explanation",
        "appellant__username",
        "appellant__email",
        "message__body",
    )
    raw_id_fields = ("message", "appellant", "reviewer")
    readonly_fields = (
        "created_at",
        "reviewed_at",
        "message_link",
        "message_body",
        "message_sender",
        "message_room",
    )
    fields = (
        "message",
        "message_link",
        "message_room",
        "message_sender",
        "message_body",
        "appellant",
        "explanation",
        "status",
        "created_at",
        "reviewed_at",
        "reviewer",
        "review_note",
    )
    actions = ["accept_selected_appeals", "reject_selected_appeals"]

    @admin.display(description="対象メッセージ")
    def message_link(self, obj):
        if obj.message_id is None:
            return "-"
        url = reverse("admin:app_chatmessage_change", args=[obj.message_id])
        return format_html('<a href="{}">ChatMessage #{}</a>', url, obj.message_id)

    @admin.display(description="元本文")
    def message_body(self, obj):
        return obj.message.body if obj.message_id else ""

    @admin.display(description="送信者")
    def message_sender(self, obj):
        return obj.message.sender if obj.message_id else ""

    @admin.display(description="ルーム")
    def message_room(self, obj):
        return obj.message.room if obj.message_id else ""

    def save_model(self, request, obj, form, change):
        from .moderation_services import (
            accept_chat_message_appeal,
            reject_chat_message_appeal,
        )

        if change:
            previous = ChatMessageModerationAppeal.objects.get(pk=obj.pk)
            if (
                previous.status == ChatMessageModerationAppeal.Status.PENDING
                and obj.status == ChatMessageModerationAppeal.Status.ACCEPTED
            ):
                accept_chat_message_appeal(
                    previous, request.user, note=obj.review_note
                )
                return
            if (
                previous.status == ChatMessageModerationAppeal.Status.PENDING
                and obj.status == ChatMessageModerationAppeal.Status.REJECTED
            ):
                reject_chat_message_appeal(
                    previous, request.user, note=obj.review_note
                )
                return
        super().save_model(request, obj, form, change)

    @admin.action(description="認容してメッセージを復元")
    def accept_selected_appeals(self, request, queryset):
        from .moderation_services import accept_chat_message_appeal

        count = 0
        for appeal in queryset.filter(status=ChatMessageModerationAppeal.Status.PENDING):
            accept_chat_message_appeal(appeal, request.user)
            count += 1
        self.message_user(request, f"{count} 件を認容し、メッセージを復元しました。")

    @admin.action(description="却下（削除状態を維持）")
    def reject_selected_appeals(self, request, queryset):
        from .moderation_services import reject_chat_message_appeal

        count = 0
        for appeal in queryset.filter(status=ChatMessageModerationAppeal.Status.PENDING):
            reject_chat_message_appeal(appeal, request.user)
            count += 1
        self.message_user(request, f"{count} 件を却下しました。")


@admin.register(ChatReadState)
class ChatReadStateAdmin(admin.ModelAdmin):
    list_display = ("room", "user", "last_read_message_id", "updated_at")
    list_filter = ("updated_at",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("chat_room", "sender", "body", "created_at")
    list_filter = ("created_at",)
    search_fields = ("body", "sender__username")


@admin.register(UserDirectMessageRoom)
class UserDirectMessageRoomAdmin(admin.ModelAdmin):
    list_display = ("user_a", "user_b", "updated_at", "created_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("user_a__username", "user_b__username")


@admin.register(UserDirectMessage)
class UserDirectMessageAdmin(admin.ModelAdmin):
    list_display = (
        "room",
        "sender",
        "message_kind",
        "body",
        "is_read",
        "created_at",
    )
    list_filter = ("message_kind", "is_read", "created_at")
    search_fields = ("body", "sender__username")
