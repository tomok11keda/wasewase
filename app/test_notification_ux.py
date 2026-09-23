"""In-app notification UX: display-name copy and post-anchor links."""

from __future__ import annotations

import json
from urllib.parse import quote

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .board_services import timeline_post_link
from .community_services import notify_community_reply, seed_communities
from .dm_api_services import send_dm_message
from .dm_services import get_or_create_dm_room
from .follow_services import toggle_follow_relationship
from .models import (
    Community,
    CommunityThread,
    CommunityThreadReply,
    Follow,
    Notification,
    TimelinePost,
    User,
    UserProfile,
)
from .notification_api_services import notification_spa_path
from .notification_services import notification_actor_label


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class NotificationActorLabelTests(TestCase):
    def test_prefers_display_name(self):
        user = User.objects.create_user(
            email="label-name@waseda.jp",
            password="test-pass-12345",
            username="handle_only",
        )
        UserProfile.objects.create(user=user, name="表示名太郎")
        self.assertEqual(notification_actor_label(user), "表示名太郎")

    def test_falls_back_to_username_when_display_name_empty(self):
        user = User.objects.create_user(
            email="label-user@waseda.jp",
            password="test-pass-12345",
            username="bare_handle",
        )
        UserProfile.objects.create(user=user, name="")
        self.assertEqual(notification_actor_label(user), "bare_handle")
        self.assertNotEqual(notification_actor_label(user), "")


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class LikeNotificationUxTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            email="like-author@waseda.jp",
            password="test-pass-12345",
            username="like_author",
        )
        self.actor = User.objects.create_user(
            email="like-actor@waseda.jp",
            password="test-pass-12345",
            username="like_actor",
        )
        UserProfile.objects.create(user=self.author, name="投稿者")
        UserProfile.objects.create(user=self.actor, name="いいね太郎")
        self.post = TimelinePost.objects.create(
            author=self.author,
            body="いいね対象の投稿",
            course_name="民法",
        )
        self.client = Client()

    def test_like_notification_uses_display_name_and_post_anchor(self):
        self.client.force_login(self.actor)
        res = self.client.post(f"/api/v1/timeline/{self.post.pk}/like/")
        self.assertEqual(res.status_code, 200)
        note = Notification.objects.get(recipient=self.author)
        self.assertEqual(
            note.message,
            "いいね太郎さんがあなたの投稿にいいねしました",
        )
        self.assertNotIn("like_actor", note.message)
        self.assertEqual(
            note.link,
            f"{reverse('home')}?tag={quote('民法')}#post-{self.post.pk}",
        )
        self.assertEqual(note.link, timeline_post_link(self.post))
        self.assertEqual(
            notification_spa_path(note.link),
            f"/?tag={quote('民法')}#post-{self.post.pk}",
        )
        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["post"]["id"], self.post.pk)

    def test_like_notification_falls_back_to_username(self):
        UserProfile.objects.filter(user=self.actor).update(name="")
        self.client.force_login(self.actor)
        res = self.client.post(f"/api/v1/timeline/{self.post.pk}/like/")
        self.assertEqual(res.status_code, 200)
        note = Notification.objects.get(recipient=self.author)
        self.assertEqual(
            note.message,
            "like_actorさんがあなたの投稿にいいねしました",
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class NotificationSpaPathAnchorTests(TestCase):
    def test_home_post_anchor_preserved(self):
        self.assertEqual(notification_spa_path("/#post-12"), "/#post-12")
        self.assertEqual(
            notification_spa_path("/?tag=民法#post-12"),
            "/?tag=民法#post-12",
        )
        self.assertEqual(notification_spa_path("/app/#post-12"), "/#post-12")

    def test_follow_and_dm_links_unchanged(self):
        self.assertEqual(notification_spa_path("/user/5/"), "/users/5/posts")
        self.assertEqual(notification_spa_path("/dm/9/"), "/dm/9")
        self.assertEqual(notification_spa_path("/chat/7/"), "/flea/chats/7")

    def test_community_reply_anchor_preserved(self):
        self.assertEqual(
            notification_spa_path(
                "/app/communities/foo/threads/9#reply-4"
            ),
            "/communities/foo/threads/9#reply-4",
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=False, WASE_REACT_SPA=True)
class OtherNotificationTypeUxTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email="ux-alice@waseda.jp",
            password="test-pass-12345",
            username="ux_alice",
        )
        self.bob = User.objects.create_user(
            email="ux-bob@waseda.jp",
            password="test-pass-12345",
            username="ux_bob",
        )
        UserProfile.objects.create(user=self.alice, name="アリス")
        UserProfile.objects.create(user=self.bob, name="ボブ")
        Follow.objects.create(follower=self.alice, following=self.bob)
        Follow.objects.create(follower=self.bob, following=self.alice)
        self.client = Client()

    def test_follow_notification_uses_display_name(self):
        Follow.objects.filter(follower=self.alice, following=self.bob).delete()
        toggle_follow_relationship(self.alice, self.bob)
        note = Notification.objects.get(recipient=self.bob)
        self.assertEqual(note.message, "「アリスさんにフォローされました！」")
        self.assertEqual(
            notification_spa_path(note.link), f"/users/{self.alice.pk}/posts"
        )

    def test_dm_notification_uses_display_name(self):
        room, _ = get_or_create_dm_room(self.alice, self.bob)
        send_dm_message(room, self.alice, "こんにちは")
        note = Notification.objects.get(recipient=self.bob)
        self.assertEqual(note.message, "アリス さんから DM: こんにちは")
        self.assertEqual(notification_spa_path(note.link), f"/dm/{room.pk}")

    def test_community_reply_notification_is_anonymous(self):
        seed_communities()
        community = Community.objects.filter(is_active=True).first()
        thread = CommunityThread.objects.create(
            community=community,
            author=self.bob,
            title="質問",
            body="本文",
        )
        reply = CommunityThreadReply.objects.create(
            thread=thread,
            author=self.alice,
            body="返信です",
        )
        notify_community_reply(reply=reply, thread=thread)
        note = Notification.objects.get(recipient=self.bob)
        self.assertEqual(note.message, "コミュニティの投稿に返信がありました")
        self.assertNotIn("アリス", note.message)
        self.assertNotIn("ux_alice", note.message)
        self.assertEqual(
            notification_spa_path(note.link),
            f"/communities/{community.slug}/threads/{thread.pk}#reply-{reply.pk}",
        )

    def test_timeline_comment_notification_uses_display_name(self):
        post = TimelinePost.objects.create(
            author=self.bob,
            body="コメント対象",
        )
        self.client.force_login(self.alice)
        res = self.client.post(
            f"/api/v1/timeline/{post.pk}/comments/",
            data=json.dumps({"body": "nice"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        note = Notification.objects.get(recipient=self.bob)
        self.assertEqual(
            note.message,
            "「アリスさんがあなたの投稿にコメントしました」",
        )
        self.assertIn(f"#post-{post.pk}", note.link)
        self.assertIn(f"#post-{post.pk}", notification_spa_path(note.link))
