from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    CustomUser,
    Comment,
    CourseThread,
    GodButtonUse,
    Like,
    Notification,
    Product,
    Review,
    ThreadPost,
    ThreadTip,
    TimelinePost,
    TimelineTip,
    TradeMessage,
    UserProfile,
)

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ("email", "username", "is_staff", "is_active")
    list_filter = ("is_staff", "is_active")
    ordering = ("email",)
    # 管理画面での編集項目をメールベースに変更
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("個人情報", {"fields": ("username",)}),
        ("権限", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("重要日程", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "username", "password")}),
    )

@admin.register(TimelinePost)
class TimelinePostAdmin(admin.ModelAdmin):
    list_display = (
        "course_name",
        "author",
        "god_count",
        "tip_total",
        "created_at",
    )
    list_filter = ("faculty", "created_at")
    search_fields = ("body", "course_name", "professor_name")


@admin.register(TimelineTip)
class TimelineTipAdmin(admin.ModelAdmin):
    list_display = ("timeline_post", "user", "amount", "created_at")


@admin.register(CourseThread)
class CourseThreadAdmin(admin.ModelAdmin):
    list_display = (
        "course_name",
        "professor_name",
        "faculty",
        "god_boost_count",
        "tip_total",
        "last_activity",
    )
    list_filter = ("faculty",)
    search_fields = ("course_name", "professor_name")


@admin.register(ThreadPost)
class ThreadPostAdmin(admin.ModelAdmin):
    list_display = ("thread", "author", "is_god_pick", "created_at")


@admin.register(ThreadTip)
class ThreadTipAdmin(admin.ModelAdmin):
    list_display = ("thread", "user", "amount", "created_at")


@admin.register(GodButtonUse)
class GodButtonUseAdmin(admin.ModelAdmin):
    list_display = ("user", "thread", "post", "created_at")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "faculty")
    list_filter = ("faculty",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "seller", "price", "status", "category", "created_at")
    list_filter = ("status", "category", "created_at")
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
    list_display = ("product", "body", "created_at")
    list_filter = ("created_at",)
    search_fields = ("body", "product__name")


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    list_filter = ("created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "message", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("message", "recipient__username")


@admin.register(TradeMessage)
class TradeMessageAdmin(admin.ModelAdmin):
    list_display = ("product", "sender", "body", "is_preset", "created_at")
    list_filter = ("is_preset", "created_at")
