import secrets
import string

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from .constants import FACULTY_CHOICES, GRADE_CHOICES, HANDLE_PATTERN


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
        assign_handle_after_insert = False
        if not self.username:
            self.username = self._generate_unique_username_without_pk()
            assign_handle_after_insert = True
        super().save(*args, **kwargs)
        if assign_handle_after_insert and self.pk:
            desired = self._generate_unique_username()
            if self.username != desired:
                self.username = desired
                super().save(update_fields=["username"])

    def _generate_unique_username_without_pk(self) -> str:
        alphabet = string.ascii_lowercase + string.digits
        for _ in range(50):
            suffix = "".join(secrets.choice(alphabet) for _ in range(8))
            candidate = f"user_{suffix}"
            if self._is_available_handle(candidate):
                return candidate
        return f"user_{secrets.token_hex(8)}"

    def _is_available_handle(self, candidate: str) -> bool:
        if not HANDLE_PATTERN.match(candidate):
            return False
        return (
            not User.objects.filter(username__iexact=candidate)
            .exclude(pk=self.pk)
            .exists()
        )

    def _generate_unique_username(self) -> str:
        candidates: list[str] = []
        if self.pk:
            candidates.append(f"user_{self.pk}")
            for suffix in range(1, 1000):
                candidates.append(f"user_{self.pk}_{suffix}")
        for _ in range(30):
            candidates.append(self._generate_unique_username_without_pk())
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if self._is_available_handle(candidate):
                return candidate
        raise ValueError("一意なハンドルを生成できませんでした。")


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
        """アプリ内の表示名（ニックネーム）。未設定時はユーザーID。"""
        if self.name and self.name.strip():
            return self.name.strip()
        username = (
            User.objects.filter(pk=self.user_id)
            .values_list("username", flat=True)
            .first()
        )
        return username or self.user.username

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
    is_removed = models.BooleanField("運営削除", default=False, db_index=True)
    removed_at = models.DateTimeField("削除日時", null=True, blank=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="removed_products",
        null=True,
        blank=True,
    )

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
    is_removed = models.BooleanField("運営削除", default=False, db_index=True)
    removed_at = models.DateTimeField("削除日時", null=True, blank=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="removed_comments",
        null=True,
        blank=True,
    )

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


class DevicePushToken(models.Model):
    """FCM / APNs デバイストークン（Capacitor プッシュ通知用）。"""

    class Platform(models.TextChoices):
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_push_tokens",
    )
    token = models.CharField("デバイストークン", max_length=512, unique=True)
    platform = models.CharField(
        "プラットフォーム",
        max_length=16,
        choices=Platform.choices,
        default=Platform.IOS,
    )
    updated_at = models.DateTimeField("更新日時", auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.user_id} ({self.platform})"


class ContentReport(models.Model):
    """ユーザーからの UGC 通報。"""

    class TargetType(models.TextChoices):
        POST = "post", "タイムライン投稿"
        COMMENT = "comment", "コメント"
        USER = "user", "ユーザー"
        PRODUCT = "product", "出品"

    class Reason(models.TextChoices):
        SPAM = "spam", "スパム・宣伝"
        HARASSMENT = "harassment", "嫌がらせ・誹謗中傷"
        INAPPROPRIATE = "inappropriate", "不適切な内容"
        FRAUD = "fraud", "詐欺・虚偽出品"
        OTHER = "other", "その他"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="content_reports_sent",
    )
    target_type = models.CharField(
        "対象種別",
        max_length=16,
        choices=TargetType.choices,
    )
    target_id = models.PositiveIntegerField("対象ID")
    reason = models.CharField(
        "理由",
        max_length=32,
        choices=Reason.choices,
    )
    detail = models.TextField("詳細", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "target_type", "target_id"],
                name="unique_content_report_per_user_target",
            )
        ]

    def __str__(self) -> str:
        return f"{self.reporter_id} → {self.target_type}:{self.target_id}"


class UserBlock(models.Model):
    """ユーザーブロック（相手の投稿・出品を非表示）。"""

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_initiated",
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["blocker", "blocked"],
                name="unique_user_block",
            )
        ]

    def __str__(self) -> str:
        return f"{self.blocker_id} ⊘ {self.blocked_id}"


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
    tip_total = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_activity"]

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

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
    quoted_post = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
        verbose_name="引用元投稿",
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
    like_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_removed = models.BooleanField("運営削除", default=False, db_index=True)
    removed_at = models.DateTimeField("削除日時", null=True, blank=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="removed_timeline_posts",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        if self.course_name:
            return f"{self.course_name}: {self.body[:40]}"
        return self.body[:40]

    @property
    def has_course_info(self) -> bool:
        return bool(self.course_name or self.professor_name or self.faculty)


class Community(models.Model):
  class Category(models.TextChoices):
    FACULTY = "faculty", "学部"
    COURSE = "course", "授業・ゼミ"
    GENERAL = "general", "総合"

  slug = models.SlugField(max_length=80, unique=True)
  name = models.CharField(max_length=100)
  description = models.CharField(max_length=300, blank=True)
  category = models.CharField(
    max_length=20,
    choices=Category.choices,
    default=Category.GENERAL,
  )
  faculty = models.CharField(max_length=50, choices=FACULTY_CHOICES, blank=True)
  latest_thread_title = models.CharField(max_length=120, blank=True)
  latest_thread_preview = models.CharField(max_length=200, blank=True)
  latest_activity_at = models.DateTimeField(null=True, blank=True)
  is_active = models.BooleanField(default=True, db_index=True)
  sort_order = models.PositiveIntegerField(default=0)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ["sort_order", "name"]
    verbose_name = "コミュニティ掲示板"
    verbose_name_plural = "コミュニティ掲示板"

  def __str__(self) -> str:
    return self.name


class CommunityThread(models.Model):
    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name="threads",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_threads",
    )
    title = models.CharField(max_length=120)
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_removed = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "コミュニティスレッド"
        verbose_name_plural = "コミュニティスレッド"

    def __str__(self) -> str:
        return self.title


class CommunityThreadReply(models.Model):
    thread = models.ForeignKey(
        CommunityThread,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_thread_replies",
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_removed = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "コミュニティスレッド返信"
        verbose_name_plural = "コミュニティスレッド返信"

    def __str__(self) -> str:
        return self.body[:40]


class TimelineLike(models.Model):
    timeline_post = models.ForeignKey(
        TimelinePost, on_delete=models.CASCADE, related_name="likes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="timeline_likes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["timeline_post", "user"],
                name="unique_timeline_like_per_user",
            ),
        ]

