"""Timeline comment conversation-participant notifications (OPTION A)."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Comment, Notification, TimelinePost, UserProfile
from .notification_api_services import notification_spa_path


def _user(email: str, username: str, *, name: str = "") -> object:
    user = get_user_model().objects.create_user(
        email=email,
        password="password",
        username=username,
    )
    UserProfile.objects.create(user=user, name=name or username)
    return user


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TimelineCommentParticipantNotificationTests(TestCase):
    def setUp(self):
        self.author_a = _user("a@waseda.jp", "user_a", name="Alice")
        self.user_b = _user("b@waseda.jp", "user_b", name="Bob")
        self.user_c = _user("c@waseda.jp", "user_c", name="Carol")
        self.user_d = _user("d@waseda.jp", "user_d", name="Dave")
        self.post = TimelinePost.objects.create(
            author=self.author_a,
            body="conversation root",
            course_name="民法",
        )

    def _api_comment(self, user, body: str, post=None, *, parent_id=None):
        post = post or self.post
        self.client.force_login(user)
        payload = {"body": body}
        if parent_id is not None:
            payload["parent_comment_id"] = parent_id
        return self.client.post(
            f"/api/v1/timeline/{post.pk}/comments/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _classic_comment(self, user, body: str, post=None):
        post = post or self.post
        self.client.force_login(user)
        return self.client.post(
            reverse("board_timeline_comment", args=[post.pk]),
            {"body": body},
        )

    def _recipient_ids(self):
        return set(
            Notification.objects.values_list("recipient_id", flat=True)
        )

    def _messages_for(self, user):
        return list(
            Notification.objects.filter(recipient=user).values_list(
                "message", flat=True
            )
        )

    def test_case1_first_comment_notifies_author_only(self):
        res = self._api_comment(self.user_b, "first")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self._recipient_ids(), {self.author_a.pk})
        self.assertEqual(
            self._messages_for(self.author_a),
            ["「Bobさんがあなたの投稿にコメントしました」"],
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.user_b).exists()
        )

    def test_case2_third_comment_notifies_author_and_prior_commenter(self):
        self._api_comment(self.user_b, "from b")
        Notification.objects.all().delete()
        res = self._api_comment(self.user_c, "from c")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            self._recipient_ids(), {self.author_a.pk, self.user_b.pk}
        )
        self.assertEqual(
            self._messages_for(self.author_a),
            ["「Carolさんがあなたの投稿にコメントしました」"],
        )
        self.assertEqual(
            self._messages_for(self.user_b),
            ["「Carolさんがコメントした投稿に新しいコメントがあります」"],
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.user_c).exists()
        )

    def test_case3_author_comment_notifies_prior_participants_only(self):
        self._api_comment(self.user_b, "from b")
        Notification.objects.all().delete()
        res = self._api_comment(self.author_a, "author follow-up")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self._recipient_ids(), {self.user_b.pk})
        self.assertEqual(
            self._messages_for(self.user_b),
            ["「Aliceさんがコメントした投稿に新しいコメントがあります」"],
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.author_a).exists()
        )

    def test_case4_repeat_commenter_notifies_author_only(self):
        self._api_comment(self.user_b, "b1")
        Notification.objects.all().delete()
        res = self._api_comment(self.user_b, "b2")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self._recipient_ids(), {self.author_a.pk})
        self.assertFalse(
            Notification.objects.filter(recipient=self.user_b).exists()
        )

    def test_case5_fourth_comment_notifies_author_and_all_prior(self):
        self._api_comment(self.user_b, "b")
        self._api_comment(self.user_c, "c")
        Notification.objects.all().delete()
        res = self._api_comment(self.user_d, "d")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            self._recipient_ids(),
            {self.author_a.pk, self.user_b.pk, self.user_c.pk},
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.user_d).exists()
        )

    def test_case6_multiple_comments_from_same_user_dedupe_to_one(self):
        self._api_comment(self.user_b, "b1")
        self._api_comment(self.user_b, "b2")
        self._api_comment(self.user_b, "b3")
        Notification.objects.all().delete()
        self._api_comment(self.user_c, "c")
        self.assertEqual(
            Notification.objects.filter(recipient=self.user_b).count(), 1
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.author_a).count(), 1
        )

    def test_deleted_only_comment_removes_participant(self):
        created = self._api_comment(self.user_b, "only").json()["comment"]["id"]
        Notification.objects.all().delete()
        deleted = self.client.delete(f"/api/v1/timeline/comments/{created}/")
        self.assertEqual(deleted.status_code, 200)
        self._api_comment(self.user_c, "after delete")
        self.assertFalse(
            Notification.objects.filter(recipient=self.user_b).exists()
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.author_a).exists()
        )

    def test_remaining_visible_comment_keeps_participant(self):
        first = self._api_comment(self.user_b, "keep").json()["comment"]["id"]
        second = self._api_comment(self.user_b, "drop").json()["comment"]["id"]
        self.assertNotEqual(first, second)
        Notification.objects.all().delete()
        self.client.force_login(self.user_b)
        self.client.delete(f"/api/v1/timeline/comments/{second}/")
        self._api_comment(self.user_c, "after partial delete")
        self.assertEqual(
            Notification.objects.filter(recipient=self.user_b).count(), 1
        )

    def test_moderated_removed_comment_excludes_participant(self):
        comment = Comment.objects.create(
            timeline_post=self.post,
            author=self.user_b,
            body="will be removed",
        )
        Comment.objects.filter(pk=comment.pk).update(is_removed=True)
        Notification.objects.all().delete()
        self._api_comment(self.user_c, "after moderation")
        self.assertFalse(
            Notification.objects.filter(recipient=self.user_b).exists()
        )

    def test_mention_of_participant_dedupes_to_mention_only(self):
        self._api_comment(self.user_b, "prior")
        Notification.objects.all().delete()
        self._api_comment(self.user_c, f"@{self.user_b.username} ありがとう")
        notes = list(Notification.objects.filter(recipient=self.user_b))
        self.assertEqual(len(notes), 1)
        self.assertIn("メンション", notes[0].message)
        self.assertNotIn("新しいコメント", notes[0].message)

    def test_mention_of_author_dedupes_to_author_comment_only(self):
        Notification.objects.all().delete()
        self._api_comment(
            self.user_b, f"@{self.author_a.username} 見てください"
        )
        notes = list(Notification.objects.filter(recipient=self.author_a))
        self.assertEqual(len(notes), 1)
        self.assertIn("あなたの投稿にコメントしました", notes[0].message)
        self.assertNotIn("メンション", notes[0].message)

    def test_self_mention_creates_no_self_notification(self):
        self._api_comment(self.user_b, "prior")
        Notification.objects.all().delete()
        self._api_comment(self.user_c, f"@{self.user_c.username} note")
        self.assertFalse(
            Notification.objects.filter(recipient=self.user_c).exists()
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.author_a).exists()
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.user_b).exists()
        )

    def test_author_and_participant_links_are_canonical_detail(self):
        self._api_comment(self.user_b, "prior")
        Notification.objects.all().delete()
        self._api_comment(self.user_c, "latest")
        author_note = Notification.objects.get(recipient=self.author_a)
        participant_note = Notification.objects.get(recipient=self.user_b)
        expected = f"/app/posts/{self.post.pk}"
        self.assertEqual(author_note.link, expected)
        self.assertEqual(participant_note.link, expected)
        self.assertEqual(
            notification_spa_path(author_note.link), f"/posts/{self.post.pk}"
        )
        self.assertEqual(
            notification_spa_path(participant_note.link),
            f"/posts/{self.post.pk}",
        )

    def test_classic_path_matches_spa_recipients(self):
        self._classic_comment(self.user_b, "classic prior")
        Notification.objects.all().delete()
        res = self._classic_comment(self.user_c, "classic next")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(
            self._recipient_ids(), {self.author_a.pk, self.user_b.pk}
        )
        self.assertIn(
            "あなたの投稿にコメントしました",
            self._messages_for(self.author_a)[0],
        )
        self.assertIn(
            "新しいコメントがあります",
            self._messages_for(self.user_b)[0],
        )

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_participant_notification_uses_centralized_push(self, mock_push):
        mock_push.return_value = 0
        self._api_comment(self.user_b, "prior")
        mock_push.reset_mock()
        self._api_comment(self.user_c, "next")
        # author + participant
        self.assertEqual(mock_push.call_count, 2)
        bodies = {call.kwargs["body"] for call in mock_push.call_args_list}
        self.assertIn("「Carolさんがあなたの投稿にコメントしました」", bodies)
        self.assertIn(
            "「Carolさんがコメントした投稿に新しいコメントがあります」",
            bodies,
        )
        links = {call.kwargs["link"] for call in mock_push.call_args_list}
        self.assertEqual(links, {f"/app/posts/{self.post.pk}"})

    def test_null_author_comment_does_not_become_participant(self):
        Comment.objects.create(
            timeline_post=self.post,
            author=None,
            body="orphan",
        )
        Notification.objects.all().delete()
        self._api_comment(self.user_c, "next")
        self.assertEqual(self._recipient_ids(), {self.author_a.pk})

    def test_reply_notifies_parent_author_and_keeps_post_author(self):
        parent = self._api_comment(self.user_b, "from b").json()["comment"]
        Notification.objects.all().delete()
        res = self._api_comment(self.user_c, "reply to b", parent_id=parent["id"])
        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            self._recipient_ids(), {self.author_a.pk, self.user_b.pk}
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.user_b).count(), 1
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.author_a).count(), 1
        )
        self.assertEqual(
            self._messages_for(self.user_b),
            ["「Carolさんがあなたのコメントに返信しました」"],
        )
        self.assertEqual(
            self._messages_for(self.author_a),
            ["「Carolさんがあなたの投稿にコメントしました」"],
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.user_c).exists()
        )
        b_note = Notification.objects.get(recipient=self.user_b)
        self.assertEqual(b_note.link, f"/app/posts/{self.post.pk}")
        self.assertEqual(
            notification_spa_path(b_note.link), f"/posts/{self.post.pk}"
        )

    def test_reply_to_post_author_comment_does_not_duplicate(self):
        parent = self._api_comment(self.author_a, "author comment").json()[
            "comment"
        ]
        Notification.objects.all().delete()
        res = self._api_comment(
            self.user_c, "reply to author", parent_id=parent["id"]
        )
        self.assertEqual(res.status_code, 201)
        notes = list(Notification.objects.filter(recipient=self.author_a))
        self.assertEqual(len(notes), 1)
        self.assertEqual(
            notes[0].message,
            "「Carolさんがあなたのコメントに返信しました」",
        )
        self.assertNotIn("あなたの投稿にコメントしました", notes[0].message)

    def test_self_reply_creates_no_self_notification(self):
        parent = self._api_comment(self.user_b, "mine").json()["comment"]
        Notification.objects.all().delete()
        res = self._api_comment(
            self.user_b, "reply to myself", parent_id=parent["id"]
        )
        self.assertEqual(res.status_code, 201)
        self.assertFalse(
            Notification.objects.filter(recipient=self.user_b).exists()
        )
        self.assertEqual(
            self._messages_for(self.author_a),
            ["「Bobさんがあなたの投稿にコメントしました」"],
        )

    def test_reply_mention_of_parent_author_dedupes_to_reply_only(self):
        parent = self._api_comment(self.user_b, "prior").json()["comment"]
        Notification.objects.all().delete()
        res = self._api_comment(
            self.user_c,
            f"@{self.user_b.username} 返信です",
            parent_id=parent["id"],
        )
        self.assertEqual(res.status_code, 201)
        notes = list(Notification.objects.filter(recipient=self.user_b))
        self.assertEqual(len(notes), 1)
        self.assertIn("あなたのコメントに返信しました", notes[0].message)
        self.assertNotIn("メンション", notes[0].message)

    def test_nested_reply_notifies_immediate_parent_not_root(self):
        root = self._api_comment(self.user_b, "root").json()["comment"]
        child = self._api_comment(
            self.user_c, "child", parent_id=root["id"]
        ).json()["comment"]
        Notification.objects.all().delete()
        res = self._api_comment(
            self.user_d, "grandchild", parent_id=child["id"]
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            self._messages_for(self.user_c),
            ["「Daveさんがあなたのコメントに返信しました」"],
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.user_c).count(), 1
        )
        self.assertNotIn(
            "あなたのコメントに返信しました",
            " ".join(self._messages_for(self.user_b)),
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.author_a).exists()
        )

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_reply_notification_uses_reply_push_body(self, mock_push):
        mock_push.return_value = 0
        parent = self._api_comment(self.user_b, "prior").json()["comment"]
        mock_push.reset_mock()
        self._api_comment(self.user_c, "reply", parent_id=parent["id"])
        bodies = {call.kwargs["body"] for call in mock_push.call_args_list}
        self.assertIn(
            "「Carolさんがあなたのコメントに返信しました」", bodies
        )
        self.assertIn(
            "「Carolさんがあなたの投稿にコメントしました」", bodies
        )
        self.assertEqual(mock_push.call_count, 2)
