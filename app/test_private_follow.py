"""Private account + follow request backend tests."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .models import (
    Follow,
    FollowRequest,
    Notification,
    Product,
    TimelinePost,
    User,
    UserBlock,
    UserProfile,
)
from .notification_api_services import notification_spa_path
from .services import count_followers


@override_settings(BROWSE_MODE_GATE_ENABLED=False, WASE_REACT_SPA=True)
class PrivateAccountFollowTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email="alice-priv@waseda.jp",
            password="test-pass-12345",
            username="alicepriv",
        )
        self.bob = User.objects.create_user(
            email="bob-priv@waseda.jp",
            password="test-pass-12345",
            username="bobpriv",
        )
        self.carol = User.objects.create_user(
            email="carol-priv@waseda.jp",
            password="test-pass-12345",
            username="carolpriv",
        )
        UserProfile.objects.update_or_create(
            user=self.alice, defaults={"name": "Alice", "is_private": False}
        )
        UserProfile.objects.update_or_create(
            user=self.bob, defaults={"name": "Bob", "is_private": True}
        )
        UserProfile.objects.update_or_create(
            user=self.carol, defaults={"name": "Carol", "is_private": False}
        )
        self.bob_post = TimelinePost.objects.create(
            author=self.bob, body="bob private post"
        )
        self.bob_product = Product.objects.create(
            seller=self.bob,
            name="bob private product",
            price=1000,
            description="",
            category="未分類",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.client = Client()

    def test_public_follow_unfollow(self):
        self.client.force_login(self.alice)
        r = self.client.post(f"/api/v1/profile/{self.carol.pk}/follow/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["is_following"])
        self.assertEqual(data["follow_state"], "following")
        self.assertTrue(
            Follow.objects.filter(follower=self.alice, following=self.carol).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.carol, message__contains="フォローされました"
            ).exists()
        )

        r2 = self.client.post(f"/api/v1/profile/{self.carol.pk}/follow/")
        self.assertFalse(r2.json()["is_following"])
        self.assertFalse(
            Follow.objects.filter(follower=self.alice, following=self.carol).exists()
        )

    def test_private_request_cancel_accept_reject(self):
        self.client.force_login(self.alice)
        r = self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data["is_following"])
        self.assertEqual(data["follow_state"], "requested")
        self.assertFalse(
            Follow.objects.filter(follower=self.alice, following=self.bob).exists()
        )
        self.assertTrue(
            FollowRequest.objects.filter(from_user=self.alice, to_user=self.bob).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.bob, message__contains="フォローリクエスト"
            ).exists()
        )
        note = Notification.objects.filter(
            recipient=self.bob, message__contains="フォローリクエスト"
        ).latest("id")
        self.assertEqual(note.link, "/app/settings/follow-requests")
        self.assertEqual(
            notification_spa_path(note.link), "/settings/follow-requests"
        )

        # cancel
        r2 = self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        self.assertEqual(r2.json()["follow_state"], "none")
        self.assertFalse(
            FollowRequest.objects.filter(from_user=self.alice, to_user=self.bob).exists()
        )

        # request again and accept
        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        req = FollowRequest.objects.get(from_user=self.alice, to_user=self.bob)
        self.client.force_login(self.bob)
        accept = self.client.post(f"/api/v1/follow-requests/{req.pk}/accept/")
        self.assertEqual(accept.status_code, 200)
        self.assertTrue(
            Follow.objects.filter(follower=self.alice, following=self.bob).exists()
        )
        self.assertFalse(FollowRequest.objects.filter(pk=req.pk).exists())
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.bob, message__contains="フォローされました"
            ).exists()
        )

        # reject path
        Follow.objects.filter(follower=self.alice, following=self.bob).delete()
        self.client.force_login(self.carol)
        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        req2 = FollowRequest.objects.get(from_user=self.carol, to_user=self.bob)
        self.client.force_login(self.bob)
        reject = self.client.post(f"/api/v1/follow-requests/{req2.pk}/reject/")
        self.assertEqual(reject.status_code, 200)
        self.assertFalse(
            Follow.objects.filter(follower=self.carol, following=self.bob).exists()
        )
        self.assertFalse(FollowRequest.objects.filter(pk=req2.pk).exists())

    def test_duplicate_and_self_and_block(self):
        self.client.force_login(self.alice)
        self.assertEqual(
            self.client.post(f"/api/v1/profile/{self.alice.pk}/follow/").status_code,
            400,
        )

        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        # second request while pending cancels (toggle), so re-request once
        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")  # cancel
        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")  # request
        self.assertEqual(
            FollowRequest.objects.filter(from_user=self.alice, to_user=self.bob).count(),
            1,
        )

        UserBlock.objects.create(blocker=self.bob, blocked=self.alice)
        FollowRequest.objects.filter(from_user=self.alice, to_user=self.bob).delete()
        blocked = self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        self.assertEqual(blocked.status_code, 403)

    def test_privacy_toggle_auto_accept(self):
        self.client.force_login(self.alice)
        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        self.assertTrue(
            FollowRequest.objects.filter(from_user=self.alice, to_user=self.bob).exists()
        )

        self.client.force_login(self.bob)
        # public → already private; set public
        r = self.client.patch(
            "/api/v1/me/privacy/",
            data=json.dumps({"is_private": False}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["is_private"])
        self.assertGreaterEqual(r.json()["auto_accepted_requests"], 1)
        self.assertTrue(
            Follow.objects.filter(follower=self.alice, following=self.bob).exists()
        )
        self.assertFalse(
            FollowRequest.objects.filter(from_user=self.alice, to_user=self.bob).exists()
        )

        # public → private keeps follow
        r2 = self.client.patch(
            "/api/v1/me/privacy/",
            data=json.dumps({"is_private": True}),
            content_type="application/json",
        )
        self.assertTrue(r2.json()["is_private"])
        self.assertTrue(
            Follow.objects.filter(follower=self.alice, following=self.bob).exists()
        )

    def test_access_control_posts_products_timeline_search(self):
        # stranger cannot see
        posts = self.client.get(f"/api/v1/profile/{self.bob.pk}/posts/")
        self.assertEqual(posts.json()["posts"], [])
        products = self.client.get(f"/api/v1/profile/{self.bob.pk}/products/")
        self.assertEqual(products.json()["products"], [])

        tl = self.client.get("/api/v1/timeline/")
        bodies = [p["body"] for p in tl.json()["posts"]]
        self.assertNotIn("bob private post", bodies)

        search = self.client.get("/api/v1/search/", {"q": "bob private", "tab": "all"})
        self.assertEqual(search.json()["post_count"], 0)

        # like / quote as stranger → not found
        self.client.force_login(self.alice)
        like = self.client.post(f"/api/v1/timeline/{self.bob_post.pk}/like/")
        self.assertEqual(like.status_code, 404)
        quote = self.client.get(f"/api/v1/timeline/{self.bob_post.pk}/quote/")
        self.assertEqual(quote.status_code, 404)

        flea = self.client.get(f"/api/v1/flea/products/{self.bob_product.pk}/")
        self.assertEqual(flea.status_code, 404)

        # approve then visible
        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        req = FollowRequest.objects.get(from_user=self.alice, to_user=self.bob)
        self.client.force_login(self.bob)
        self.client.post(f"/api/v1/follow-requests/{req.pk}/accept/")

        self.client.force_login(self.alice)
        posts2 = self.client.get(f"/api/v1/profile/{self.bob.pk}/posts/")
        self.assertTrue(any(p["body"] == "bob private post" for p in posts2.json()["posts"]))
        products2 = self.client.get(f"/api/v1/profile/{self.bob.pk}/products/")
        self.assertTrue(
            any(p["name"] == "bob private product" for p in products2.json()["products"])
        )
        detail = self.client.get(f"/api/v1/profile/{self.bob.pk}/")
        self.assertTrue(detail.json()["can_view_content"])
        self.assertEqual(detail.json()["follow_state"], "following")

        # owner always can
        self.client.force_login(self.bob)
        own = self.client.get(f"/api/v1/profile/{self.bob.pk}/posts/")
        self.assertTrue(any(p["body"] == "bob private post" for p in own.json()["posts"]))

    def test_request_not_in_counts_or_following_feed(self):
        self.client.force_login(self.alice)
        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        self.assertEqual(count_followers(self.bob), 0)
        detail = self.client.get(f"/api/v1/profile/{self.bob.pk}/")
        self.assertEqual(detail.json()["stats"]["follower_count"], 0)
        self.assertEqual(detail.json()["follow_state"], "requested")

        feed = self.client.get("/api/v1/timeline/?feed=following")
        bodies = [p.get("body") for p in feed.json()["posts"]]
        self.assertNotIn("bob private post", bodies)

    def test_follow_requests_list(self):
        self.client.force_login(self.alice)
        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        self.client.force_login(self.bob)
        listing = self.client.get("/api/v1/follow-requests/")
        self.assertEqual(listing.status_code, 200)
        reqs = listing.json()["requests"]
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["from_user"]["id"], self.alice.pk)
        self.assertEqual(reqs[0]["from_user"]["display_name"], "Alice")

    def test_block_clears_request(self):
        self.client.force_login(self.alice)
        self.client.post(f"/api/v1/profile/{self.bob.pk}/follow/")
        self.assertTrue(
            FollowRequest.objects.filter(from_user=self.alice, to_user=self.bob).exists()
        )
        self.client.force_login(self.bob)
        self.client.post(f"/api/v1/profile/{self.alice.pk}/block/")
        self.assertFalse(
            FollowRequest.objects.filter(from_user=self.alice, to_user=self.bob).exists()
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=False, WASE_REACT_SPA=True)
class QuotePrivacyTests(TestCase):
    """Private post body must not leak via quote create or quoted_post serialize."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner-quote@waseda.jp",
            password="test-pass-12345",
            username="ownerquote",
        )
        self.follower = User.objects.create_user(
            email="follower-quote@waseda.jp",
            password="test-pass-12345",
            username="followerquote",
        )
        self.stranger = User.objects.create_user(
            email="stranger-quote@waseda.jp",
            password="test-pass-12345",
            username="strangerquote",
        )
        UserProfile.objects.update_or_create(
            user=self.owner, defaults={"name": "Owner", "is_private": False}
        )
        UserProfile.objects.update_or_create(
            user=self.follower, defaults={"name": "Follower", "is_private": False}
        )
        UserProfile.objects.update_or_create(
            user=self.stranger, defaults={"name": "Stranger", "is_private": False}
        )
        self.public_post = TimelinePost.objects.create(
            author=self.owner, body="owner public secret body"
        )
        self.client = Client()

    def _create_quote(self, actor, quoted_pk, body="quote comment"):
        self.client.force_login(actor)
        return self.client.post(
            "/api/v1/timeline/",
            {"body": body, "quoted_post_id": str(quoted_pk)},
        )

    def _quoted_body_from_timeline(self, viewer, quote_post_id):
        self.client.force_login(viewer)
        feed = self.client.get("/api/v1/timeline/")
        self.assertEqual(feed.status_code, 200)
        for post in feed.json()["posts"]:
            if post["id"] == quote_post_id:
                qp = post.get("quoted_post") or {}
                return qp.get("body") or "", qp
        self.fail(f"quote post {quote_post_id} not in timeline")

    def test_a_public_post_quote_succeeds_and_returns_body(self):
        resp = self._create_quote(self.follower, self.public_post.pk)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["post"]["quoted_post"]["body"], "owner public secret body")
        body, _ = self._quoted_body_from_timeline(
            self.stranger, data["post"]["id"]
        )
        self.assertEqual(body, "owner public secret body")

    def test_b_private_accepted_follower_can_quote_and_see_body(self):
        UserProfile.objects.filter(user=self.owner).update(is_private=True)
        private_post = TimelinePost.objects.create(
            author=self.owner, body="owner private secret body"
        )
        Follow.objects.create(follower=self.follower, following=self.owner)

        resp = self._create_quote(self.follower, private_post.pk)
        self.assertEqual(resp.status_code, 201)
        qp = resp.json()["post"]["quoted_post"]
        self.assertFalse(qp["is_removed"])
        self.assertEqual(qp["body"], "owner private secret body")

        body, _ = self._quoted_body_from_timeline(self.follower, resp.json()["post"]["id"])
        self.assertEqual(body, "owner private secret body")

    def test_c_private_non_follower_cannot_quote_or_see_body(self):
        UserProfile.objects.filter(user=self.owner).update(is_private=True)
        private_post = TimelinePost.objects.create(
            author=self.owner, body="owner private secret body"
        )
        # Existing quote created by an accepted follower
        Follow.objects.create(follower=self.follower, following=self.owner)
        ok = self._create_quote(self.follower, private_post.pk, body="follower quote")
        self.assertEqual(ok.status_code, 201)
        quote_id = ok.json()["post"]["id"]
        Follow.objects.filter(follower=self.follower, following=self.owner).delete()

        denied = self._create_quote(self.stranger, private_post.pk)
        self.assertEqual(denied.status_code, 400)
        self.assertIn("quoted_post_id", denied.json().get("errors", {}))
        self.assertFalse(
            TimelinePost.objects.filter(
                author=self.stranger, quoted_post_id=private_post.pk
            ).exists()
        )

        body, qp = self._quoted_body_from_timeline(self.stranger, quote_id)
        self.assertEqual(body, "")
        self.assertTrue(qp.get("is_removed"))
        self.assertNotIn("owner private secret body", json.dumps(qp))

    def test_d_private_pending_request_cannot_quote_or_see_body(self):
        UserProfile.objects.filter(user=self.owner).update(is_private=True)
        private_post = TimelinePost.objects.create(
            author=self.owner, body="owner private secret body"
        )
        Follow.objects.create(follower=self.follower, following=self.owner)
        ok = self._create_quote(self.follower, private_post.pk, body="accepted quote")
        quote_id = ok.json()["post"]["id"]

        FollowRequest.objects.create(from_user=self.stranger, to_user=self.owner)
        denied = self._create_quote(self.stranger, private_post.pk)
        self.assertEqual(denied.status_code, 400)

        body, qp = self._quoted_body_from_timeline(self.stranger, quote_id)
        self.assertEqual(body, "")
        self.assertTrue(qp.get("is_removed"))

    def test_e_blocked_cannot_quote_or_see_body(self):
        UserProfile.objects.filter(user=self.owner).update(is_private=True)
        private_post = TimelinePost.objects.create(
            author=self.owner, body="owner private secret body"
        )
        Follow.objects.create(follower=self.follower, following=self.owner)
        ok = self._create_quote(self.follower, private_post.pk, body="before block")
        quote_id = ok.json()["post"]["id"]

        UserBlock.objects.create(blocker=self.owner, blocked=self.stranger)
        denied = self._create_quote(self.stranger, private_post.pk)
        self.assertEqual(denied.status_code, 400)

        body, qp = self._quoted_body_from_timeline(self.stranger, quote_id)
        self.assertEqual(body, "")
        self.assertTrue(qp.get("is_removed"))

    def test_f_owner_can_quote_own_private_post(self):
        UserProfile.objects.filter(user=self.owner).update(is_private=True)
        private_post = TimelinePost.objects.create(
            author=self.owner, body="owner private secret body"
        )
        resp = self._create_quote(self.owner, private_post.pk, body="self quote")
        self.assertEqual(resp.status_code, 201)
        qp = resp.json()["post"]["quoted_post"]
        self.assertFalse(qp["is_removed"])
        self.assertEqual(qp["body"], "owner private secret body")

    def test_classic_compose_rejects_private_quote_for_stranger(self):
        UserProfile.objects.filter(user=self.owner).update(is_private=True)
        private_post = TimelinePost.objects.create(
            author=self.owner, body="owner private classic body"
        )
        self.client.force_login(self.stranger)
        before = TimelinePost.objects.count()
        resp = self.client.post(
            "/board/compose/",
            {
                "body": "classic quote attempt",
                "quoted_post_id": str(private_post.pk),
            },
        )
        # Invalid form redirects back without creating the quote
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(TimelinePost.objects.count(), before)
        self.assertFalse(
            TimelinePost.objects.filter(
                author=self.stranger, quoted_post_id=private_post.pk
            ).exists()
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=False, WASE_REACT_SPA=True)
class PrivateMutationAclTests(TestCase):
    """ID直叩きの purchase/like/comment 等が private ACL を通ること。"""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner-mut@waseda.jp",
            password="test-pass-12345",
            username="ownermut",
        )
        self.follower = User.objects.create_user(
            email="follower-mut@waseda.jp",
            password="test-pass-12345",
            username="followermut",
        )
        self.stranger = User.objects.create_user(
            email="stranger-mut@waseda.jp",
            password="test-pass-12345",
            username="strangermut",
        )
        UserProfile.objects.update_or_create(
            user=self.owner, defaults={"name": "Owner", "is_private": True}
        )
        UserProfile.objects.update_or_create(
            user=self.follower, defaults={"name": "Follower", "is_private": False}
        )
        UserProfile.objects.update_or_create(
            user=self.stranger, defaults={"name": "Stranger", "is_private": False}
        )
        self.private_post = TimelinePost.objects.create(
            author=self.owner, body="private mutation post"
        )
        self.private_product = Product.objects.create(
            seller=self.owner,
            name="private mutation product",
            price=2000,
            description="",
            category="未分類",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.public_owner = User.objects.create_user(
            email="public-mut@waseda.jp",
            password="test-pass-12345",
            username="publicmut",
        )
        UserProfile.objects.update_or_create(
            user=self.public_owner, defaults={"name": "Public", "is_private": False}
        )
        self.public_post = TimelinePost.objects.create(
            author=self.public_owner, body="public mutation post"
        )
        self.public_product = Product.objects.create(
            seller=self.public_owner,
            name="public mutation product",
            price=1500,
            description="",
            category="未分類",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.client = Client()

    def test_stranger_denied_api_and_classic_mutations(self):
        self.client.force_login(self.stranger)
        self.assertEqual(
            self.client.post(
                f"/api/v1/flea/products/{self.private_product.pk}/purchase/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/flea/products/{self.private_product.pk}/chat/start/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/flea/products/{self.private_product.pk}/like/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/timeline/{self.private_post.pk}/like/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/timeline/{self.private_post.pk}/bookmark/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/timeline/{self.private_post.pk}/comments/",
                {"body": "nope"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/product/{self.private_product.pk}/purchase/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/product/{self.private_product.pk}/chat/start/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(f"/product/{self.private_product.pk}/like/").status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/board/post/{self.private_post.pk}/like/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/board/post/{self.private_post.pk}/bookmark/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/board/post/{self.private_post.pk}/comment/",
                {"body": "nope"},
            ).status_code,
            404,
        )

    def test_accepted_follower_can_mutate(self):
        Follow.objects.create(follower=self.follower, following=self.owner)
        self.client.force_login(self.follower)

        like = self.client.post(
            f"/api/v1/flea/products/{self.private_product.pk}/like/"
        )
        self.assertEqual(like.status_code, 200)
        self.assertTrue(like.json()["liked"])

        chat = self.client.post(
            f"/api/v1/flea/products/{self.private_product.pk}/chat/start/"
        )
        self.assertEqual(chat.status_code, 200)
        self.assertTrue(chat.json()["ok"])

        tl_like = self.client.post(f"/api/v1/timeline/{self.private_post.pk}/like/")
        self.assertEqual(tl_like.status_code, 200)
        self.assertTrue(tl_like.json()["liked"])

        comment = self.client.post(
            f"/api/v1/timeline/{self.private_post.pk}/comments/",
            {"body": "hello private"},
        )
        self.assertEqual(comment.status_code, 201)

        classic_like = self.client.post(
            f"/board/post/{self.private_post.pk}/like/"
        )
        self.assertEqual(classic_like.status_code, 302)

        classic_comment = self.client.post(
            f"/board/post/{self.private_post.pk}/comment/",
            {"body": "classic ok"},
        )
        self.assertEqual(classic_comment.status_code, 302)

        classic_flea_like = self.client.post(
            f"/product/{self.private_product.pk}/like/"
        )
        self.assertEqual(classic_flea_like.status_code, 302)

    def test_public_mutations_still_work(self):
        self.client.force_login(self.stranger)
        self.assertEqual(
            self.client.post(
                f"/api/v1/flea/products/{self.public_product.pk}/like/"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/timeline/{self.public_post.pk}/like/"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/board/post/{self.public_post.pk}/like/"
            ).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(f"/product/{self.public_product.pk}/like/").status_code,
            302,
        )

    def test_block_denies_mutations(self):
        from .ugc_services import block_user

        Follow.objects.create(follower=self.follower, following=self.owner)
        block_user(self.owner, self.follower)
        self.client.force_login(self.follower)
        self.assertEqual(
            self.client.post(
                f"/api/v1/flea/products/{self.private_product.pk}/like/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/timeline/{self.private_post.pk}/like/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/board/post/{self.private_post.pk}/like/"
            ).status_code,
            404,
        )

    def test_owner_can_mutate_own_private_content(self):
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(
                f"/api/v1/timeline/{self.private_post.pk}/like/"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/board/post/{self.private_post.pk}/comment/",
                {"body": "own comment"},
            ).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/flea/products/{self.private_product.pk}/like/"
            ).status_code,
            200,
        )
        purchase = self.client.post(
            f"/api/v1/flea/products/{self.private_product.pk}/purchase/"
        )
        self.assertEqual(purchase.status_code, 400)
        self.assertEqual(purchase.json().get("error"), "own_product")
