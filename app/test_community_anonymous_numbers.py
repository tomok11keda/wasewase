"""Thread-local anonymous numbers: assignment, stability, privacy."""

from __future__ import annotations

import json
import threading
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .account_deletion_services import delete_user_account
from .community_participant_services import (
    CREATOR_NUMBER,
    anonymous_label_for,
    ensure_participants_for_thread,
    get_or_assign_participant,
    participant_numbers,
)
from .community_services import (
    create_community_thread,
    create_thread_reply,
    seed_communities,
    soft_remove_community_reply,
)
from .models import (
    Community,
    CommunityThread,
    CommunityThreadParticipant,
    CommunityThreadReply,
    User,
)


IDENTITY_KEYS = (
    "author",
    "author_id",
    "user_id",
    "username",
    "display_name",
    "email",
    "first_name",
    "last_name",
    "avatar_url",
    "profile_url",
    "initial",
    "anonymous_id",
    "global_id",
)


def _assert_no_identity(testcase: TestCase, payload: dict) -> None:
    for key in IDENTITY_KEYS:
        testcase.assertNotIn(key, payload)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityAnonymousNumberTests(TestCase):
    def setUp(self):
        seed_communities()
        self.community = Community.objects.filter(is_active=True).first()
        self.creator = User.objects.create_user(
            email="num-creator@waseda.jp",
            password="test-pass-12345",
            username="num_creator",
            first_name="創",
            last_name="作",
        )
        self.alice = User.objects.create_user(
            email="num-alice@waseda.jp",
            password="test-pass-12345",
            username="num_alice",
        )
        self.bob = User.objects.create_user(
            email="num-bob@waseda.jp",
            password="test-pass-12345",
            username="num_bob",
        )
        self.cara = User.objects.create_user(
            email="num-cara@waseda.jp",
            password="test-pass-12345",
            username="num_cara",
        )
        self.client = Client()

    def _api_create_thread(self, user, *, title="番号スレ", body="本文"):
        self.client.force_login(user)
        created = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps(
                {
                    "title": title,
                    "body": body,
                    "tag": self.community.faculty or "",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        return created.json()["thread"]

    def _api_reply(self, user, slug, pk, body, reply_to_id=None):
        self.client.force_login(user)
        payload = {"body": body}
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id
        response = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["reply"]

    def test_creator_is_user_one(self):
        thread = self._api_create_thread(self.creator)
        self.assertEqual(thread["anonymous_number"], CREATOR_NUMBER)
        self.assertEqual(thread["anonymous_label"], "ユーザー1")
        mapping = CommunityThreadParticipant.objects.get(
            thread_id=thread["id"], user=self.creator
        )
        self.assertEqual(mapping.anonymous_number, 1)

    def test_first_distinct_commenter_is_user_two(self):
        thread = self._api_create_thread(self.creator)
        slug = thread["community"]["slug"]
        reply = self._api_reply(self.alice, slug, thread["id"], "初コメント")
        self.assertEqual(reply["anonymous_number"], 2)
        self.assertEqual(reply["anonymous_label"], "ユーザー2")

    def test_same_user_keeps_number_across_comments_and_nested_replies(self):
        thread = self._api_create_thread(self.creator)
        slug = thread["community"]["slug"]
        pk = thread["id"]
        top = self._api_reply(self.alice, slug, pk, "トップ")
        nested = self._api_reply(
            self.alice, slug, pk, "ネスト", reply_to_id=top["id"]
        )
        again = self._api_reply(self.alice, slug, pk, "もう一度")
        self.assertEqual(top["anonymous_number"], 2)
        self.assertEqual(nested["anonymous_number"], 2)
        self.assertEqual(again["anonymous_number"], 2)
        self.assertEqual(
            CommunityThreadParticipant.objects.filter(
                thread_id=pk, user=self.alice
            ).count(),
            1,
        )

    def test_nested_and_top_level_share_one_sequence(self):
        thread = self._api_create_thread(self.creator)
        slug = thread["community"]["slug"]
        pk = thread["id"]
        top = self._api_reply(self.alice, slug, pk, "alice top")
        nested = self._api_reply(
            self.bob, slug, pk, "bob nested", reply_to_id=top["id"]
        )
        later_top = self._api_reply(self.bob, slug, pk, "bob later top")
        self.assertEqual(nested["anonymous_number"], 3)
        self.assertEqual(later_top["anonymous_number"], 3)
        self.assertEqual(anonymous_label_for(3), "ユーザー3")

    def test_numbers_are_thread_local(self):
        thread_a = create_community_thread(
            self.community, self.creator, "A", "body A"
        )
        thread_b = create_community_thread(
            self.community, self.bob, "B", "body B"
        )
        create_thread_reply(thread_a, self.alice, "a1")
        create_thread_reply(thread_a, self.bob, "a2")
        create_thread_reply(thread_b, self.cara, "b1")
        create_thread_reply(thread_b, self.alice, "b2")
        create_thread_reply(thread_b, self.creator, "b3")
        nums_a = participant_numbers(thread_a)
        nums_b = participant_numbers(thread_b)
        self.assertEqual(nums_a[self.creator.pk], 1)
        self.assertEqual(nums_a[self.alice.pk], 2)
        self.assertEqual(nums_a[self.bob.pk], 3)
        self.assertEqual(nums_b[self.bob.pk], 1)
        self.assertEqual(nums_b[self.cara.pk], 2)
        self.assertEqual(nums_b[self.alice.pk], 3)
        self.assertEqual(nums_b[self.creator.pk], 4)
        self.assertNotEqual(nums_a[self.alice.pk], nums_b[self.alice.pk])

    def test_soft_delete_does_not_renumber(self):
        thread = create_community_thread(
            self.community, self.creator, "del", "body"
        )
        r2 = create_thread_reply(thread, self.alice, "alice")
        r3 = create_thread_reply(thread, self.bob, "bob")
        soft_remove_community_reply(r2)
        self.client.force_login(self.cara)
        detail = self.client.get(
            f"/api/v1/communities/{thread.community.slug}/threads/{thread.pk}/"
        ).json()["thread"]
        by_id = {item["id"]: item for item in detail["replies"]}
        self.assertTrue(by_id[r2.pk]["is_removed"])
        self.assertNotIn("anonymous_number", by_id[r2.pk])
        self.assertEqual(by_id[r3.pk]["anonymous_number"], 3)
        self.assertEqual(by_id[r3.pk]["anonymous_label"], "ユーザー3")
        self.assertEqual(participant_numbers(thread)[self.bob.pk], 3)

    def test_moderation_hide_does_not_renumber(self):
        thread = create_community_thread(
            self.community, self.creator, "mod", "body"
        )
        hidden = create_thread_reply(thread, self.alice, "hide me")
        later = create_thread_reply(thread, self.bob, "still 3")
        hidden.is_removed = True
        hidden.save(update_fields=["is_removed"])
        nums = participant_numbers(thread)
        self.assertEqual(nums[self.alice.pk], 2)
        self.assertEqual(nums[self.bob.pk], 3)
        later.refresh_from_db()
        self.assertEqual(
            get_or_assign_participant(thread=thread, user=self.bob), 3
        )

    def test_backfill_is_deterministic_with_tie_break(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.creator,
            title="既存",
            body="本文",
        )
        now = timezone.now()
        first = CommunityThreadReply.objects.create(
            thread=thread, author=self.bob, body="later pk"
        )
        second = CommunityThreadReply.objects.create(
            thread=thread, author=self.alice, body="earlier pk wait"
        )
        CommunityThreadReply.objects.filter(pk=first.pk).update(created_at=now)
        CommunityThreadReply.objects.filter(pk=second.pk).update(created_at=now)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.created_at, second.created_at)
        self.assertLess(first.pk, second.pk)

        nums = ensure_participants_for_thread(thread)
        self.assertEqual(nums[self.creator.pk], 1)
        self.assertEqual(nums[self.bob.pk], 2)
        self.assertEqual(nums[self.alice.pk], 3)
        thread.refresh_from_db()
        self.assertEqual(thread.author_id, self.creator.pk)

    def test_lazy_backfill_on_detail_does_not_rewrite_author_fk(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.creator,
            title="lazy",
            body="body",
        )
        reply = CommunityThreadReply.objects.create(
            thread=thread, author=self.alice, body="hi"
        )
        self.client.force_login(self.bob)
        detail = self.client.get(
            f"/api/v1/communities/{thread.community.slug}/threads/{thread.pk}/"
        ).json()["thread"]
        self.assertEqual(detail["anonymous_number"], 1)
        self.assertEqual(detail["replies"][0]["anonymous_number"], 2)
        thread.refresh_from_db()
        reply.refresh_from_db()
        self.assertEqual(thread.author_id, self.creator.pk)
        self.assertEqual(reply.author_id, self.alice.pk)

    def test_api_privacy_and_owner_controls(self):
        thread = self._api_create_thread(self.creator)
        slug = thread["community"]["slug"]
        pk = thread["id"]
        listed = self.client.get("/api/v1/communities/threads/").json()["threads"]
        payload = next(item for item in listed if item["id"] == pk)
        _assert_no_identity(self, payload)
        self.assertEqual(payload["anonymous_label"], "ユーザー1")
        self.assertTrue(payload["is_mine"])
        self.assertTrue(payload["can_delete"])
        self.assertFalse(payload["can_report"])

        reply = self._api_reply(self.alice, slug, pk, "alice")
        _assert_no_identity(self, reply)
        self.assertTrue(reply["is_mine"])
        self.assertTrue(reply["can_edit"])
        self.assertTrue(reply["can_delete"])
        blob = json.dumps(reply)
        self.assertNotIn("num_alice", blob)
        self.assertNotIn("num-alice@waseda.jp", blob)

        self.client.force_login(self.creator)
        detail = self.client.get(
            f"/api/v1/communities/{slug}/threads/{pk}/"
        ).json()["thread"]
        _assert_no_identity(self, detail)
        viewed = next(item for item in detail["replies"] if item["id"] == reply["id"])
        _assert_no_identity(self, viewed)
        self.assertFalse(viewed["is_mine"])
        self.assertTrue(viewed["can_report"])
        self.assertIn("anonymous_number", viewed)
        self.assertIn("anonymous_label", viewed)

    def test_unique_constraints_prevent_duplicate_numbers(self):
        thread = create_community_thread(
            self.community, self.creator, "uniq", "body"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CommunityThreadParticipant.objects.create(
                    thread=thread,
                    user=self.alice,
                    anonymous_number=CREATOR_NUMBER,
                )
        get_or_assign_participant(thread=thread, user=self.alice)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CommunityThreadParticipant.objects.create(
                    thread=thread,
                    user=self.bob,
                    anonymous_number=2,
                )

    @patch("app.bookmark_services.get_firestore_client", return_value=None)
    def test_account_deletion_does_not_pack_remaining_numbers(self, _mock):
        thread = create_community_thread(
            self.community, self.creator, "leave", "body"
        )
        create_thread_reply(thread, self.alice, "alice 2")
        create_thread_reply(thread, self.bob, "bob 3")
        alice_id = self.alice.pk
        delete_user_account(self.alice)
        self.assertFalse(User.objects.filter(pk=alice_id).exists())
        nums = participant_numbers(thread)
        self.assertEqual(nums[self.creator.pk], 1)
        self.assertEqual(nums[self.bob.pk], 3)
        self.assertNotIn(alice_id, nums)
        reserved = CommunityThreadParticipant.objects.get(
            thread=thread, anonymous_number=2
        )
        self.assertIsNone(reserved.user_id)
        next_n = get_or_assign_participant(thread=thread, user=self.cara)
        self.assertEqual(next_n, 4)

    def test_ensure_participants_does_not_shift_existing_mapping(self):
        thread = create_community_thread(
            self.community, self.creator, "stable", "body"
        )
        create_thread_reply(thread, self.alice, "a")
        create_thread_reply(thread, self.bob, "b")
        CommunityThreadReply.objects.filter(thread=thread, author=self.alice).delete()
        again = ensure_participants_for_thread(thread)
        self.assertEqual(again[self.bob.pk], 3)
        self.assertEqual(again[self.alice.pk], 2)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityParticipantConcurrencyTests(TransactionTestCase):
    def setUp(self):
        seed_communities()
        self.community = Community.objects.filter(is_active=True).first()
        self.creator = User.objects.create_user(
            email="race-creator@waseda.jp",
            password="test-pass-12345",
            username="race_creator",
        )
        self.u1 = User.objects.create_user(
            email="race-u1@waseda.jp",
            password="test-pass-12345",
            username="race_u1",
        )
        self.u2 = User.objects.create_user(
            email="race-u2@waseda.jp",
            password="test-pass-12345",
            username="race_u2",
        )

    def test_concurrent_first_commenters_get_distinct_numbers(self):
        if connection.vendor == "sqlite":
            self.skipTest(
                "SQLite write lock is not the production race; unique+retry is the PG guard."
            )
        thread = create_community_thread(
            self.community, self.creator, "race", "body"
        )
        results: list[int] = []
        errors: list[BaseException] = []

        def worker(user):
            try:
                results.append(get_or_assign_participant(thread=thread, user=user))
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)
            finally:
                connection.close()

        threads = [
            threading.Thread(target=worker, args=(self.u1,)),
            threading.Thread(target=worker, args=(self.u2,)),
        ]
        for item in threads:
            item.start()
        for item in threads:
            item.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), [2, 3])
        numbers = list(
            CommunityThreadParticipant.objects.filter(thread=thread)
            .exclude(user=self.creator)
            .values_list("anonymous_number", flat=True)
        )
        self.assertEqual(sorted(numbers), [2, 3])
