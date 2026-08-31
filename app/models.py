import secrets
import string

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower

from .constants import (
    FACULTY_CHOICES,
    GRADE_CHOICES,
    HANDLE_PATTERN,
    HANDOVER_CAMPUS_CHOICES,
)


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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="app_user_username_lower_uniq",
            ),
        ]

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
    avatar = models.ImageField(
        "プロフィール画像",
        upload_to="avatars/",
        blank=True,
        null=True,
    )
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
    terms_accepted = models.BooleanField(
        "利用規約への同意",
        default=False,
        help_text="新規登録時に利用規約・プライバシーポリシーへ同意したか。",
    )
    is_timetable_public = models.BooleanField(
        "時間割を公開する",
        default=False,
        help_text="true のとき他ユーザーのプロフィールから時間割を閲覧できる。",
    )
    is_private = models.BooleanField(
        "非公開アカウント",
        default=False,
        help_text="true のときフォローにはリクエスト承認が必要で、投稿等は承認フォロワーのみ閲覧可。",
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


class TimetableSlot(models.Model):
    """ユーザーごとの時間割セル（通常限・オンデマンド）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="timetable_slots",
        verbose_name="ユーザー",
    )
    slot_key = models.CharField(
        "スロットキー",
        max_length=16,
        help_text="例: p1-d0（月曜1限）, od1-d2（水曜OD1）",
    )
    name = models.CharField("授業名", max_length=120, blank=True)
    room = models.CharField("教室", max_length=80, blank=True)
    credits = models.CharField("単位", max_length=20, blank=True)
    memo = models.TextField("進捗・課題メモ", blank=True)
    offering = models.ForeignKey(
        "CourseOffering",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timetable_slots",
        verbose_name="開講授業",
    )
    meeting = models.ForeignKey(
        "CourseMeeting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timetable_slots",
        verbose_name="授業ミーティング",
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "時間割スロット"
        verbose_name_plural = "時間割スロット"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slot_key"],
                name="unique_timetable_slot_per_user",
            )
        ]
        ordering = ["slot_key"]

    def __str__(self) -> str:
        label = self.name or "(空)"
        return f"{self.user_id}:{self.slot_key} {label}"


class Course(models.Model):
    """授業の概念的な親（例: マーケティング論）。"""

    title = models.CharField("授業名", max_length=120)
    title_normalized = models.CharField(
        "正規化授業名", max_length=120, blank=True, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "授業"
        verbose_name_plural = "授業"
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["title_normalized"],
                name="unique_course_title_normalized",
            )
        ]

    def __str__(self) -> str:
        return self.title


class CourseOffering(models.Model):
    """特定年度・学期・教員の開講インスタンス。

    曜日・時限は CourseMeeting（1対多）。
    day_of_week / period / period_kind は代表ミーティングの非正規化（互換用）。
    レビュー・履修・欠席・授業トークは Offering 単位で共通。
    """

    class Semester(models.TextChoices):
        SPRING = "spring", "春学期"
        FALL = "fall", "秋学期"
        FULL = "full", "通年"

    class PeriodKind(models.TextChoices):
        PERIOD = "period", "通常限"
        OD = "od", "オンデマンド"

    class Source(models.TextChoices):
        USER = "user", "ユーザー"
        ADMIN = "admin", "管理者"

    class Status(models.TextChoices):
        ACTIVE = "active", "有効"
        MERGED = "merged", "統合済み"
        HIDDEN = "hidden", "非表示"

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="offerings",
        verbose_name="授業",
    )
    academic_year = models.PositiveIntegerField("年度", db_index=True)
    semester = models.CharField(
        "学期",
        max_length=16,
        choices=Semester.choices,
        db_index=True,
    )
    title = models.CharField("授業名", max_length=120)
    title_normalized = models.CharField(
        "正規化授業名", max_length=120, blank=True, db_index=True
    )
    instructor = models.CharField("担当教員", max_length=120)
    instructor_normalized = models.CharField(
        "正規化教員名", max_length=120, blank=True, db_index=True
    )
    day_of_week = models.PositiveSmallIntegerField(
        "代表曜日",
        help_text="0=月 … 5=土（代表ミーティングの非正規化）",
    )
    period_kind = models.CharField(
        "代表時限種別",
        max_length=16,
        choices=PeriodKind.choices,
        default=PeriodKind.PERIOD,
    )
    period = models.PositiveSmallIntegerField("代表時限")
    school = models.CharField("学部", max_length=50, blank=True)
    campus = models.CharField("キャンパス", max_length=40, blank=True)
    room = models.CharField("教室", max_length=80, blank=True)
    credits = models.CharField("単位", max_length=20, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="course_offerings_created",
        verbose_name="作成者",
    )
    source = models.CharField(
        "出典",
        max_length=16,
        choices=Source.choices,
        default=Source.USER,
    )
    status = models.CharField(
        "状態",
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_from",
        verbose_name="統合先",
    )
    chat_room = models.OneToOneField(
        "ChatRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="course_offering",
        verbose_name="授業トーク",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "開講授業"
        verbose_name_plural = "開講授業"
        ordering = ["title", "day_of_week", "period"]
        indexes = [
            models.Index(
                fields=[
                    "status",
                    "title_normalized",
                    "instructor_normalized",
                ]
            ),
            models.Index(
                fields=["status", "day_of_week", "period_kind", "period"]
            ),
            models.Index(fields=["academic_year", "semester", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "title_normalized",
                    "instructor_normalized",
                    "academic_year",
                    "semester",
                ],
                condition=models.Q(status="active"),
                name="uniq_active_course_offering_identity",
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.instructor})"

    @property
    def slot_key(self) -> str:
        prefix = "od" if self.period_kind == self.PeriodKind.OD else "p"
        return f"{prefix}{self.period}-d{self.day_of_week}"


class CourseMeeting(models.Model):
    """開講授業の開催スロット（曜日・時限）。1 Offering に複数可。"""

    offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.CASCADE,
        related_name="meetings",
        verbose_name="開講授業",
    )
    day_of_week = models.PositiveSmallIntegerField(
        "曜日",
        help_text="0=月 … 5=土",
    )
    period_kind = models.CharField(
        "時限種別",
        max_length=16,
        choices=CourseOffering.PeriodKind.choices,
        default=CourseOffering.PeriodKind.PERIOD,
    )
    period = models.PositiveSmallIntegerField("時限")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "授業ミーティング"
        verbose_name_plural = "授業ミーティング"
        ordering = ["day_of_week", "period_kind", "period", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["offering", "day_of_week", "period_kind", "period"],
                name="unique_course_meeting_per_offering_slot",
            )
        ]
        indexes = [
            models.Index(fields=["day_of_week", "period_kind", "period"]),
        ]

    def __str__(self) -> str:
        return f"{self.offering_id}:{self.slot_key}"

    @property
    def slot_key(self) -> str:
        prefix = (
            "od" if self.period_kind == CourseOffering.PeriodKind.OD else "p"
        )
        return f"{prefix}{self.period}-d{self.day_of_week}"


class CourseEnrollment(models.Model):
    """ユーザーの履修（時間割登録）状態。"""

    class Role(models.TextChoices):
        CURRENT = "current", "履修中"
        PAST = "past", "過去履修"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_enrollments",
        verbose_name="ユーザー",
    )
    offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="開講授業",
    )
    role = models.CharField(
        "役割",
        max_length=16,
        choices=Role.choices,
        default=Role.CURRENT,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "履修"
        verbose_name_plural = "履修"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "offering"],
                name="unique_course_enrollment_per_user",
            )
        ]
        indexes = [
            models.Index(fields=["offering", "role"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.offering_id} ({self.role})"


class CourseReview(models.Model):
    """開講授業レビュー（1ユーザー1件）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_reviews",
        verbose_name="ユーザー",
    )
    offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="開講授業",
    )
    overall_rating = models.PositiveSmallIntegerField("総合評価")
    difficulty_rating = models.PositiveSmallIntegerField("単位取得難易度")
    workload_rating = models.PositiveSmallIntegerField("課題量")
    attendance_rating = models.PositiveSmallIntegerField("出席重要度")
    exam_rating = models.PositiveSmallIntegerField("試験")
    comment = models.TextField("コメント", blank=True, max_length=1000)
    is_hidden = models.BooleanField(
        "非表示",
        default=False,
        db_index=True,
        help_text="モデレーションにより一覧から隠す",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "授業レビュー"
        verbose_name_plural = "授業レビュー"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "offering"],
                name="unique_course_review_per_user",
            )
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"review {self.offering_id} by {self.user_id}"


