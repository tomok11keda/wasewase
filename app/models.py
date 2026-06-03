from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from .constants import FACULTY_CHOICES, GRADE_CHOICES


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("メールアドレスは必須です。")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("スーパーユーザーは is_staff=True である必要があります。")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(
                "スーパーユーザーは is_superuser=True である必要があります。"
            )
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField("メールアドレス", unique=True)
    stripe_connect_account_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Stripe Connect アカウントID",
        help_text="acct_ で始まる Connect アカウントID（出品者の受取先）",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self._generate_username()
        super().save(*args, **kwargs)

    def _generate_username(self) -> str:
        if self.email:
            local = self.email.split("@")[0]
            base = "".join(c if c.isalnum() or c == "_" else "_" for c in local)[:20]
            base = base or "user"
        else:
            base = "user"
        candidate = base
        suffix = 1
        while (
            User.objects.filter(username=candidate)
            .exclude(pk=self.pk)
            .exists()
        ):
            candidate = f"{base}{suffix}"
            suffix += 1
        return candidate


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    name = models.CharField("名前", max_length=80, blank=True)
    bio = models.TextField("概要", blank=True)
    department = models.CharField(
        "学部",
        max_length=50,
        choices=FACULTY_CHOICES,
        blank=True,
    )
    grade = models.CharField(
        "学年",
        max_length=20,
        choices=GRADE_CHOICES,
        blank=True,
    )

    def __str__(self) -> str:
        label = self.name or self.user.username
        dept = self.department or "未設定"
        return f"{label} ({dept})"

    @property
    def display_name(self) -> str:
        return self.name.strip() if self.name else self.user.username

    @property
    def department_grade_display(self) -> str:
        parts = [p for p in (self.department, self.grade) if p]
        return " ".join(parts)


class Follow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="following",
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="followers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["follower", "following"],
                name="unique_follow_relationship",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.follower_id} → {self.following_id}"


class SignupOTP(models.Model):
    """新規登録メール認証用のワンタイムコード（平文は保存しない）。"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signup_otp",
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()

    def __str__(self) -> str:
        return f"OTP for {self.user.email} (expires {self.expires_at})"


class Product(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "出品中"
        TRADING = "trading", "取引中"
        SOLD_OUT = "sold_out", "売り切れ"

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
    faculty = models.CharField(max_length=50, choices=FACULTY_CHOICES, blank=True)
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
    seller_trade_completed = models.BooleanField(default=False)
    buyer_trade_completed = models.BooleanField(default=False)
    stripe_checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="進行中の Stripe Checkout Session ID",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_sold(self) -> bool:
        return self.status == self.Status.SOLD_OUT

    @property
    def is_trading(self) -> bool:
        return self.status == self.Status.TRADING


class Comment(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="comments",
        null=True,
        blank=True,
    )
    timeline_post = models.ForeignKey(
        "TimelinePost",
        on_delete=models.CASCADE,
        related_name="comments",
        null=True,
        blank=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="comments",
        null=True,
        blank=True,
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        if self.product_id:
            return f"{self.product.name} へのコメント"
        if self.timeline_post_id:
            label = self.timeline_post.course_name or "タイムライン"
            return f"{label} への返信"
        return self.body[:30]


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


class ChatRoom(models.Model):
    """商品 × 購入希望者ごとのチャットルーム（ジモティー型）。"""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="chat_rooms",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_chat_rooms",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "buyer"],
                name="unique_product_buyer_chat_room",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product.name} × {self.buyer.username}"


class Message(models.Model):
    chat_room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )
    body = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender}: {self.body[:30]}"


class UserDirectMessageRoom(models.Model):
    """ユーザー同士の1対1 DM ルーム（商品とは無関係）。"""

    user_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dm_rooms_as_user_a",
    )
    user_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dm_rooms_as_user_b",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user_a", "user_b"],
                name="unique_user_dm_room_pair",
            ),
            models.CheckConstraint(
                condition=models.Q(user_a_id__lt=models.F("user_b_id")),
                name="dm_room_ordered_user_ids",
            ),
        ]

    def __str__(self) -> str:
        return f"DM: {self.user_a.username} ↔ {self.user_b.username}"

    def involves_user(self, user) -> bool:
        return user.id in (self.user_a_id, self.user_b_id)

    def other_user(self, user):
        if self.user_a_id == user.id:
            return self.user_b
        if self.user_b_id == user.id:
            return self.user_a
        return None


class UserDirectMessage(models.Model):
    room = models.ForeignKey(
        UserDirectMessageRoom,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_messages_sent",
    )
    body = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender}: {self.body[:30]}"


class CourseThread(models.Model):
    course_name = models.CharField(
        max_length=120, blank=True, null=True, verbose_name="授業名"
    )
    professor_name = models.CharField(
        max_length=120, blank=True, null=True, verbose_name="教授名"
    )
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
        return self.course_name or f"スレッド #{self.pk}"


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
        label = self.thread.course_name or "授業タグなし"
        return f"{label}: {self.body[:40]}"


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
    course_name = models.CharField(
        max_length=120, blank=True, null=True, verbose_name="授業名"
    )
    professor_name = models.CharField(
        max_length=120, blank=True, null=True, verbose_name="教授名"
    )
    faculty = models.CharField(max_length=50, choices=FACULTY_CHOICES, blank=True)
    image = models.ImageField(
        upload_to="post_images/",
        blank=True,
        null=True,
        verbose_name="画像",
    )
    god_count = models.PositiveIntegerField(default=0)
    tip_total = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        if self.course_name:
            return f"{self.course_name}: {self.body[:40]}"
        return self.body[:40]

    @property
    def has_course_info(self) -> bool:
        return bool(self.course_name or self.professor_name or self.faculty)


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
