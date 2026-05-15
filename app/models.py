from django.conf import settings
from django.db import models

from .constants import FACULTY_CHOICES


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    faculty = models.CharField(
        max_length=50, choices=FACULTY_CHOICES, blank=True
    )

    def __str__(self) -> str:
        return f"{self.user.username} ({self.faculty or '未設定'})"


class Product(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "出品中"
        SOLD = "sold", "売却済み"

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="products",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    price = models.PositiveIntegerField()
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100)
    course_name = models.CharField(max_length=120, blank=True, verbose_name="授業名")
    professor_name = models.CharField(max_length=120, blank=True, verbose_name="教授名")
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="purchases",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    image = models.ImageField(upload_to="products/", blank=True)
    image_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_sold(self) -> bool:
        return self.status == self.Status.SOLD


class Comment(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="comments"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.product.name} へのコメント"


class Like(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="likes",
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="likes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="unique_user_product_like"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} → {self.product.name}"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.recipient}: {self.message[:30]}"


class Review(models.Model):
    class Rating(models.IntegerChoices):
        BAD = 1, "悪い"
        NORMAL = 2, "普通"
        GOOD = 3, "良い"

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews_given",
    )
    reviewee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews_received",
    )
    rating = models.IntegerField(choices=Rating.choices)
    comment = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "reviewer"], name="unique_review_per_product"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.reviewer} → {self.reviewee} ({self.rating})"

    @property
    def rating_stars(self) -> str:
        return "★" * self.rating


class TradeMessage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="trade_messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trade_messages",
    )
    body = models.CharField(max_length=200)
    is_preset = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender}: {self.body[:30]}"


class CourseThread(models.Model):
    course_name = models.CharField(max_length=120)
    professor_name = models.CharField(max_length=120, blank=True)
    faculty = models.CharField(max_length=50, choices=FACULTY_CHOICES, blank=True)
    description = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_threads",
        null=True,
        blank=True,
    )
    god_boost_count = models.PositiveIntegerField(default=0)
    tip_total = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-god_boost_count", "-last_activity"]

    def __str__(self) -> str:
        return self.course_name


class ThreadPost(models.Model):
    thread = models.ForeignKey(
        CourseThread, on_delete=models.CASCADE, related_name="posts"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="thread_posts",
    )
    body = models.TextField(max_length=1000)
    is_god_pick = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_god_pick", "-created_at"]

    def __str__(self) -> str:
        return f"{self.thread.course_name}: {self.body[:40]}"


class ThreadTip(models.Model):
    thread = models.ForeignKey(
        CourseThread, on_delete=models.CASCADE, related_name="tips"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="thread_tips",
    )
    amount = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TimelinePost(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="timeline_posts",
    )
    body = models.CharField(max_length=280)
    course_name = models.CharField(max_length=120)
    professor_name = models.CharField(max_length=120, blank=True)
    faculty = models.CharField(max_length=50, choices=FACULTY_CHOICES, blank=True)
    god_count = models.PositiveIntegerField(default=0)
    tip_total = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.course_name}: {self.body[:40]}"


class TimelineTip(models.Model):
    timeline_post = models.ForeignKey(
        TimelinePost, on_delete=models.CASCADE, related_name="tips"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="timeline_tips",
    )
    amount = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class GodButtonUse(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="god_button_uses",
    )
    thread = models.ForeignKey(
        CourseThread,
        on_delete=models.CASCADE,
        related_name="god_uses",
        null=True,
        blank=True,
    )
    post = models.ForeignKey(
        ThreadPost,
        on_delete=models.SET_NULL,
        related_name="god_uses",
        null=True,
        blank=True,
    )
    timeline_post = models.ForeignKey(
        TimelinePost,
        on_delete=models.CASCADE,
        related_name="god_uses",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