class CalendarEvent(models.Model):
    """ユーザー個人のカレンダー予定（時間割タブのカレンダービュー用）。"""

    class Category(models.TextChoices):
        CLASS = "class", "授業"
        ASSIGNMENT = "assignment", "課題"
        EXAM = "exam", "テスト"
        SEMINAR = "seminar", "ゼミ"
        CLUB = "club", "サークル"
        OTHER = "other", "その他"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_events",
        verbose_name="ユーザー",
    )
    title = models.CharField("予定名", max_length=120)
    date = models.DateField("日付", db_index=True)
    start_time = models.TimeField("開始時刻", null=True, blank=True)
    end_time = models.TimeField("終了時刻", null=True, blank=True)
    memo = models.TextField("メモ", blank=True)
    category = models.CharField(
        "カテゴリ",
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "カレンダー予定"
        verbose_name_plural = "カレンダー予定"
        ordering = ["date", "start_time", "pk"]
        indexes = [
            models.Index(fields=["user", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.date} {self.title}"


class CourseCalendarException(models.Model):
    """時間割由来のカレンダー授業に対する日付単位の例外。

    TimetableSlot / CourseEnrollment は変更しない。
    現状は status=skipped（その日だけカレンダー非表示）のみ。
    """

    class Status(models.TextChoices):
        SKIPPED = "skipped", "非表示"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_calendar_exceptions",
        verbose_name="ユーザー",
    )
    offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.CASCADE,
        related_name="calendar_exceptions",
        verbose_name="開講授業",
    )
    date = models.DateField("対象日", db_index=True)
    status = models.CharField(
        "状態",
        max_length=20,
        choices=Status.choices,
        default=Status.SKIPPED,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "授業カレンダー例外"
        verbose_name_plural = "授業カレンダー例外"
        ordering = ["-date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "offering", "date"],
                name="unique_course_calendar_exception_per_day",
            )
        ]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.offering_id}@{self.date} ({self.status})"


