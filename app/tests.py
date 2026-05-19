from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Comment, Notification, Product, TimelinePost, TradeMessage, UserProfile


class EmailAuthTests(TestCase):
    def test_signup_rejects_duplicate_email(self):
        get_user_model().objects.create_user(
            email="dup@example.com",
            password="password",
        )
        response = self.client.post(
            reverse("signup"),
            {
                "email": "dup@example.com",
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

    def test_signup_creates_profile_and_logs_in(self):
        response = self.client.post(
            reverse("signup"),
            {
                "email": "new@example.com",
                "password1": "newpass123",
                "password2": "newpass123",
                "faculty": "法学部",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(email="new@example.com")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.faculty, "法学部")


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
            f"{reverse('home')}?tab=board&tag={quote('民法')}",
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
            f"{reverse('home')}?tab=board&tag={quote('民法')}",
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
            "actorさんがあなたの投稿にコメントしました",
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
