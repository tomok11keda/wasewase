from datetime import timedelta
from unittest.mock import patch
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    ChatRoom,
    Comment,
    ContentReport,
    DevicePushToken,
    Follow,
    Message,
    Notification,
    Product,
    SignupOTP,
    TimelinePost,
    TradeMessage,
    UserDirectMessage,
    UserDirectMessageRoom,
    UserProfile,
)
from .dm_services import get_or_create_dm_room, ordered_user_pair
from .level_services import (
    compute_level_score,
    level_from_score,
    rank_title_from_level,
    recalculate_user_level,
    score_to_next_level,
)
from wasewase.email_env import (
    is_plausible_email,
    load_sanitized_email_env,
    sanitize_email_address,
)

from .otp_services import SIGNUP_PENDING_SESSION_KEY, create_and_send_signup_otp
from .services import build_product_share_timeline_body, notify_seller


class EmailEnvSanitizeTests(TestCase):
    def test_rejects_japanese_placeholder_email(self):
        self.assertEqual(
            sanitize_email_address("あなたのGmailアドレス", "WASE_EMAIL_HOST_USER"),
            "",
        )

    def test_accepts_valid_ascii_email(self):
        self.assertEqual(
            sanitize_email_address("user@gmail.com", "WASE_EMAIL_HOST_USER"),
            "user@gmail.com",
        )

    def test_load_marks_smtp_not_ready_for_placeholders(self):
        from wasewase import email_env

        original = email_env.WASE_USE_BUILTIN_GMAIL
        email_env.WASE_USE_BUILTIN_GMAIL = False
        try:
            user, password, from_email, smtp_ready = load_sanitized_email_env(
                "あなたの@gmail.com",
                "さっき取得した16桁のアプリパスワード",
                "",
            )
            self.assertFalse(smtp_ready)
            self.assertEqual(user, "")
            self.assertEqual(password, "")
            self.assertTrue(is_plausible_email(from_email))
        finally:
            email_env.WASE_USE_BUILTIN_GMAIL = original

    def test_builtin_config_overrides_invalid_env(self):
        user, password, from_email, smtp_ready = load_sanitized_email_env(
            "あなたの@gmail.com",
            "さっき取得した16桁のアプリパスワード",
            "",
        )
        self.assertTrue(smtp_ready)
        self.assertEqual(user, "wasewaseofficial@gmail.com")
        self.assertEqual(password, "qqxwgfaweaclghbv")
        self.assertIn("wasewaseofficial@gmail.com", from_email)