class CourseAttendanceRecord(models.Model):
    """ユーザー個人の欠席記録（日付単位）。

    欠席回数は本テーブルの件数から算出する（整数カウンターは持たない）。
    CourseCalendarException（休講等の予定非表示）とは独立。
    週複数回開講でも Offering 単位で共通（Meeting は時間割セル用）。
    """

    class Status(models.TextChoices):
        ABSENT = "absent", "欠席"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_attendance_records",
        verbose_name="ユーザー",
    )
    offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name="開講授業",
        help_text="その日の開催スロットに対応する Offering",
    )
    date = models.DateField("対象日", db_index=True)
    status = models.CharField(
        "状態",
        max_length=20,
        choices=Status.choices,
        default=Status.ABSENT,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "授業欠席記録"
        verbose_name_plural = "授業欠席記録"
        ordering = ["-date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "offering", "date"],
                name="unique_course_attendance_per_day",
            )
        ]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["offering", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.offering_id}@{self.date} ({self.status})"


class Follow(models.Model):
    """承認済みフォロー関係のみを保持する（pending は FollowRequest）。"""

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


class FollowRequest(models.Model):
    """非公開アカウント向けのフォローリクエスト（pending のみ）。"""

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="follow_requests_sent",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="follow_requests_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_user", "to_user"],
                name="unique_follow_request",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_user=models.F("to_user")),
                name="follow_request_no_self",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"request {self.from_user_id} → {self.to_user_id}"


