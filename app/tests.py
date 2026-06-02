from datetime import timedelta
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Comment,
    Follow,
    Notification,
    Product,
    SignupOTP,
    TimelinePost,
    TradeMessage,
    UserProfile,
)
from .services import build_product_share_timeline_body
from wasewase.email_env import (
    is_plausible_email,
    load_sanitized_email_env,
    sanitize_email_address,
)

from .otp_services import SIGNUP_PENDING_SESSION_KEY, create_and_send_signup_otp


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
    def test_signup_rejects_duplicate_nickname(self):
        get_user_model().objects.create_user(
            email="taken@example.com",
            password="password",
            username="taken_name",
        )
        response = self.client.post(
            reverse("signup"),
            {
                "email": "other@example.com",
                "nickname": "taken_name",
                "password1": "newpass123",
                "password2": "newpass123",
                "faculty": "商学部",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "すでに使われています")

    def test_signup_rejects_duplicate_email(self):
        get_user_model().objects.create_user(
            email="dup@example.com",
            password="password",
        )
        response = self.client.post(
            reverse("signup"),
            {
                "email": "dup@example.com",
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

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    def test_signup_sends_otp_and_redirects_to_verify(self):
        response = self.client.post(
            reverse("signup"),
            {
                "email": "new@example.com",
                "nickname": "wase_taro",
                "password1": "newpass123",
                "password2": "newpass123",
                "faculty": "法学部",
            },
        )
        self.assertRedirects(response, reverse("verify_otp"))
        user = get_user_model().objects.get(email="new@example.com")
        self.assertEqual(user.username, "wase_taro")
        self.assertFalse(user.is_active)
        profile = UserProfile.objects.get(user=user)
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
            email="pending@example.com",
            password="oldpass123",
            is_active=False,
        )
        response = self.client.post(
            reverse("signup"),
            {
                "email": "pending@example.com",
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
                "email": "bad@example.com",
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

        response = self.client.get(reverse("home"), {"tab": "board", "q": "佐藤"})

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
            {"tab": "board", "faculty": "社会科学部"},
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

        page = self.client.get(reverse("home"), {"tab": "board"})
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

        page = self.client.get(reverse("home"), {"tab": "board"})
        self.assertContains(page, "テキストだけの投稿です")


class BoardTimelineNotificationTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(
            email="author@example.com",
            password="password",
        )
        self.actor = get_user_model().objects.create_user(
            email="actor@example.com",
            password="password",
        )
        self.post = TimelinePost.objects.create(
            author=self.author,
            body="試験範囲の共有です。",
            course_name="民法",
            professor_name="田中先生",
        )

    def test_tip_notifies_timeline_post_author(self):
        self.client.force_login(self.actor)

        response = self.client.post(reverse("board_timeline_tip", args=[self.post.pk]))

        self.assertEqual(response.status_code, 302)
        notification = Notification.objects.get(recipient=self.author)
        self.assertEqual(
            notification.message,
            "actorさんがあなたの投稿に1円投げ銭しました",
        )
        self.assertEqual(
            notification.link,
            f"{reverse('home')}?tab=board&tag={quote('民法')}#post-{self.post.pk}",
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
            f"{reverse('home')}?tab=board&tag={quote('民法')}#post-{self.post.pk}",
        )

    def test_self_tip_and_god_do_not_create_notifications(self):
        self.client.force_login(self.author)

        self.client.post(reverse("board_timeline_tip", args=[self.post.pk]))
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
            f"{reverse('home')}?tab=board&tag={quote('民法')}#post-{self.post.pk}",
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

        response = self.client.get(reverse("home"), {"tab": "board"})

        self.assertContains(response, "💬 1")
        self.assertContains(response, "助かりました。")


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
        response = self.client.get(reverse("home"))

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

        response = self.client.get(reverse("home"), {"faculty": "基幹理工学部"})

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

    def test_mypage_edit_updates_profile(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("mypage_edit"),
            {
                "name": "じろう",
                "bio": "テスト概要",
                "department": "商学部",
                "grade": "3年",
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.viewer)
        self.assertEqual(profile.name, "じろう")
        self.assertEqual(profile.bio, "テスト概要")
        self.assertEqual(profile.department, "商学部")
        self.assertEqual(profile.grade, "3年")

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
        response = self.client.get(reverse("home"), {"tab": "board", "feed": "following"})
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
        self.assertEqual(response["Location"], f"{reverse('home')}?tab=board&tag={quote('憲法')}")
        self.assertFalse(TimelinePost.objects.filter(pk=self.post.pk).exists())

    def test_other_user_cannot_delete_timeline_post(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("delete_timeline_post", args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TimelinePost.objects.filter(pk=self.post.pk).exists())

    def test_timeline_shows_delete_only_for_author(self):
        self.client.force_login(self.owner)
        owner_page = self.client.get(reverse("home"), {"tab": "board"})
        self.assertContains(owner_page, "btn-tweet-delete")
        self.assertContains(owner_page, reverse("delete_timeline_post", args=[self.post.pk]))

        self.client.force_login(self.other)
        other_page = self.client.get(reverse("home"), {"tab": "board"})
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
            f"{reverse('home')}?tab=board&tag={quote('刑法')}#post-{self.timeline_post.pk}",
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
        page = self.client.get(reverse("home"), {"tab": "board"})
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