class EmailAuthTests(TestCase):
    def test_signup_allows_duplicate_nickname(self):
        get_user_model().objects.create_user(
            email="taken@example.com",
            password="password",
            username="taken_name",
        )
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            DEFAULT_FROM_EMAIL="test@waseda.jp",
        ):
            response = self.client.post(
                reverse("signup"),
                {
                    "email": "other@stu.waseda.jp",
                    "nickname": "たろう",
                    "password1": "newpass123",
                    "password2": "newpass123",
                    "faculty": "商学部",
                },
            )
        self.assertRedirects(response, reverse("verify_otp"))
        user = get_user_model().objects.get(email="other@stu.waseda.jp")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.name, "たろう")

    def test_signup_rejects_duplicate_email(self):
        get_user_model().objects.create_user(
            email="dup@waseda.jp",
            password="password",
        )
        response = self.client.post(
            reverse("signup"),
            {
                "email": "dup@waseda.jp",
                "nickname": "dup_user",
                "password1": "newpass123",
                "password2": "newpass123",
                "faculty": "商学部",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "すでに登録されています")

    def test_login_with_email_and_password(self):
        get_user_model().objects.create_user(
            email="login@example.com",
            password="secret123",
        )
        response = self.client.post(
            reverse("login"),
            {"username": "login@example.com", "password": "secret123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            get_user_model().objects.filter(email="login@example.com").exists()
        )

    def test_signup_rejects_non_waseda_email(self):
        response = self.client.post(
            reverse("signup"),
            {
                "email": "user@gmail.com",
                "nickname": "gmail_user",
                "password1": "newpass123",
                "password2": "newpass123",
                "faculty": "商学部",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "早稲田大学のメールアドレス（waseda.jp）のみ登録可能です",
        )
        self.assertFalse(
            get_user_model().objects.filter(email="user@gmail.com").exists()
        )

    def test_signup_accepts_subdomain_waseda_email(self):
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            DEFAULT_FROM_EMAIL="test@waseda.jp",
        ):
            response = self.client.post(
                reverse("signup"),
                {
                    "email": "student@my.waseda.jp",
                    "nickname": "wase_student",
                    "password1": "newpass123",
                    "password2": "newpass123",
                    "faculty": "商学部",
                },
            )
        self.assertRedirects(response, reverse("verify_otp"))
        self.assertTrue(
            get_user_model().objects.filter(email="student@my.waseda.jp").exists()
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    def test_signup_sends_otp_and_redirects_to_verify(self):
        response = self.client.post(
            reverse("signup"),
            {
                "email": "new@waseda.jp",
                "nickname": "wase_taro",
                "password1": "newpass123",
                "password2": "newpass123",
                "faculty": "法学部",
            },
        )
        self.assertRedirects(response, reverse("verify_otp"))
        user = get_user_model().objects.get(email="new@waseda.jp")
        self.assertEqual(user.username, f"user_{user.pk}")
        self.assertFalse(user.is_active)
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.name, "wase_taro")
        self.assertEqual(profile.department, "法学部")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("認証コード", mail.outbox[0].subject)
        self.assertTrue(SignupOTP.objects.filter(user=user).exists())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    def test_verify_otp_activates_user_and_logs_in(self):
        user = get_user_model().objects.create_user(
            email="verify@example.com",
            password="newpass123",
            is_active=False,
        )
        UserProfile.objects.create(user=user, department="商学部")
        code = create_and_send_signup_otp(user)
        session = self.client.session
        session[SIGNUP_PENDING_SESSION_KEY] = user.pk
        session.save()

        response = self.client.post(
            reverse("verify_otp"),
            {"code": code},
        )
        self.assertRedirects(response, reverse("home"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(SignupOTP.objects.filter(user=user).exists())

    def test_verify_otp_rejects_wrong_code(self):
        user = get_user_model().objects.create_user(
            email="wrong@example.com",
            password="pass",
            is_active=False,
        )
        SignupOTP.objects.create(
            user=user,
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        session = self.client.session
        session[SIGNUP_PENDING_SESSION_KEY] = user.pk
        session.save()

        response = self.client.post(
            reverse("verify_otp"),
            {"code": "000000"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "正しくありません")
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_inactive_user_cannot_login(self):
        get_user_model().objects.create_user(
            email="inactive@example.com",
            password="secret123",
            is_active=False,
        )
        response = self.client.post(
            reverse("login"),
            {"username": "inactive@example.com", "password": "secret123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "メールアドレスまたはパスワードが正しくありません")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    def test_pending_user_can_resignup_and_redirects_to_verify(self):
        get_user_model().objects.create_user(
            email="pending@waseda.jp",
            password="oldpass123",
            is_active=False,
        )
        response = self.client.post(
            reverse("signup"),
            {
                "email": "pending@waseda.jp",
                "nickname": "pending_user",
                "password1": "newpass123",
                "password2": "newpass123",
                "faculty": "商学部",
            },
        )
        self.assertRedirects(response, reverse("verify_otp"))
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    def test_verify_otp_resend_sends_mail(self):
        user = get_user_model().objects.create_user(
            email="resend@example.com",
            password="pass",
            is_active=False,
        )
        session = self.client.session
        session[SIGNUP_PENDING_SESSION_KEY] = user.pk
        session.save()

        response = self.client.post(reverse("verify_otp_resend"))
        self.assertRedirects(response, reverse("verify_otp"))
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    def test_signup_shows_validation_errors_in_messages(self):
        response = self.client.post(
            reverse("signup"),
            {
                "email": "bad@gmail.com",
                "nickname": "bad_user",
                "password1": "newpass123",
                "password2": "different",
                "faculty": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "パスワード")


class GlobalSearchTests(TestCase):
    def setUp(self):
        self.seller = get_user_model().objects.create_user(
            email="seller@example.com",
            password="password",
            username="seller",
        )
        self.poster = get_user_model().objects.create_user(
            email="poster@example.com",
            password="password",
            username="poster",
        )

    def test_search_finds_product_by_name_and_description(self):
        Product.objects.create(
            seller=self.seller,
            name="古着デニム",
            description="サイズMのジャケット",
            price=3000,
            category="服",
        )
        Product.objects.create(
            seller=self.seller,
            name="別商品",
            description="関係なし",
            price=100,
            category="本",
        )

        response = self.client.get(reverse("search"), {"q": "デニム"})
        self.assertContains(response, "古着デニム")
        self.assertNotContains(response, "別商品")
        self.assertContains(response, "フリマの検索結果")

    def test_search_finds_timeline_by_body(self):
        TimelinePost.objects.create(
            author=self.poster,
            body="明日のゼミの予習は第3章まで",
        )
        TimelinePost.objects.create(
            author=self.poster,
            body="今日は晴れ",
        )

        response = self.client.get(reverse("search"), {"q": "ゼミ"})
        self.assertContains(response, "明日のゼミの予習は第3章まで")
        self.assertNotContains(response, "今日は晴れ")
        self.assertContains(response, "スレッドの検索結果")

    def test_search_shows_both_sections(self):
        Product.objects.create(
            seller=self.seller,
            name="教科書セット",
            description="線形代数の参考書",
            price=2000,
            category="本",
        )
        TimelinePost.objects.create(
            author=self.poster,
            body="線形代数の過去問を共有します",
        )

        response = self.client.get(reverse("search"), {"q": "線形代数"})
        self.assertContains(response, "教科書セット")
        self.assertContains(response, "過去問を共有します")

    def test_search_empty_query_shows_prompt(self):
        response = self.client.get(reverse("search"))
        self.assertContains(response, "キーワードを入力")


class BoardTimelineSearchTests(TestCase):
    def test_board_search_matches_professor_name(self):
        user = get_user_model().objects.create_user(
            email="poster@example.com",
            password="password",
        )
        TimelinePost.objects.create(
            author=user,
            body="中間レポートは講義資料を見れば大丈夫です。",
            course_name="社会学入門",
            professor_name="佐藤花子",
        )
        TimelinePost.objects.create(
            author=user,
            body="期末試験は持ち込み不可です。",
            course_name="統計学",
            professor_name="山田太郎",
        )

        response = self.client.get(reverse("home"), { "q": "佐藤"})

        self.assertContains(response, "中間レポートは講義資料を見れば大丈夫です。")
        self.assertNotContains(response, "期末試験は持ち込み不可です。")

    def test_board_filter_matches_faculty(self):
        user = get_user_model().objects.create_user(
            email="faculty-poster@example.com",
            password="password",
        )
        TimelinePost.objects.create(
            author=user,
            body="社学向けの履修情報です。",
            course_name="社会科学入門",
            faculty="社会科学部",
        )
        TimelinePost.objects.create(
            author=user,
            body="理工向けの履修情報です。",
            course_name="情報数学",
            faculty="基幹理工学部",
        )

        response = self.client.get(
            reverse("home"),
            {"faculty": "社会科学部"},
        )

        self.assertContains(response, "社学向けの履修情報です。")
        self.assertNotContains(response, "理工向けの履修情報です。")


class BoardTimelineImageTests(TestCase):
    _MINIMAL_GIF = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\x00\x00\x00\x00\x00!\xf9\x04"
        b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x01D\x00;"
    )

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="photo@example.com",
            password="password",
        )

    def test_board_compose_saves_image_and_shows_on_timeline(self):
        self.client.force_login(self.user)
        image = SimpleUploadedFile(
            "timeline.gif", self._MINIMAL_GIF, content_type="image/gif"
        )
        response = self.client.post(
            reverse("board_compose"),
            {
                "body": "板書の写真です",
                "course_name": "線形代数",
                "professor_name": "",
                "faculty": "基幹理工学部",
                "image": image,
            },
        )
        self.assertEqual(response.status_code, 302)
        post = TimelinePost.objects.get(body="板書の写真です")
        self.assertTrue(post.image.name.startswith("post_images/"))

        page = self.client.get(reverse("home"))
        self.assertContains(page, "板書の写真です")
        self.assertContains(page, post.image.url)

    def test_board_compose_allows_post_without_course_info(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("board_compose"),
            {
                "body": "テキストだけの投稿です",
                "course_name": "",
                "professor_name": "",
                "faculty": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        post = TimelinePost.objects.get(body="テキストだけの投稿です")
        self.assertIsNone(post.course_name)
        self.assertIsNone(post.professor_name)
        self.assertEqual(post.faculty, "")

        page = self.client.get(reverse("home"))
        self.assertContains(page, "テキストだけの投稿です")

    def test_board_compose_redirects_to_unfiltered_timeline(self):
        other = get_user_model().objects.create_user(
            email="other@example.com",
            password="password",
        )
        TimelinePost.objects.create(
            author=other,
            body="別授業の投稿です",
            course_name="統計学",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("board_compose"),
            {
                "body": "線形代数のメモです",
                "course_name": "線形代数",
                "professor_name": "",
                "faculty": "基幹理工学部",
            },
        )

        self.assertEqual(response.status_code, 302)
        post = TimelinePost.objects.get(body="線形代数のメモです")
        self.assertEqual(
            response["Location"],
            f"{reverse('home')}#post-{post.pk}",
        )
        self.assertNotIn("tag=", response["Location"])

        page = self.client.get(reverse("home"))
        self.assertContains(page, "線形代数のメモです")
        self.assertContains(page, "別授業の投稿です")


class BoardTimelineNotificationTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(
            email="author@example.com",
            password="password",
        )
        self.actor = get_user_model().objects.create_user(
            email="actor@example.com",
            password="password",
            username="actor",
        )
        self.post = TimelinePost.objects.create(
            author=self.author,
            body="試験範囲の共有です。",
            course_name="民法",
            professor_name="田中先生",
        )

    def test_like_notifies_timeline_post_author(self):
        self.client.force_login(self.actor)

        response = self.client.post(reverse("board_timeline_like", args=[self.post.pk]))

        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.like_count, 1)
        notification = Notification.objects.get(recipient=self.author)
        self.assertEqual(
            notification.message,
            "actorさんがあなたの投稿にいいねしました",
        )
        self.assertEqual(
            notification.link,
            f"{reverse('home')}?tag={quote('民法')}#post-{self.post.pk}",
        )

    def test_god_notifies_timeline_post_author(self):
        self.client.force_login(self.actor)

        response = self.client.post(reverse("board_timeline_god", args=[self.post.pk]))

        self.assertEqual(response.status_code, 302)
        notification = Notification.objects.get(recipient=self.author)
        self.assertEqual(
            notification.message,
            "actorさんがあなたの投稿を『神！』と言っています",
        )
        self.assertEqual(
            notification.link,
            f"{reverse('home')}?tag={quote('民法')}#post-{self.post.pk}",
        )

    def test_like_toggle_decrements_count(self):
        self.client.force_login(self.actor)
        self.client.post(reverse("board_timeline_like", args=[self.post.pk]))
        self.client.post(reverse("board_timeline_like", args=[self.post.pk]))
        self.post.refresh_from_db()
        self.assertEqual(self.post.like_count, 0)

    def test_self_like_and_god_do_not_create_notifications(self):
        self.client.force_login(self.author)

        self.client.post(reverse("board_timeline_like", args=[self.post.pk]))
        self.client.post(reverse("board_timeline_god", args=[self.post.pk]))

        self.assertFalse(Notification.objects.filter(recipient=self.author).exists())

    def test_comment_creates_timeline_comment_and_notification(self):
        self.client.force_login(self.actor)

        response = self.client.post(
            reverse("board_timeline_comment", args=[self.post.pk]),
            {"body": "ありがとうございます！"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"#post-{self.post.pk}", response["Location"])
        comment = Comment.objects.get(timeline_post=self.post)
        self.assertEqual(comment.author, self.actor)
        self.assertEqual(comment.body, "ありがとうございます！")
        notification = Notification.objects.get(recipient=self.author)
        self.assertEqual(
            notification.message,
            f"「{self.actor.username}さんがあなたの投稿にコメントしました」",
        )
        self.assertEqual(
            notification.link,
            f"{reverse('home')}?tag={quote('民法')}#post-{self.post.pk}",
        )

    def test_self_comment_does_not_create_notification(self):
        self.client.force_login(self.author)

        self.client.post(
            reverse("board_timeline_comment", args=[self.post.pk]),
            {"body": "補足です。"},
        )

        self.assertTrue(Comment.objects.filter(timeline_post=self.post).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.author).exists())

    def test_board_timeline_shows_comment_count_and_body(self):
        Comment.objects.create(
            timeline_post=self.post,
            author=self.actor,
            body="助かりました。",
        )

        response = self.client.get(reverse("home"))

        self.assertContains(response, "💬 1")
        self.assertContains(response, "助かりました。")


class SocialFeaturesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.author = User.objects.create_user(
            email="author@example.com",
            password="password",
            username="post_author",
        )
        UserProfile.objects.create(user=self.author, name="投稿者")
        self.mentioned = User.objects.create_user(
            email="mentioned@example.com",
            password="password",
            username="mention_me",
        )
        UserProfile.objects.create(user=self.mentioned, name="メンション先")
        self.actor = User.objects.create_user(
            email="actor@example.com",
            password="password",
            username="quote_actor",
        )
        self.original = TimelinePost.objects.create(
            author=self.author,
            body="引用される元投稿です。",
            course_name="民法",
        )

    def test_post_mention_creates_notification(self):
        self.client.force_login(self.actor)
        response = self.client.post(
            reverse("board_compose"),
            {"body": "こんにちは @mention_me さん", "course_name": "", "professor_name": "", "faculty": ""},
        )
        self.assertEqual(response.status_code, 302)
        notification = Notification.objects.get(recipient=self.mentioned)
        self.assertIn("メンション", notification.message)

    def test_comment_mention_creates_notification(self):
        self.client.force_login(self.actor)
        self.client.post(
            reverse("board_timeline_comment", args=[self.original.pk]),
            {"body": "@mention_me 見てください"},
        )
        notification = Notification.objects.get(recipient=self.mentioned)
        self.assertIn("メンション", notification.message)

    def test_quote_post_renders_embedded_card(self):
        self.client.force_login(self.actor)
        response = self.client.post(
            reverse("board_compose"),
            {
                "body": "これについて意見です",
                "quoted_post_id": self.original.pk,
                "course_name": "",
                "professor_name": "",
                "faculty": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        quote = TimelinePost.objects.get(body="これについて意見です")
        self.assertEqual(quote.quoted_post_id, self.original.pk)

        page = self.client.get(reverse("home"))
        self.assertContains(page, "quoted-post-card")
        self.assertContains(page, "引用される元投稿です。")

    def test_board_quote_redirects_to_compose(self):
        self.client.force_login(self.actor)
        response = self.client.get(reverse("board_quote", args=[self.original.pk]))
        self.assertRedirects(
            response,
            f"{reverse('home')}?quote={self.original.pk}#compose",
        )

    def test_signup_assigns_user_pk_handle(self):
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            DEFAULT_FROM_EMAIL="test@waseda.jp",
        ):
            response = self.client.post(
                reverse("signup"),
                {
                    "email": "handle@waseda.jp",
                    "nickname": "表示名テスト",
                    "password1": "newpass123",
                    "password2": "newpass123",
                    "faculty": "商学部",
                },
            )
        self.assertRedirects(response, reverse("verify_otp"))
        user = get_user_model().objects.get(email="handle@waseda.jp")
        self.assertEqual(user.username, f"user_{user.pk}")
        self.assertEqual(UserProfile.objects.get(user=user).name, "表示名テスト")

    def test_mypage_edit_rejects_duplicate_handle(self):
        self.client.force_login(self.actor)
        response = self.client.post(
            reverse("mypage_edit"),
            {
                "name": "",
                "user_id": "mention_me",
                "bio": "",
                "department": "",
                "grade": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "すでに使われています")


class ProductTimestampDisplayTests(TestCase):
    def setUp(self):
        self.seller = get_user_model().objects.create_user(
            email="seller@example.com",
            password="password",
        )
        self.buyer = get_user_model().objects.create_user(
            email="buyer@example.com",
            password="password",
        )
        self.product = Product.objects.create(
            seller=self.seller,
            name="線形代数の教科書",
            price=1000,
            description="書き込み少なめです。",
            category="未分類",
            faculty="基幹理工学部",
        )

    def test_home_product_card_shows_seller_and_posted_time(self):
        response = self.client.get(reverse("home"), {"tab": "flea"})

        self.assertContains(response, "線形代数の教科書")
        self.assertContains(response, "seller")
        self.assertContains(response, "前")

    def test_product_detail_shows_posted_time_and_comment_author_time(self):
        Comment.objects.create(
            product=self.product,
            author=self.buyer,
            body="まだ購入できますか？",
        )

        response = self.client.get(reverse("product_detail", args=[self.product.pk]))

        self.assertContains(response, "出品日時:")
        self.assertContains(response, "buyer")
        self.assertContains(response, "まだ購入できますか？")
        self.assertContains(response, "前")

    def test_product_comment_saves_logged_in_author(self):
        self.client.force_login(self.buyer)

        self.client.post(
            reverse("product_detail", args=[self.product.pk]),
            {"body": "購入したいです。"},
        )

        comment = Comment.objects.get(product=self.product, body="購入したいです。")
        self.assertEqual(comment.author, self.buyer)

    def test_home_product_filter_matches_faculty(self):
        Product.objects.create(
            seller=self.seller,
            name="法学部の参考書",
            price=800,
            description="",
            category="未分類",
            faculty="法学部",
        )

        response = self.client.get(
            reverse("home"), {"tab": "flea", "faculty": "基幹理工学部"}
        )

        self.assertContains(response, "線形代数の教科書")
        self.assertNotContains(response, "法学部の参考書")
        self.assertContains(response, "基幹理工学部で絞り込み中")

    def test_home_shows_all_faculty_tabs(self):
        response = self.client.get(reverse("home"))

        for faculty in (
            "政治経済学部",
            "法学部",
            "教育学部",
            "商学部",
            "社会科学部",
            "国際教養学部",
            "文化構想学部",
            "文学部",
            "基幹理工学部",
            "創造理工学部",
            "先進理工学部",
            "人間科学部",
            "スポーツ科学部",
            "その他",
        ):
            self.assertContains(response, faculty)


class ProductTradeFlowTests(TestCase):
    def setUp(self):
        self.seller = get_user_model().objects.create_user(
            email="trade-seller@example.com",
            password="password",
        )
        self.buyer = get_user_model().objects.create_user(
            email="trade-buyer@example.com",
            password="password",
        )
        self.other = get_user_model().objects.create_user(
            email="other@example.com",
            password="password",
        )
        self.product = Product.objects.create(
            seller=self.seller,
            name="取引テスト商品",
            price=1200,
            description="",
            category="未分類",
            faculty="商学部",
        )

    def test_purchase_starts_trade_without_selling_out(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("purchase_product", args=[self.product.pk])
        )

        self.product.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("product_trade", args=[self.product.pk]),
        )
        self.assertEqual(self.product.status, Product.Status.TRADING)
        self.assertEqual(self.product.buyer, self.buyer)
        self.assertFalse(self.product.is_sold)

    def test_other_user_cannot_access_or_buy_trading_product(self):
        self.product.status = Product.Status.TRADING
        self.product.buyer = self.buyer
        self.product.save(update_fields=["status", "buyer"])
        self.client.force_login(self.other)

        trade_response = self.client.get(
            reverse("product_trade", args=[self.product.pk])
        )
        purchase_response = self.client.post(
            reverse("purchase_product", args=[self.product.pk])
        )

        self.product.refresh_from_db()
        self.assertEqual(trade_response.status_code, 302)
        self.assertEqual(purchase_response.status_code, 302)
        self.assertEqual(self.product.buyer, self.buyer)
        self.assertEqual(self.product.status, Product.Status.TRADING)

    def test_trade_chat_saves_message_for_participants(self):
        self.product.status = Product.Status.TRADING
        self.product.buyer = self.buyer
        self.product.save(update_fields=["status", "buyer"])
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("send_trade_message", args=[self.product.pk]),
            {"body": "大隈講堂前でお願いします。"},
        )

        self.assertEqual(response.status_code, 302)
        message = TradeMessage.objects.get(product=self.product)
        self.assertEqual(message.sender, self.buyer)
        self.assertEqual(message.body, "大隈講堂前でお願いします。")

    def test_trade_completes_only_after_both_confirm(self):
        self.product.status = Product.Status.TRADING
        self.product.buyer = self.buyer
        self.product.save(update_fields=["status", "buyer"])

        self.client.force_login(self.buyer)
        self.client.post(reverse("complete_trade", args=[self.product.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.TRADING)
        self.assertTrue(self.product.buyer_trade_completed)
        self.assertFalse(self.product.seller_trade_completed)

        self.client.force_login(self.seller)
        self.client.post(reverse("complete_trade", args=[self.product.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.SOLD_OUT)
        self.assertTrue(self.product.is_sold)
        self.assertTrue(self.product.seller_trade_completed)


class ProfileAndFollowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(
            email="viewer@example.com",
            password="pass12345",
            username="viewer",
        )
        self.target = User.objects.create_user(
            email="target@example.com",
            password="pass12345",
            username="target",
        )
        UserProfile.objects.create(
            user=self.target,
            name="たろう",
            bio="よろしく",
            department="法学部",
            grade="2年",
        )

    def test_mypage_edit_updates_display_name_user_id_and_profile(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("mypage_edit"),
            {
                "name": "テストユーザー1",
                "user_id": "jiro_new",
                "bio": "テスト概要",
                "department": "商学部",
                "grade": "3年",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("mypage"))
        self.viewer.refresh_from_db()
        self.assertEqual(self.viewer.username, "jiro_new")
        profile = UserProfile.objects.get(user=self.viewer)
        self.assertEqual(profile.name, "テストユーザー1")
        self.assertEqual(profile.bio, "テスト概要")
        self.assertEqual(profile.department, "商学部")
        self.assertEqual(profile.grade, "3年")

    def test_display_name_and_user_id_reflect_separately(self):
        self.client.force_login(self.viewer)
        self.client.post(
            reverse("mypage_edit"),
            {
                "name": "新しい表示名",
                "user_id": "new_user_id",
                "bio": "",
                "department": "",
                "grade": "",
            },
        )
        Product.objects.create(
            seller=self.viewer,
            name="テスト商品",
            price=500,
            category="本",
        )
        TimelinePost.objects.create(author=self.viewer, body="表示名テスト投稿")

        home = self.client.get(reverse("home"), {"tab": "flea"})
        self.assertContains(home, "新しい表示名")
        self.assertNotContains(home, "new_user_id")
        board = self.client.get(reverse("home"))
        self.assertContains(board, "新しい表示名")

        profile_page = self.client.get(
            reverse("user_profile", args=[self.viewer.pk]),
            {"from": "market"},
        )
        self.assertContains(profile_page, "新しい表示名")
        self.assertContains(profile_page, "@new_user_id")

    def test_mypage_edit_persists_after_reload(self):
        self.client.force_login(self.viewer)
        self.client.post(
            reverse("mypage_edit"),
            {
                "name": "リロード後も残る名前",
                "user_id": "persist_user",
                "bio": "",
                "department": "",
                "grade": "",
            },
        )
        mypage = self.client.get(reverse("mypage"))
        self.assertContains(mypage, "リロード後も残る名前")
        self.assertContains(mypage, "@persist_user")

        profile = UserProfile.objects.get(user=self.viewer)
        self.viewer.refresh_from_db()
        self.assertEqual(profile.name, "リロード後も残る名前")
        self.assertEqual(self.viewer.username, "persist_user")

    def test_user_profile_shows_product_count_from_market(self):
        Product.objects.create(
            seller=self.target,
            name="本",
            price=500,
            category="本",
        )
        response = self.client.get(
            reverse("user_profile", args=[self.target.pk]),
            {"from": "market"},
        )
        self.assertContains(response, "たろう")
        self.assertContains(response, "@target")
        self.assertContains(response, "よろしく")
        self.assertContains(response, "法学部 2年")
        self.assertContains(response, "出品数")
        self.assertContains(response, ">1<", html=False)
        self.assertContains(response, "この人の投稿（スレッド）を見る")
        self.assertContains(response, "?from=thread")

    def test_user_profile_shows_post_count_from_thread(self):
        TimelinePost.objects.create(
            author=self.target,
            body="板書メモ",
            course_name="線形代数",
        )
        response = self.client.get(
            reverse("user_profile", args=[self.target.pk]),
            {"from": "thread"},
        )
        self.assertContains(response, "投稿数")
        self.assertContains(response, "この人の出品（フリマ）を見る")
        self.assertContains(response, "?from=market")

    def test_toggle_follow(self):
        self.client.force_login(self.viewer)
        follow_url = reverse("toggle_follow", args=[self.target.pk])
        profile_url = reverse("user_profile", args=[self.target.pk])

        self.client.post(follow_url, {"next": profile_url})
        from app.models import Follow

        self.assertTrue(
            Follow.objects.filter(
                follower=self.viewer, following=self.target
            ).exists()
        )
        notification = Notification.objects.get(recipient=self.target)
        self.assertEqual(
            notification.message,
            f"「{self.viewer.username}さんにフォローされました！」",
        )
        self.assertEqual(
            notification.link,
            reverse("user_profile", args=[self.viewer.pk]),
        )

        response = self.client.get(profile_url)
        self.assertContains(response, "フォロー解除")

        self.client.post(follow_url, {"next": profile_url})
        self.assertFalse(
            Follow.objects.filter(
                follower=self.viewer, following=self.target
            ).exists()
        )


class FeedAndShareTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(
            email="viewer@example.com",
            password="pass12345",
            username="viewer",
        )
        self.seller = User.objects.create_user(
            email="seller@example.com",
            password="pass12345",
            username="seller",
        )
        self.other = User.objects.create_user(
            email="other@example.com",
            password="pass12345",
            username="other",
        )
        Follow.objects.create(follower=self.viewer, following=self.seller)
        self.followed_product = Product.objects.create(
            seller=self.seller,
            name="フォロー出品",
            price=1000,
            category="本",
        )
        Product.objects.create(
            seller=self.other,
            name="その他出品",
            price=500,
            category="本",
        )
        TimelinePost.objects.create(
            author=self.seller,
            body="フォロー投稿",
            course_name="線形代数",
        )
        TimelinePost.objects.create(
            author=self.other,
            body="その他投稿",
            course_name="微分積分",
        )

    def test_flea_following_feed_shows_only_followed_seller_products(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("home"), {"tab": "flea", "feed": "following"})
        self.assertContains(response, "フォロー出品")
        self.assertNotContains(response, "その他出品")

    def test_board_following_feed_shows_only_followed_posts(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("home"), {"feed": "following"})
        self.assertContains(response, "フォロー投稿")
        self.assertNotContains(response, "その他投稿")

    def test_following_feed_prompts_login_when_anonymous(self):
        response = self.client.get(reverse("home"), {"tab": "flea", "feed": "following"})
        self.assertContains(response, "ログイン")
        self.assertNotContains(response, "フォロー出品")

    def test_share_product_to_timeline(self):
        product = Product.objects.create(
            seller=self.seller,
            name="シェア本",
            price=800,
            category="本",
            course_name="経済学",
        )
        self.client.force_login(self.seller)
        detail_url = f"http://testserver{reverse('product_detail', args=[product.pk])}"
        expected_body = build_product_share_timeline_body(product, detail_url)

        response = self.client.post(
            reverse("share_product_to_timeline", args=[product.pk]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        post = TimelinePost.objects.latest("created_at")
        self.assertEqual(post.author, self.seller)
        self.assertEqual(post.body, expected_body)
        self.assertEqual(post.course_name, "経済学")

    def test_share_product_to_timeline_without_course_name(self):
        product = Product.objects.create(
            seller=self.seller,
            name="ノート",
            price=300,
            category="本",
        )
        self.client.force_login(self.seller)
        self.client.post(
            reverse("share_product_to_timeline", args=[product.pk]),
            follow=True,
        )
        post = TimelinePost.objects.latest("created_at")
        self.assertIsNone(post.course_name)


class DeleteContentTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            email="owner@example.com",
            password="password",
            username="owner",
        )
        self.other = get_user_model().objects.create_user(
            email="other@example.com",
            password="password",
            username="other",
        )
        self.post = TimelinePost.objects.create(
            author=self.owner,
            body="削除テスト投稿",
            course_name="憲法",
        )
        self.product = Product.objects.create(
            seller=self.owner,
            name="削除テスト商品",
            price=500,
            category="本",
        )

    def test_owner_can_delete_timeline_post(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("delete_timeline_post", args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('home')}?tag={quote('憲法')}")
        self.assertFalse(TimelinePost.objects.filter(pk=self.post.pk).exists())

    def test_other_user_cannot_delete_timeline_post(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("delete_timeline_post", args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TimelinePost.objects.filter(pk=self.post.pk).exists())

    def test_timeline_shows_delete_only_for_author(self):
        self.client.force_login(self.owner)
        owner_page = self.client.get(reverse("home"))
        self.assertContains(owner_page, "btn-tweet-delete")
        self.assertContains(owner_page, reverse("delete_timeline_post", args=[self.post.pk]))

        self.client.force_login(self.other)
        other_page = self.client.get(reverse("home"))
        self.assertNotContains(other_page, reverse("delete_timeline_post", args=[self.post.pk]))

    def test_owner_can_delete_product(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("delete_product", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('home')}?tab=flea")
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

    def test_other_user_cannot_delete_product(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("delete_product", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_product_detail_shows_delete_only_for_seller(self):
        self.client.force_login(self.owner)
        owner_page = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertContains(owner_page, "この商品を削除する")
        self.assertContains(owner_page, reverse("delete_product", args=[self.product.pk]))

        self.client.force_login(self.other)
        other_page = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertNotContains(other_page, "この商品を削除する")


class DeleteCommentTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            email="owner@example.com",
            password="password",
        )
        self.other = get_user_model().objects.create_user(
            email="other@example.com",
            password="password",
        )
        self.product = Product.objects.create(
            seller=self.owner,
            name="コメント削除商品",
            price=300,
            category="本",
        )
        self.timeline_post = TimelinePost.objects.create(
            author=self.owner,
            body="親投稿",
            course_name="刑法",
        )
        self.product_comment = Comment.objects.create(
            product=self.product,
            author=self.owner,
            body="商品へのコメント",
        )
        self.timeline_comment = Comment.objects.create(
            timeline_post=self.timeline_post,
            author=self.owner,
            body="タイムラインへのコメント",
        )

    def test_owner_can_delete_product_comment(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("delete_comment", args=[self.product_comment.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("product_detail", args=[self.product.pk]),
        )
        self.assertFalse(
            Comment.objects.filter(pk=self.product_comment.pk).exists()
        )

    def test_owner_can_delete_timeline_comment(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("delete_comment", args=[self.timeline_comment.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{reverse('home')}?tag={quote('刑法')}#post-{self.timeline_post.pk}",
        )
        self.assertFalse(
            Comment.objects.filter(pk=self.timeline_comment.pk).exists()
        )

    def test_other_user_cannot_delete_comment(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("delete_comment", args=[self.product_comment.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Comment.objects.filter(pk=self.product_comment.pk).exists()
        )

    def test_product_detail_shows_comment_delete_only_for_author(self):
        Comment.objects.create(
            product=self.product,
            author=self.other,
            body="他人のコメント",
        )
        self.client.force_login(self.owner)
        page = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertContains(
            page,
            reverse("delete_comment", args=[self.product_comment.pk]),
        )
        other_comment = Comment.objects.get(product=self.product, author=self.other)
        delete_urls = page.content.decode().count(
            reverse("delete_comment", args=[other_comment.pk])
        )
        self.assertEqual(delete_urls, 0)

    def test_timeline_shows_comment_delete_only_for_author(self):
        Comment.objects.create(
            timeline_post=self.timeline_post,
            author=self.other,
            body="他人の返信",
        )
        self.client.force_login(self.owner)
        page = self.client.get(reverse("home"))
        self.assertContains(
            page,
            reverse("delete_comment", args=[self.timeline_comment.pk]),
        )
        other_comment = Comment.objects.get(
            timeline_post=self.timeline_post, author=self.other
        )
        self.assertNotContains(
            page,
            reverse("delete_comment", args=[other_comment.pk]),
        )


class ProductChatTests(TestCase):
    def setUp(self):
        self.seller = get_user_model().objects.create_user(
            email="chat-seller@example.com",
            password="password",
        )
        self.buyer = get_user_model().objects.create_user(
            email="chat-buyer@example.com",
            password="password",
        )
        self.other = get_user_model().objects.create_user(
            email="chat-other@example.com",
            password="password",
        )
        self.product = Product.objects.create(
            seller=self.seller,
            name="チャットテスト商品",
            price=900,
            category="本",
        )

    def test_buyer_starts_chat_and_reuses_room(self):
        self.client.force_login(self.buyer)
        response = self.client.post(reverse("start_product_chat", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)
        room = ChatRoom.objects.get(product=self.product, buyer=self.buyer)
        self.assertEqual(response["Location"], reverse("chat_room", args=[room.pk]))

        response2 = self.client.post(reverse("start_product_chat", args=[self.product.pk]))
        self.assertEqual(ChatRoom.objects.filter(product=self.product).count(), 1)
        self.assertEqual(response2["Location"], reverse("chat_room", args=[room.pk]))

    def test_seller_cannot_start_chat(self):
        self.client.force_login(self.seller)
        response = self.client.post(reverse("start_product_chat", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ChatRoom.objects.filter(product=self.product).exists())

    def test_other_user_cannot_access_chat_room(self):
        room = ChatRoom.objects.create(product=self.product, buyer=self.buyer)
        self.client.force_login(self.other)
        response = self.client.get(reverse("chat_room", args=[room.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("product_detail", args=[self.product.pk]),
        )

    def test_participants_can_send_and_receive_messages(self):
        room = ChatRoom.objects.create(product=self.product, buyer=self.buyer)
        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("send_chat_message", args=[room.pk]),
            {"body": "こんにちは、購入希望です。"},
        )
        self.assertEqual(response.status_code, 302)
        message = Message.objects.get(chat_room=room)
        self.assertEqual(message.sender, self.buyer)
        self.assertEqual(message.body, "こんにちは、購入希望です。")

        self.client.force_login(self.seller)
        page = self.client.get(reverse("chat_room", args=[room.pk]))
        self.assertContains(page, "こんにちは、購入希望です。")

    def test_chat_room_uses_partial_poll_instead_of_meta_refresh(self):
        room = ChatRoom.objects.create(product=self.product, buyer=self.buyer)
        self.client.force_login(self.buyer)
        page = self.client.get(reverse("chat_room", args=[room.pk]))
        self.assertNotContains(page, 'http-equiv="refresh"')
        self.assertContains(page, 'id="message-area"')
        self.assertContains(page, 'id="message-input"')
        self.assertContains(page, reverse("chat_room_messages", args=[room.pk]))

    def test_chat_room_messages_api_returns_only_new_messages(self):
        room = ChatRoom.objects.create(product=self.product, buyer=self.buyer)
        first = Message.objects.create(
            chat_room=room,
            sender=self.buyer,
            body="1通目",
        )
        second = Message.objects.create(
            chat_room=room,
            sender=self.seller,
            body="2通目",
        )
        self.client.force_login(self.buyer)
        response = self.client.get(
            reverse("chat_room_messages", args=[room.pk]),
            {"after": first.pk},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["latest_id"], second.pk)
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["id"], second.pk)
        self.assertEqual(data["messages"][0]["body"], "2通目")
        self.assertTrue(data["messages"][0]["is_mine"] is False)

    def test_other_user_cannot_poll_chat_room_messages(self):
        room = ChatRoom.objects.create(product=self.product, buyer=self.buyer)
        self.client.force_login(self.other)
        response = self.client.get(reverse("chat_room_messages", args=[room.pk]))
        self.assertEqual(response.status_code, 403)

    def test_product_detail_shows_chat_button_for_non_seller(self):
        self.client.force_login(self.buyer)
        page = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertContains(page, "出品者にチャットで連絡する")
        self.assertContains(page, reverse("start_product_chat", args=[self.product.pk]))

    def test_product_detail_shows_seller_chat_list(self):
        room = ChatRoom.objects.create(product=self.product, buyer=self.buyer)
        self.client.force_login(self.seller)
        page = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertContains(page, "購入希望者とのチャット")
        self.assertContains(page, reverse("chat_room", args=[room.pk]))
        self.assertContains(page, self.buyer.username)


class UserDirectMessageTests(TestCase):
    def setUp(self):
        self.user_a = get_user_model().objects.create_user(
            email="dm-a@waseda.jp",
            password="password",
            username="dm_user_a",
        )
        self.user_b = get_user_model().objects.create_user(
            email="dm-b@waseda.jp",
            password="password",
            username="dm_user_b",
        )
        self.other = get_user_model().objects.create_user(
            email="dm-other@waseda.jp",
            password="password",
            username="dm_other",
        )

    def test_ordered_pair_prevents_duplicate_rooms(self):
        room1, created1 = get_or_create_dm_room(self.user_a, self.user_b)
        room2, created2 = get_or_create_dm_room(self.user_b, self.user_a)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(room1.pk, room2.pk)
        self.assertEqual(UserDirectMessageRoom.objects.count(), 1)
        low, high = ordered_user_pair(self.user_b, self.user_a)
        self.assertLess(low.pk, high.pk)

    def test_start_user_dm_creates_room_and_redirects(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("start_user_dm", args=[self.user_b.pk]))
        self.assertEqual(response.status_code, 302)
        room = UserDirectMessageRoom.objects.get()
        self.assertEqual(response["Location"], reverse("user_dm_room", args=[room.pk]))

    def test_cannot_dm_self(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("start_user_dm", args=[self.user_a.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserDirectMessageRoom.objects.exists())

    def test_other_user_cannot_access_dm_room(self):
        room, _ = get_or_create_dm_room(self.user_a, self.user_b)
        self.client.force_login(self.other)
        response = self.client.get(reverse("user_dm_room", args=[room.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("home"))

    def test_participants_can_send_dm_messages(self):
        room, _ = get_or_create_dm_room(self.user_a, self.user_b)
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse("send_user_dm_message", args=[room.pk]),
            {"body": "こんにちは！"},
        )
        self.assertEqual(response.status_code, 302)
        message = UserDirectMessage.objects.get(room=room)
        self.assertEqual(message.sender, self.user_a)
        self.assertEqual(message.body, "こんにちは！")

        self.client.force_login(self.user_b)
        page = self.client.get(reverse("user_dm_room", args=[room.pk]))
        self.assertContains(page, "こんにちは！")

    def test_dm_room_uses_partial_poll_instead_of_meta_refresh(self):
        room, _ = get_or_create_dm_room(self.user_a, self.user_b)
        self.client.force_login(self.user_a)
        page = self.client.get(reverse("user_dm_room", args=[room.pk]))
        self.assertNotContains(page, 'http-equiv="refresh"')
        self.assertContains(page, 'id="message-area"')
        self.assertContains(page, 'id="message-input"')
        self.assertContains(page, reverse("user_dm_room_messages", args=[room.pk]))

    def test_dm_room_messages_api_returns_only_new_messages(self):
        room, _ = get_or_create_dm_room(self.user_a, self.user_b)
        first = UserDirectMessage.objects.create(
            room=room,
            sender=self.user_a,
            body="最初",
        )
        second = UserDirectMessage.objects.create(
            room=room,
            sender=self.user_b,
            body="返信",
        )
        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse("user_dm_room_messages", args=[room.pk]),
            {"after": first.pk},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["latest_id"], second.pk)
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["id"], second.pk)
        self.assertEqual(data["messages"][0]["body"], "返信")
        self.assertTrue(data["messages"][0]["is_mine"] is False)

    def test_other_user_cannot_poll_dm_room_messages(self):
        room, _ = get_or_create_dm_room(self.user_a, self.user_b)
        self.client.force_login(self.other)
        response = self.client.get(reverse("user_dm_room_messages", args=[room.pk]))
        self.assertEqual(response.status_code, 403)

    def test_profile_shows_dm_button_for_other_user(self):
        self.client.force_login(self.user_a)
        page = self.client.get(
            reverse("user_profile", args=[self.user_b.pk]),
            {"from": "thread"},
        )
        self.assertContains(page, "DMを送る")
        self.assertContains(page, reverse("start_user_dm", args=[self.user_b.pk]))

    def test_timeline_shows_dm_button_for_other_author(self):
        post = TimelinePost.objects.create(
            author=self.user_b,
            body="DMテスト投稿",
        )
        self.client.force_login(self.user_a)
        page = self.client.get(reverse("home"))
        self.assertContains(page, reverse("start_user_dm", args=[self.user_b.pk]))
        self.assertContains(page, "DMテスト投稿")

    def test_dm_is_separate_from_product_chat_room(self):
        product = Product.objects.create(
            seller=self.user_b,
            name="別チャット商品",
            price=100,
            category="本",
        )
        ChatRoom.objects.create(product=product, buyer=self.user_a)
        room, _ = get_or_create_dm_room(self.user_a, self.user_b)
        self.assertNotEqual(
            ChatRoom.objects.filter(product=product, buyer=self.user_a).count(),
            0,
        )
        self.assertEqual(UserDirectMessageRoom.objects.filter(pk=room.pk).count(), 1)


class PwaTests(TestCase):
    def test_manifest_json_is_served(self):
        response = self.client.get(reverse("pwa_manifest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json; charset=utf-8")
        data = response.json()
        self.assertEqual(data["name"], "わせわせ")
        self.assertEqual(data["theme_color"], "#891E2B")
        self.assertTrue(data["icons"])

    def test_service_worker_is_served(self):
        response = self.client.get(reverse("pwa_service_worker"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response["Content-Type"])
        self.assertIn("skipWaiting", response.content.decode())

    def test_home_includes_manifest_link(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'rel="manifest"')
        self.assertContains(response, "/manifest.json")
        self.assertContains(response, "serviceWorker.register")

    def test_ads_txt_is_served(self):
        response = self.client.get(reverse("ads_txt"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn(b"Google AdSense ads.txt placeholder", response.content)

    def test_privacy_and_terms_pages_are_served(self):
        privacy = self.client.get(reverse("privacy"))
        self.assertEqual(privacy.status_code, 200)
        self.assertContains(privacy, "プライバシーポリシー")
        self.assertContains(privacy, "Google AdSense")
        self.assertContains(privacy, "wasewaseofficial@gmail.com")

        terms = self.client.get(reverse("terms"))
        self.assertEqual(terms.status_code, 200)
        self.assertContains(terms, "利用規約")
        self.assertContains(terms, "第1条（利用資格）")

        home = self.client.get(reverse("home"))
        self.assertContains(home, reverse("privacy"))
        self.assertContains(home, reverse("terms"))
        self.assertContains(home, "運営：『わせわせ』運営事務局")
        self.assertContains(home, "wasewaseofficial@gmail.com")


class TimelineInfiniteScrollTests(TestCase):
    def setUp(self):
        from app.board_services import TIMELINE_INITIAL_SIZE

        self.author = get_user_model().objects.create_user(
            email="timeline-author@waseda.jp",
            password="password",
        )
        self.initial_size = TIMELINE_INITIAL_SIZE
        for i in range(self.initial_size + 5):
            TimelinePost.objects.create(author=self.author, body=f"scroll-post-{i}")

    def test_initial_timeline_shows_25_posts_without_show_all_button(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="timeline-list"')
        self.assertContains(response, 'data-has-more="true"')
        self.assertNotContains(response, "すべて表示")
        self.assertEqual(
            response.content.decode().count('class="tweet-card'),
            self.initial_size,
        )

    def test_timeline_feed_returns_next_batch(self):
        response = self.client.get(
            reverse("timeline_feed"),
            {"offset": self.initial_size},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["next_offset"], self.initial_size + 5)
        self.assertFalse(data["has_more"])
        self.assertEqual(data["html"].count('class="tweet-card"'), 5)


class UserLevelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.author = User.objects.create_user(
            email="level-author@example.com",
            password="password",
            username="level_author",
        )
        self.actor = User.objects.create_user(
            email="level-actor@example.com",
            password="password",
            username="level_actor",
        )
        self.buyer = User.objects.create_user(
            email="level-buyer@example.com",
            password="password",
            username="level_buyer",
        )

    def test_level_helpers(self):
        self.assertEqual(level_from_score(0), 1)
        self.assertEqual(level_from_score(9), 1)
        self.assertEqual(level_from_score(10), 2)
        self.assertEqual(level_from_score(49), 5)
        self.assertEqual(score_to_next_level(0), 10)
        self.assertEqual(score_to_next_level(9), 1)
        self.assertEqual(rank_title_from_level(1), "一般学生")
        self.assertEqual(rank_title_from_level(5), "アクティブ早大生")
        self.assertEqual(rank_title_from_level(15), "わせわせ常連組")
        self.assertEqual(rank_title_from_level(30), "早稲田インフルエンサー")
        self.assertEqual(rank_title_from_level(50), "大隈重信クラス")

    def test_compute_level_score_from_likes_gods_and_trades(self):
        TimelinePost.objects.create(
            author=self.author,
            body="人気投稿",
            like_count=3,
            god_count=2,
        )
        Product.objects.create(
            seller=self.author,
            buyer=self.buyer,
            name="教科書",
            price=1000,
            category="本",
            status=Product.Status.SOLD_OUT,
        )

        stats = compute_level_score(self.author)
        self.assertEqual(stats["likes_received"], 3)
        self.assertEqual(stats["gods_received"], 2)
        self.assertEqual(stats["like_score"], 3)
        self.assertEqual(stats["god_score"], 60)
        self.assertEqual(stats["engagement_score"], 63)
        self.assertEqual(stats["completed_trades"], 1)
        self.assertEqual(stats["trade_score"], 20)
        self.assertEqual(stats["total_score"], 83)
        self.assertEqual(stats["level"], 9)
        self.assertEqual(stats["rank_title"], "アクティブ早大生")
        self.assertEqual(stats["score_to_next_level"], 7)

    def test_recalculate_user_level_updates_profile_fields(self):
        TimelinePost.objects.create(
            author=self.author,
            body="保存テスト",
            like_count=10,
            god_count=0,
        )
        stats = recalculate_user_level(self.author)
        profile = UserProfile.objects.get(user=self.author)
        self.assertEqual(profile.level_score, stats["total_score"])
        self.assertEqual(profile.level, stats["level"])
        self.assertEqual(profile.level, 2)

    def test_like_updates_author_level(self):
        post = TimelinePost.objects.create(
            author=self.author,
            body="いいね対象",
            like_count=0,
        )
        self.client.force_login(self.actor)
        self.client.post(reverse("board_timeline_like", args=[post.pk]))
        profile = UserProfile.objects.get(user=self.author)
        self.assertEqual(profile.level_score, 1)
        self.assertEqual(profile.level, 1)

    def test_profile_page_shows_level_and_rank(self):
        TimelinePost.objects.create(
            author=self.author,
            body="表示テスト",
            like_count=40,
            god_count=10,
        )
        recalculate_user_level(self.author)
        response = self.client.get(reverse("user_profile", args=[self.author.pk]))
        self.assertContains(response, "Lv.35")
        self.assertContains(response, "【早稲田インフルエンサー】")
        self.assertContains(response, "次のレベルまであと")
        self.assertContains(response, "わせわせレベル＆ランクシステム")
        self.assertContains(response, "神！ボタンをもらう：＋30点")

    def test_mypage_shows_level_and_rank(self):
        TimelinePost.objects.create(
            author=self.author,
            body="マイページ表示",
            like_count=0,
            god_count=0,
        )
        self.client.force_login(self.author)
        response = self.client.get(reverse("mypage"))
        self.assertContains(response, "Lv.1")
        self.assertContains(response, "【一般学生】")
        self.assertContains(response, "レベル・ランクシステムの説明")

    def test_recalculate_user_level_survives_missing_profile_columns(self):
        stats = compute_level_score(self.author)
        with patch.object(
            UserProfile.objects,
            "get_or_create",
            side_effect=OperationalError("no such column: app_userprofile.level_score"),
        ):
            result = recalculate_user_level(self.author)
        self.assertEqual(result, stats)


class EnsureSuperuserCommandTests(TestCase):
    def test_promotes_existing_user_to_superuser(self):
        from io import StringIO

        from django.contrib.auth import get_user_model
        from django.core.management import call_command

        from app.management.commands.ensure_superuser import (
            SUPERUSER_EMAIL,
            SUPERUSER_PASSWORD,
        )

        get_user_model().objects.create_user(
            email=SUPERUSER_EMAIL,
            password="old-password",
            username="tomok11keda",
        )
        out = StringIO()
        call_command("ensure_superuser", stdout=out)

        user = get_user_model().objects.get(email=SUPERUSER_EMAIL)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(SUPERUSER_PASSWORD))
        self.assertFalse(user.check_password("old-password"))
        self.assertIn("管理者に設定しました", out.getvalue())

    def test_updates_password_even_when_already_superuser(self):
        from io import StringIO

        from django.contrib.auth import get_user_model
        from django.core.management import call_command

        from app.management.commands.ensure_superuser import (
            SUPERUSER_EMAIL,
            SUPERUSER_PASSWORD,
        )

        get_user_model().objects.create_superuser(
            email=SUPERUSER_EMAIL,
            password="different-password",
            username="admin",
        )
        out = StringIO()
        call_command("ensure_superuser", stdout=out)

        user = get_user_model().objects.get(email=SUPERUSER_EMAIL)
        self.assertTrue(user.check_password(SUPERUSER_PASSWORD))
        self.assertIn("管理者に設定しました", out.getvalue())

    def test_reports_missing_user(self):
        from io import StringIO

        from django.core.management import call_command

        from app.management.commands.ensure_superuser import SUPERUSER_EMAIL

        out = StringIO()
        err = StringIO()
        call_command("ensure_superuser", stdout=out, stderr=err)

        self.assertIn("見つかりません", err.getvalue())


class PushNotificationTests(TestCase):
    def setUp(self):
        self.seller = get_user_model().objects.create_user(
            email="push-seller@example.com",
            password="password",
        )
        self.buyer = get_user_model().objects.create_user(
            email="push-buyer@example.com",
            password="password",
        )
        self.product = Product.objects.create(
            seller=self.seller,
            name="プッシュ通知テスト商品",
            price=500,
            description="",
            category="未分類",
            faculty="商学部",
        )

    def test_register_push_token_api(self):
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("register_push_token"),
            data='{"token":"abc123token","platform":"ios"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        device = DevicePushToken.objects.get(user=self.seller)
        self.assertEqual(device.token, "abc123token")
        self.assertEqual(device.platform, DevicePushToken.Platform.IOS)

    def test_register_push_token_updates_existing_token_owner(self):
        DevicePushToken.objects.create(
            user=self.buyer,
            token="shared-token",
            platform=DevicePushToken.Platform.IOS,
        )
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("register_push_token"),
            data='{"token":"shared-token","platform":"android"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        device = DevicePushToken.objects.get(token="shared-token")
        self.assertEqual(device.user, self.seller)
        self.assertEqual(device.platform, DevicePushToken.Platform.ANDROID)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_comment_notifies_seller_with_push(self, mock_notify_push):
        mock_notify_push.return_value = 1
        DevicePushToken.objects.create(
            user=self.seller,
            token="seller-device-token",
            platform=DevicePushToken.Platform.IOS,
        )
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("product_detail", args=[self.product.pk]),
            data={"body": "購入検討中です"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.seller,
                message__contains="コメントがつきました",
            ).exists()
        )
        mock_notify_push.assert_called_once()
        _, kwargs = mock_notify_push.call_args
        self.assertIn("コメントがつきました", kwargs["body"])

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_purchase_notifies_seller_with_push(self, mock_notify_push):
        mock_notify_push.return_value = 1
        DevicePushToken.objects.create(
            user=self.seller,
            token="seller-device-token",
            platform=DevicePushToken.Platform.IOS,
        )
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("purchase_product", args=[self.product.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.seller,
                message__contains="購入希望がありました",
            ).exists()
        )
        mock_notify_push.assert_called_once()
        _, kwargs = mock_notify_push.call_args
        self.assertIn("購入希望がありました", kwargs["body"])

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=False)
    @patch("app.push_services.get_firebase_app")
    def test_notify_seller_skips_push_when_disabled(self, mock_get_firebase_app):
        DevicePushToken.objects.create(
            user=self.seller,
            token="seller-device-token",
            platform=DevicePushToken.Platform.IOS,
        )

        notify_seller(
            self.product,
            "テスト通知",
            actor_id=self.buyer.id,
        )

        mock_get_firebase_app.assert_not_called()


class UGCSafetyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(
            email="viewer@example.com",
            password="pass12345",
            username="viewer",
        )
        self.author = User.objects.create_user(
            email="author@example.com",
            password="pass12345",
            username="author",
        )
        self.post = TimelinePost.objects.create(
            author=self.author,
            body="テスト投稿",
            course_name="線形代数",
        )
        self.product = Product.objects.create(
            seller=self.author,
            name="テスト出品",
            price=500,
            category="本",
        )

    def test_submit_report_creates_record(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("submit_report"),
            {
                "target_type": ContentReport.TargetType.POST,
                "target_id": self.post.pk,
                "reason": ContentReport.Reason.SPAM,
                "detail": "宣伝です",
            },
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ContentReport.objects.filter(
                reporter=self.viewer,
                target_type=ContentReport.TargetType.POST,
                target_id=self.post.pk,
            ).exists()
        )

    def test_submit_report_rejects_self_report(self):
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("submit_report"),
            {
                "target_type": ContentReport.TargetType.POST,
                "target_id": self.post.pk,
                "reason": ContentReport.Reason.OTHER,
            },
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_toggle_block_hides_timeline_posts(self):
        self.client.force_login(self.viewer)
        self.client.post(reverse("toggle_block", args=[self.author.pk]))

        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "テスト投稿")

        self.client.post(reverse("toggle_block", args=[self.author.pk]))
        response = self.client.get(reverse("home"))
        self.assertContains(response, "テスト投稿")

    def test_soft_removed_post_hidden_from_feed(self):
        self.post.is_removed = True
        self.post.save(update_fields=["is_removed"])

        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "テスト投稿")

    def test_soft_removed_product_redirects_home(self):
        self.product.is_removed = True
        self.product.save(update_fields=["is_removed"])

        response = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/")