class SignupOTP(models.Model):
    """新規登録メール認証用のワンタイムコード（平文は保存しない）。"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signup_otp",
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)

    def __str__(self) -> str:
        return f"OTP for {self.user.email} (expires {self.expires_at})"


class PasswordResetOTP(models.Model):
    """パスワード再設定用のワンタイムコード（平文は保存しない）。"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_otp",
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Password reset OTP for {self.user.email} (expires {self.expires_at})"


class Product(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "出品中"
        PENDING = "pending", "取引中"
        SOLD = "sold", "売り切れ"

    # 旧ステータス値（DB移行前のデータ互換）
    _LEGACY_PENDING = "trading"
    _LEGACY_SOLD = "sold_out"

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
    handover_campus = models.CharField(
        "受け渡しキャンパス",
        max_length=32,
        choices=HANDOVER_CAMPUS_CHOICES,
        blank=True,
        default="",
        db_index=True,
    )
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
        return self.status in (self.Status.SOLD, self._LEGACY_SOLD)

    @property
    def is_pending(self) -> bool:
        return self.status in (self.Status.PENDING, self._LEGACY_PENDING)

    @property
    def is_trading(self) -> bool:
        """後方互換: 取引確定中（pending）。"""
        return self.is_pending

    @property
    def is_available(self) -> bool:
        return self.status == self.Status.AVAILABLE


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
        COURSE_OFFERING = "course_offering", "開講授業"
        COURSE_REVIEW = "course_review", "授業レビュー"
        CHAT_MESSAGE = "chat_message", "チャットメッセージ"

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

    class Kind(models.TextChoices):
        PRODUCT = "product", "商品チャット"
        GROUP = "group", "グループチャット"
        COURSE = "course", "授業トーク"

    class DealStatus(models.TextChoices):
        NEGOTIATING = "negotiating", "交渉中"
        CONFIRMED = "confirmed", "取引確定"
        CLOSED = "closed", "終了"

    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.PRODUCT,
        db_index=True,
    )
    # グループチャット時の表示名（任意）。既存の「商品チャット」では未使用。
    name = models.CharField(max_length=120, blank=True, default="")
    # グループ作成者（任意）。既存の「商品チャット」では未使用。
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_rooms_created_by",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="chat_rooms",
        null=True,
        blank=True,
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_chat_rooms",
        null=True,
        blank=True,
    )
    deal_status = models.CharField(
        max_length=20,
        choices=DealStatus.choices,
        default=DealStatus.NEGOTIATING,
        db_index=True,
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
        if self.kind == ChatRoom.Kind.COURSE:
            offering = getattr(self, "course_offering", None)
            if offering is not None:
                return f"授業トーク: {offering.title}"
            return f"授業トーク #{self.pk}"
        if self.kind == ChatRoom.Kind.GROUP:
            return self.name or f"グループチャット #{self.pk}"
        if self.product_id and self.buyer_id:
            return f"{self.product.name} × {self.buyer.username}"
        return f"チャットルーム #{self.pk}"

    @property
    def is_negotiating(self) -> bool:
        return self.deal_status == self.DealStatus.NEGOTIATING

    @property
    def is_confirmed(self) -> bool:
        return self.deal_status == self.DealStatus.CONFIRMED

    @property
    def is_closed(self) -> bool:
        return self.deal_status == self.DealStatus.CLOSED


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
        null=True,
        blank=True,
    )
    body = models.TextField(max_length=500)
    is_system = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        if self.is_system or not self.sender_id:
            return f"[system] {self.body[:30]}"
        return f"{self.sender}: {self.body[:30]}"


