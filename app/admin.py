from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from django.utils import timezone

from .models import (
    User,
    ChatRoom,
    Comment,
    Community,
    CommunityThread,
    CommunityThreadReply,
    ContentReport,
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
    TradeMessage,
    Follow,
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


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("email", "username", "is_staff", "is_active")
    search_fields = ("email", "username")
    ordering = ("email",)
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
    list_display = ("user", "name", "department", "grade")
    list_filter = ("department", "grade")
    search_fields = ("user__username", "user__email", "name")


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "following", "created_at")
    raw_id_fields = ("follower", "following")


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = ("target_type", "target_id", "reason", "reporter", "created_at")
    list_filter = ("target_type", "reason", "created_at")
    search_fields = ("target_id", "reporter__email", "reporter__username", "detail")
    readonly_fields = ("created_at",)
    actions = ["moderate_reported_content"]

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
    list_display = ("name", "seller", "price", "status", "category", "is_removed", "created_at")
    list_filter = ("status", "category", "is_removed", "created_at")
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
    list_display = ("product", "buyer", "updated_at", "created_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("product__name", "buyer__username")


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
    list_display = ("room", "sender", "body", "created_at")
    list_filter = ("created_at",)
    search_fields = ("body", "sender__username")