class ChatRoomMembership(models.Model):
    """ChatRoom に参加しているユーザー（グループチャット用）。"""

    class Role(models.TextChoices):
        OWNER = "owner", "管理者"
        MEMBER = "member", "メンバー"

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_memberships",
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.MEMBER,
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"],
                name="unique_chat_room_membership",
            )
        ]
        ordering = ["-joined_at"]

    def __str__(self) -> str:
        return f"{self.user_id} in room {self.room_id} ({self.role})"


class ChatRoomInvitation(models.Model):
    """
    グループチャット招待（承認制）。

    pending の間はメンバーではない。accepted で ChatRoomMembership を作成する。
    declined 後は同一 (room, invitee) を pending に戻して再招待できる。
    """

    class Status(models.TextChoices):
        PENDING = "pending", "招待中"
        ACCEPTED = "accepted", "参加済み"
        DECLINED = "declined", "辞退"

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_invitations_sent",
    )
    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_invitations_received",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "invitee"],
                name="unique_chat_room_invitation_per_invitee",
            ),
            models.CheckConstraint(
                condition=~models.Q(inviter=models.F("invitee")),
                name="chat_room_invitation_no_self",
            ),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"invite room={self.room_id} → {self.invitee_id} ({self.status})"


class ChatMessage(models.Model):
    """グループ／授業トーク用のメッセージ。"""

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages_sent",
    )
    body = models.TextField(max_length=500)
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name="返信先",
    )
    is_hidden = models.BooleanField(
        "非表示",
        default=False,
        db_index=True,
        help_text="モデレーションにより一覧から隠す",
    )
    deleted_at = models.DateTimeField(
        "ユーザー削除日時",
        null=True,
        blank=True,
        db_index=True,
        help_text="送信者によるソフト削除。モデレーションの is_hidden とは別。",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender}: {self.body[:30]}"

    @property
    def is_deleted_by_author(self) -> bool:
        return self.deleted_at is not None


class ChatReadState(models.Model):
    """グループチャットの既読位置（ユーザー単位）。"""

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="chat_read_states",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_read_states",
    )
    last_read_message_id = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"],
                name="unique_chat_read_state_per_user_room",
            )
        ]

    def __str__(self) -> str:
        return f"ChatRead {self.user_id} @ room {self.room_id}"


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


class UserDirectMessageReadState(models.Model):
    """DMルームごとの既読位置（ユーザー単位）。"""

    room = models.ForeignKey(
        UserDirectMessageRoom,
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dm_read_states",
    )
    last_read_message_id = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"],
                name="unique_dm_read_state_per_user_room",
            )
        ]

    def __str__(self) -> str:
        return f"DM read {self.user_id} @ room {self.room_id}"


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
    is_read = models.BooleanField(
        default=False,
        help_text="1対1 DM では相手が既読にしたか。グループ化時は ReadReceipt 等へ移行予定。",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender}: {self.body[:30]}"


class UserDirectMessageRequest(models.Model):
    """
    フォロー外ユーザーからの DM をメッセージリクエストとして扱う。

    pending の間は受信者の通常 DM 一覧に出さない。
    accepted で通常 DM に昇格。declined は一覧から外し、再送で pending に戻せる。
    """

    class Status(models.TextChoices):
        PENDING = "pending", "リクエスト中"
        ACCEPTED = "accepted", "承認済み"
        DECLINED = "declined", "拒否"

    room = models.ForeignKey(
        UserDirectMessageRoom,
        on_delete=models.CASCADE,
        related_name="message_requests",
    )
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dm_requests_sent",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dm_requests_received",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "to_user"],
                name="unique_dm_request_per_room_recipient",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_user=models.F("to_user")),
                name="dm_request_no_self",
            ),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"dm_request {self.from_user_id}→{self.to_user_id} ({self.status})"


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
        on_delete=models.SET_NULL,
        related_name="timeline_posts",
        null=True,
        blank=True,
    )
    quoted_post = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
        verbose_name="リポスト元投稿",
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
    like_count = models.PositiveIntegerField(default=0, db_default=0)
    view_count = models.PositiveIntegerField(default=0, db_default=0)
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

