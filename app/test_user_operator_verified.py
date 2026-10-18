"""User operator verification badge: model, admin, API, write protection."""

from __future__ import annotations

import json

from django.contrib.admin.sites import site
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .admin import UserAdmin
from .chat_message_services import serialize_chat_message, serialize_reply_preview
from .community_api_services import serialize_community, serialize_thread_summary
from .community_services import seed_communities
from .dm_api_services import serialize_dm_message, serialize_inbox_item
from .dm_services import get_or_create_dm_room
from .flea_api_services import (
    serialize_chat_room,
    serialize_comment,
    serialize_product_card,
)
from .follow_services import serialize_follow_request
from .models import (
    ChatMessage,
    ChatRoom,
    ChatRoomMembership,
    Comment,
    Community,
    CommunityThread,
    CommunityThreadReply,
    FollowRequest,
    Message,
    Notification,
    Product,
    TimelinePost,
    User,
    UserDirectMessage,
    UserProfile,
)
from .notification_api_services import serialize_notification
from .profile_api_services import serialize_profile_user
from .services import user_is_operator_verified
from .timeline_api_services import serialize_author
from .ugc_services import block_user


def _staff_user(*, email: str, with_change: bool) -> User:
    user = User.objects.create_user(
        email=email,
        password="test-pass-12345",
        is_staff=True,
    )
    if with_change:
        content_type = ContentType.objects.get_for_model(User)
        user.user_permissions.add(
            Permission.objects.get(
                content_type=content_type, codename="view_user"
            ),
            Permission.objects.get(
                content_type=content_type, codename="change_user"
            ),
        )
    return user


def _make_user(email: str, *, verified: bool = False, **kwargs) -> User:
    user = User.objects.create_user(
        email=email,
        password="test-pass-12345",
        **kwargs,
    )
    if verified:
        user.is_operator_verified = True
        user.save(update_fields=["is_operator_verified"])
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": email.split("@")[0]},
    )
    return user


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OperatorVerifiedModelTests(TestCase):
    def test_new_user_defaults_unverified(self):
        user = User.objects.create_user(
            email="badge-default@waseda.jp",
            password="test-pass-12345",
        )
        user.refresh_from_db()
        self.assertIs(user.is_operator_verified, False)
        self.assertFalse(user_is_operator_verified(user))
        self.assertFalse(user_is_operator_verified(None))

    def test_toggle_verified_independent_of_staff(self):
        user = _make_user("badge-toggle@waseda.jp")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        user.is_operator_verified = True
        user.save(update_fields=["is_operator_verified"])
        user.refresh_from_db()
        self.assertTrue(user.is_operator_verified)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        user.is_operator_verified = False
        user.save(update_fields=["is_operator_verified"])
        user.refresh_from_db()
        self.assertFalse(user.is_operator_verified)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OperatorVerifiedAdminTests(TestCase):
    def setUp(self):
        self.target = _make_user("badge-target@waseda.jp")
        self.factory = RequestFactory()
        self.model_admin = UserAdmin(User, site)
        self.change_url = reverse("admin:app_user_change", args=[self.target.pk])
        self.form_staff = _staff_user(
            email="badge-form-reader@waseda.jp", with_change=True
        )

    def _form_data(self, user: User, *, verified: bool, actor: User | None = None) -> dict:
        request = self.factory.get(self.change_url)
        request.user = actor or self.form_staff
        Form = self.model_admin.get_form(request, obj=user)
        bound = Form(instance=user)
        data = {}
        for name, field in bound.fields.items():
            value = bound[name].value()
            if name in ("date_joined", "last_login"):
                if value:
                    local = timezone.localtime(value) if timezone.is_aware(value) else value
                    data[f"{name}_0"] = local.strftime("%Y-%m-%d")
                    data[f"{name}_1"] = local.strftime("%H:%M:%S")
                continue
            if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
                data[name] = list(value)
            elif value is True:
                data[name] = "on"
            elif value is False or value is None:
                data[name] = ""
            else:
                data[name] = value
        if verified:
            data["is_operator_verified"] = "on"
        else:
            data.pop("is_operator_verified", None)
        return data

    def test_admin_exposes_verified_without_dropping_fields(self):
        listed = set(self.model_admin.list_display)
        self.assertIn("is_operator_verified", listed)
        self.assertIn("email", listed)
        self.assertIn("username", listed)
        self.assertIn("is_operator_verified", self.model_admin.list_filter)
        self.assertEqual(self.model_admin.search_fields, ("email", "username"))
        self.assertFalse(getattr(self.model_admin, "list_editable", ()))
        flat_fields = [
            field
            for _name, opts in self.model_admin.fieldsets
            for field in opts["fields"]
        ]
        for required in (
            "email",
            "password",
            "username",
            "is_operator_verified",
            "is_active",
            "is_staff",
            "is_superuser",
        ):
            self.assertIn(required, flat_fields)
        add_fields = [
            field
            for _name, opts in self.model_admin.add_fieldsets
            for field in opts["fields"]
        ]
        self.assertNotIn("is_operator_verified", add_fields)

    def test_change_user_staff_can_toggle_verified(self):
        staff = _staff_user(email="badge-admin@waseda.jp", with_change=True)
        client = Client()
        client.force_login(staff)
        get_response = client.get(self.change_url)
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "運営認証")
        self.assertContains(get_response, "id_is_operator_verified")

        request = self.factory.post(self.change_url, self._form_data(self.target, verified=True))
        request.user = staff
        Form = self.model_admin.get_form(request, obj=self.target)
        form = Form(self._form_data(self.target, verified=True), instance=self.target)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertTrue(saved.is_operator_verified)
        self.assertFalse(saved.is_staff)
        self.assertFalse(saved.is_superuser)

        form_off = Form(
            self._form_data(self.target, verified=False), instance=self.target
        )
        self.assertTrue(form_off.is_valid(), form_off.errors)
        saved_off = form_off.save()
        self.assertFalse(saved_off.is_operator_verified)

    def test_superuser_can_toggle_verified(self):
        superuser = User.objects.create_superuser(
            email="badge-super@waseda.jp",
            password="test-pass-12345",
        )
        request = self.factory.post(self.change_url)
        request.user = superuser
        Form = self.model_admin.get_form(request, obj=self.target)
        form = Form(self._form_data(self.target, verified=True), instance=self.target)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().is_operator_verified)

    def test_staff_without_change_permission_cannot_toggle(self):
        staff = _staff_user(email="badge-no-perm@waseda.jp", with_change=False)
        client = Client()
        client.force_login(staff)
        get_response = client.get(self.change_url)
        self.assertEqual(get_response.status_code, 403)
        post_response = client.post(
            self.change_url, self._form_data(self.target, verified=True)
        )
        self.assertEqual(post_response.status_code, 403)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_operator_verified)

    def test_non_staff_cannot_change_via_admin(self):
        user = _make_user("badge-user@waseda.jp")
        client = Client()
        client.force_login(user)
        get_response = client.get(self.change_url)
        self.assertIn(get_response.status_code, (302, 403))
        post_response = client.post(
            self.change_url, self._form_data(self.target, verified=True)
        )
        self.assertIn(post_response.status_code, (302, 403))
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_operator_verified)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OperatorVerifiedSerializerTests(TestCase):
    def setUp(self):
        self.verified = _make_user(
            "badge-author@waseda.jp", verified=True, username="badge_author"
        )
        self.plain = _make_user(
            "badge-plain@waseda.jp", verified=False, username="badge_plain"
        )

    def test_serialize_author_includes_flag_without_leaking_staff(self):
        payload = serialize_author(self.verified)
        self.assertTrue(payload["is_operator_verified"])
        self.assertEqual(payload["username"], "badge_author")
        self.assertNotIn("email", payload)
        self.assertNotIn("is_staff", payload)
        self.assertNotIn("is_superuser", payload)
        self.assertFalse(serialize_author(self.plain)["is_operator_verified"])
        self.assertIsNone(serialize_author(None))

    def test_profile_and_follow_request_serializers(self):
        profile = self.verified.profile
        payload = serialize_profile_user(self.verified, profile)
        self.assertTrue(payload["is_operator_verified"])
        self.assertIn("bio", payload)
        req = FollowRequest.objects.create(
            from_user=self.verified, to_user=self.plain
        )
        follow_payload = serialize_follow_request(req)
        self.assertTrue(follow_payload["from_user"]["is_operator_verified"])

    def test_dm_and_chat_sender_flags(self):
        room, _ = get_or_create_dm_room(self.plain, self.verified)
        message = UserDirectMessage.objects.create(
            room=room, sender=self.verified, body="hello"
        )
        payload = serialize_dm_message(message, self.plain.pk)
        self.assertTrue(payload["sender_is_operator_verified"])
        anonymized = serialize_dm_message(
            message, self.plain.pk, anonymize_partner=True
        )
        self.assertEqual(anonymized["sender_name"], "不明なユーザー")
        self.assertFalse(anonymized["sender_is_operator_verified"])

        group = ChatRoom.objects.create(kind=ChatRoom.Kind.GROUP, name="badge-g")
        ChatRoomMembership.objects.create(room=group, user=self.verified)
        ChatRoomMembership.objects.create(room=group, user=self.plain)
        chat = ChatMessage.objects.create(
            room=group, sender=self.verified, body="group hi"
        )
        chat_payload = serialize_chat_message(chat, self.plain.pk)
        self.assertTrue(chat_payload["sender_is_operator_verified"])
        self.assertEqual(chat_payload["sender_name"], serialize_author(self.verified)["display_name"])

        inbox = serialize_inbox_item(
            {
                "kind": "dm",
                "room": room,
                "display_name": "x",
                "partner": self.verified,
                "latest_message": message,
                "is_blocked": False,
            }
        )
        self.assertTrue(inbox["partner"]["is_operator_verified"])
        self.assertTrue(inbox["latest_sender_is_operator_verified"])

    def test_flea_seller_and_anonymous_comment(self):
        product = Product.objects.create(
            seller=self.verified,
            name="badge book",
            price=1000,
            description="d",
            category="未分類",
        )
        card = serialize_product_card(product)
        self.assertTrue(card["seller"]["is_operator_verified"])
        comment = Comment.objects.create(product=product, body="匿名コメント")
        payload = serialize_comment(comment)
        self.assertEqual(payload["author"]["display_name"], "匿名")
        self.assertFalse(payload["author"]["is_operator_verified"])


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OperatorVerifiedApiTests(TestCase):
    def setUp(self):
        self.verified = _make_user(
            "badge-api@waseda.jp", verified=True, username="badge_api"
        )
        self.viewer = _make_user("badge-viewer@waseda.jp", username="badge_viewer")
        self.post = TimelinePost.objects.create(
            author=self.verified, body="verified author post", like_count=0
        )
        self.client = Client()

    def test_me_and_profile_and_timeline(self):
        self.client.force_login(self.verified)
        me = self.client.get("/api/v1/me/")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.json()["user"]["is_operator_verified"])
        self.assertNotIn("is_staff", me.json()["user"])

        self.client.force_login(self.viewer)
        profile = self.client.get(f"/api/v1/profile/{self.verified.pk}/")
        self.assertEqual(profile.status_code, 200)
        self.assertTrue(profile.json()["user"]["is_operator_verified"])

        feed = self.client.get("/api/v1/timeline/")
        self.assertEqual(feed.status_code, 200)
        match = next(p for p in feed.json()["posts"] if p["id"] == self.post.pk)
        self.assertTrue(match["author"]["is_operator_verified"])

        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertTrue(detail.json()["post"]["author"]["is_operator_verified"])

    def test_comment_and_likers(self):
        self.client.force_login(self.verified)
        created = self.client.post(
            f"/api/v1/timeline/{self.post.pk}/comments/",
            {"body": "verified comment"},
        )
        self.assertIn(created.status_code, (200, 201))
        self.assertTrue(created.json()["comment"]["author"]["is_operator_verified"])
        self.client.post(f"/api/v1/timeline/{self.post.pk}/like/")
        likers = self.client.get(f"/api/v1/timeline/{self.post.pk}/likers/")
        self.assertEqual(likers.status_code, 200)
        self.assertTrue(
            any(u.get("is_operator_verified") for u in likers.json().get("users", []))
        )

    def test_search_discover_follow_and_timetable(self):
        self.client.force_login(self.viewer)
        search = self.client.get("/api/v1/search/", {"q": "badge_api", "tab": "users"})
        self.assertEqual(search.status_code, 200)
        users = search.json().get("users") or []
        match = next(u for u in users if u and u.get("id") == self.verified.pk)
        self.assertTrue(match["is_operator_verified"])

        Product.objects.create(
            seller=self.verified,
            name="badge discover item",
            price=800,
            category="未分類",
        )
        discover = self.client.get("/api/v1/search/")
        self.assertEqual(discover.status_code, 200)
        products = (discover.json().get("discover") or {}).get("products") or []
        self.assertTrue(
            any(
                (p.get("seller") or {}).get("is_operator_verified")
                for p in products
            )
        )
        flea = self.client.get("/api/v1/flea/")
        self.assertEqual(flea.status_code, 200)
        self.assertTrue(
            any(
                (p.get("seller") or {}).get("is_operator_verified")
                for p in flea.json().get("products") or []
            )
        )

        following = self.client.get(f"/api/v1/profile/{self.verified.pk}/following/")
        self.assertEqual(following.status_code, 200)

        profile = self.verified.profile
        profile.is_timetable_public = True
        profile.save(update_fields=["is_timetable_public"])
        timetable = self.client.get(f"/api/timetable/user/{self.verified.pk}/")
        self.assertEqual(timetable.status_code, 200)
        self.assertTrue(timetable.json()["owner"]["is_operator_verified"])

    def test_dm_partner_and_group_member(self):
        self.client.force_login(self.viewer)
        start = self.client.post(
            "/api/v1/dm/start/",
            data={"user_id": self.verified.pk},
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 200)
        room_id = start.json()["room_id"]
        room = self.client.get(f"/api/v1/dm/rooms/{room_id}/")
        self.assertTrue(room.json()["room"]["partner"]["is_operator_verified"])

        group = self.client.post(
            "/api/v1/dm/groups/",
            data=json.dumps({"name": "badge group", "member_ids": [self.verified.pk]}),
            content_type="application/json",
        )
        self.assertEqual(group.status_code, 201)
        group_id = group.json()["room_id"]
        detail = self.client.get(f"/api/v1/dm/groups/{group_id}/")
        room = detail.json()["room"]
        flags = [
            m.get("is_operator_verified")
            for m in room.get("members") or []
            if m and m.get("id") == self.verified.pk
        ]
        flags.extend(
            (row.get("invitee") or {}).get("is_operator_verified")
            for row in room.get("pending_invites") or []
            if (row.get("invitee") or {}).get("id") == self.verified.pk
        )
        self.assertTrue(any(flags), room)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OperatorVerifiedWriteProtectionTests(TestCase):
    def setUp(self):
        self.user = _make_user("badge-write@waseda.jp", username="badge_write")
        self.client = Client()

    def test_signup_cannot_inject_flag(self):
        signup = self.client.post(
            "/api/v1/auth/signup/",
            data=json.dumps(
                {
                    "email": "badge-inject@waseda.jp",
                    "password1": "test-pass-12345",
                    "password2": "test-pass-12345",
                    "accept_terms": True,
                    "is_operator_verified": True,
                    "is_verified": True,
                    "is_official": True,
                    "is_staff": True,
                    "is_superuser": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup.status_code, 201)
        created = User.objects.get(email="badge-inject@waseda.jp")
        self.assertFalse(created.is_operator_verified)
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)

    def test_onboarding_cannot_inject_flag(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/v1/onboarding/profile/",
            data=json.dumps(
                {
                    "name": "注入太郎",
                    "username": "badge_write2",
                    "department": "商学部",
                    "is_operator_verified": True,
                    "is_verified": True,
                    "is_official": True,
                }
            ),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (200, 400))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_operator_verified)

    def test_profile_edit_cannot_inject_flag(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/mypage/edit/",
            {
                "name": "編集太郎",
                "user_id": self.user.username,
                "bio": "bio",
                "department": "商学部",
                "grade": "",
                "is_operator_verified": "on",
                "is_verified": "on",
                "is_official": "on",
            },
        )
        self.assertIn(response.status_code, (200, 302))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_operator_verified)

    def test_privacy_api_cannot_inject_flag(self):
        self.client.force_login(self.user)
        response = self.client.patch(
            "/api/v1/me/privacy/",
            data=json.dumps(
                {
                    "is_private": True,
                    "is_operator_verified": True,
                    "is_verified": True,
                    "is_official": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_operator_verified)
        self.assertTrue(self.user.profile.is_private)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OperatorVerifiedCommunityIsolationTests(TestCase):
    def setUp(self):
        seed_communities()
        self.author = _make_user(
            "badge-anon@waseda.jp", verified=True, username="badge_anon"
        )
        self.community = Community.objects.filter(is_active=True).first()
        self.thread = CommunityThread.objects.create(
            community=self.community,
            author=self.author,
            title="匿名確認",
            body="本文",
        )
        self.client = Client()

    def test_community_payloads_omit_user_verification(self):
        listed = self.client.get("/api/v1/communities/threads/")
        payload = next(t for t in listed.json()["threads"] if t["id"] == self.thread.pk)
        blob = json.dumps(payload)
        self.assertNotIn("is_operator_verified", blob)
        self.assertIn("anonymous_label", payload)
        community = payload["community"]
        self.assertIn("is_official", community)
        self.assertNotIn("is_operator_verified", community)

        reply = CommunityThreadReply.objects.create(
            thread=self.thread, author=self.author, body="返信"
        )
        detail = self.client.get(
            f"/api/v1/communities/{self.community.slug}/threads/{self.thread.pk}/"
        )
        self.assertEqual(detail.status_code, 200)
        detail_blob = json.dumps(detail.json())
        self.assertNotIn("is_operator_verified", detail_blob)
        self.assertIn("is_official", detail_blob)
        replies = detail.json().get("thread", {}).get("replies") or detail.json().get("replies") or []
        self.assertTrue(any(r["id"] == reply.pk for r in replies))

        note = Notification.objects.create(
            recipient=self.author,
            message="コミュニティの投稿に返信がありました",
            link="/app/communities/",
        )
        serialized = serialize_notification(note)
        self.assertEqual(serialized["message"], note.message)
        self.assertNotIn("is_operator_verified", serialized)
        self.assertNotIn("actor", serialized)

    def test_community_official_still_serializes(self):
        self.community.is_official = True
        self.community.save(update_fields=["is_official"])
        payload = serialize_community(self.community)
        self.assertTrue(payload["is_official"])
        summary = serialize_thread_summary(self.thread, None)
        self.assertTrue(summary["community"]["is_official"])
        self.assertNotIn("is_operator_verified", summary)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OperatorVerifiedMixedIdentityTests(TestCase):
    def setUp(self):
        self.verified = _make_user(
            "badge-mix-a@waseda.jp", verified=True, username="badge_mix_a"
        )
        self.plain = _make_user(
            "badge-mix-b@waseda.jp", verified=False, username="badge_mix_b"
        )
        self.client = Client()

    def _inbox(self, *, viewer, partner, latest_sender, blocked=False):
        room, _ = get_or_create_dm_room(viewer, partner)
        message = UserDirectMessage.objects.create(
            room=room, sender=latest_sender, body="latest mix"
        )
        return serialize_inbox_item(
            {
                "kind": "dm",
                "room": room,
                "display_name": "blocked" if blocked else "partner",
                "partner": partner,
                "latest_message": message,
                "latest_sender_display_name": (
                    "不明なユーザー" if blocked else latest_sender.email.split("@")[0]
                ),
                "is_blocked": blocked,
            }
        )

    def test_partner_verified_latest_sender_unverified(self):
        inbox = self._inbox(
            viewer=self.plain, partner=self.verified, latest_sender=self.plain
        )
        self.assertTrue(inbox["partner"]["is_operator_verified"])
        self.assertEqual(inbox["partner"]["id"], self.verified.pk)
        self.assertFalse(inbox["latest_sender_is_operator_verified"])
        self.assertNotEqual(
            inbox["partner"]["is_operator_verified"],
            inbox["latest_sender_is_operator_verified"],
        )

    def test_partner_unverified_latest_sender_verified(self):
        inbox = self._inbox(
            viewer=self.verified, partner=self.plain, latest_sender=self.verified
        )
        self.assertFalse(inbox["partner"]["is_operator_verified"])
        self.assertEqual(inbox["partner"]["id"], self.plain.pk)
        self.assertTrue(inbox["latest_sender_is_operator_verified"])
        self.assertNotEqual(
            inbox["partner"]["is_operator_verified"],
            inbox["latest_sender_is_operator_verified"],
        )

    def test_self_verified_partner_unverified_room_messages(self):
        room, _ = get_or_create_dm_room(self.verified, self.plain)
        mine = UserDirectMessage.objects.create(
            room=room, sender=self.verified, body="from verified"
        )
        theirs = UserDirectMessage.objects.create(
            room=room, sender=self.plain, body="from plain"
        )
        mine_payload = serialize_dm_message(mine, self.verified.pk)
        theirs_payload = serialize_dm_message(theirs, self.verified.pk)
        self.assertTrue(mine_payload["sender_is_operator_verified"])
        self.assertEqual(mine_payload["sender_id"], self.verified.pk)
        self.assertFalse(theirs_payload["sender_is_operator_verified"])
        self.assertEqual(theirs_payload["sender_id"], self.plain.pk)

        self.client.force_login(self.verified)
        start = self.client.post(
            "/api/v1/dm/start/",
            data={"user_id": self.plain.pk},
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 200)
        detail = self.client.get(f"/api/v1/dm/rooms/{start.json()['room_id']}/")
        self.assertFalse(detail.json()["room"]["partner"]["is_operator_verified"])
        self.assertEqual(detail.json()["room"]["partner"]["id"], self.plain.pk)

    def test_self_unverified_partner_verified_room_messages(self):
        room, _ = get_or_create_dm_room(self.plain, self.verified)
        mine = UserDirectMessage.objects.create(
            room=room, sender=self.plain, body="from plain"
        )
        theirs = UserDirectMessage.objects.create(
            room=room, sender=self.verified, body="from verified"
        )
        self.assertFalse(
            serialize_dm_message(mine, self.plain.pk)["sender_is_operator_verified"]
        )
        self.assertTrue(
            serialize_dm_message(theirs, self.plain.pk)["sender_is_operator_verified"]
        )
        self.client.force_login(self.plain)
        room_payload = self.client.get(f"/api/v1/dm/rooms/{room.pk}/").json()["room"]
        self.assertTrue(room_payload["partner"]["is_operator_verified"])
        self.assertEqual(room_payload["partner"]["id"], self.verified.pk)

    def test_blocked_partner_hides_verification_without_dropping_identity_keys(self):
        inbox = self._inbox(
            viewer=self.plain,
            partner=self.verified,
            latest_sender=self.verified,
            blocked=True,
        )
        self.assertIn("id", inbox["partner"])
        self.assertIn("username", inbox["partner"])
        self.assertIn("display_name", inbox["partner"])
        self.assertIn("is_operator_verified", inbox["partner"])
        self.assertEqual(inbox["partner"]["id"], self.verified.pk)
        self.assertFalse(inbox["partner"]["is_operator_verified"])
        self.assertFalse(inbox["latest_sender_is_operator_verified"])

        room, _ = get_or_create_dm_room(self.plain, self.verified)
        UserDirectMessage.objects.create(
            room=room, sender=self.verified, body="before block"
        )
        block_user(self.plain, self.verified)
        self.client.force_login(self.plain)
        detail = self.client.get(f"/api/v1/dm/rooms/{room.pk}/")
        self.assertEqual(detail.status_code, 200)
        partner = detail.json()["room"]["partner"]
        self.assertTrue(detail.json()["room"]["is_blocked"])
        self.assertEqual(partner["id"], self.verified.pk)
        self.assertFalse(partner["is_operator_verified"])
        theirs = [m for m in detail.json()["messages"] if not m["is_mine"]]
        self.assertTrue(theirs)
        self.assertEqual(theirs[0]["sender_name"], "不明なユーザー")
        self.assertFalse(theirs[0]["sender_is_operator_verified"])

    def test_group_members_and_messages_keep_each_sender_flag(self):
        self.client.force_login(self.plain)
        created = self.client.post(
            "/api/v1/dm/groups/",
            data=json.dumps(
                {"name": "mix group", "member_ids": [self.verified.pk]}
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        room_id = created.json()["room_id"]
        verified_client = Client()
        verified_client.force_login(self.verified)
        accept = verified_client.post(
            f"/api/v1/dm/groups/{room_id}/invitations/accept/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(accept.status_code, 200, accept.content)

        from_verified = verified_client.post(
            f"/api/v1/dm/groups/{room_id}/messages/send/",
            data={"body": "hello from A"},
            content_type="application/json",
        )
        self.assertEqual(from_verified.status_code, 201, from_verified.content)
        verified_msg = from_verified.json()["message"]
        self.assertTrue(verified_msg["sender_is_operator_verified"])
        self.assertEqual(verified_msg["sender_id"], self.verified.pk)

        from_plain = self.client.post(
            f"/api/v1/dm/groups/{room_id}/messages/send/",
            data={
                "body": "reply from B",
                "reply_to_id": verified_msg["id"],
            },
            content_type="application/json",
        )
        self.assertEqual(from_plain.status_code, 201, from_plain.content)
        plain_msg = from_plain.json()["message"]
        self.assertFalse(plain_msg["sender_is_operator_verified"])
        self.assertEqual(plain_msg["sender_id"], self.plain.pk)
        self.assertTrue(plain_msg["reply_to"]["sender_is_operator_verified"])
        self.assertEqual(plain_msg["reply_to"]["sender_name"], verified_msg["sender_name"])

        reverse_reply = verified_client.post(
            f"/api/v1/dm/groups/{room_id}/messages/send/",
            data={
                "body": "reply from A",
                "reply_to_id": plain_msg["id"],
            },
            content_type="application/json",
        )
        self.assertEqual(reverse_reply.status_code, 201, reverse_reply.content)
        reverse_payload = reverse_reply.json()["message"]
        self.assertTrue(reverse_payload["sender_is_operator_verified"])
        self.assertFalse(reverse_payload["reply_to"]["sender_is_operator_verified"])

        detail = self.client.get(f"/api/v1/dm/groups/{room_id}/")
        members = {m["id"]: m["is_operator_verified"] for m in detail.json()["room"]["members"]}
        self.assertTrue(members[self.verified.pk])
        self.assertFalse(members[self.plain.pk])

    def test_reply_preview_uses_target_sender_not_viewer(self):
        group = ChatRoom.objects.create(kind=ChatRoom.Kind.GROUP, name="preview-mix")
        ChatRoomMembership.objects.create(room=group, user=self.verified)
        ChatRoomMembership.objects.create(room=group, user=self.plain)
        parent = ChatMessage.objects.create(
            room=group, sender=self.verified, body="parent from A"
        )
        child = ChatMessage.objects.create(
            room=group, sender=self.plain, body="child from B", reply_to=parent
        )
        preview = serialize_reply_preview(parent)
        self.assertTrue(preview["sender_is_operator_verified"])
        child_payload = serialize_chat_message(child, self.verified.pk)
        self.assertFalse(child_payload["sender_is_operator_verified"])
        self.assertTrue(child_payload["reply_to"]["sender_is_operator_verified"])
        other_parent = ChatMessage.objects.create(
            room=group, sender=self.plain, body="parent from B"
        )
        other_child = ChatMessage.objects.create(
            room=group, sender=self.verified, body="child from A", reply_to=other_parent
        )
        other_payload = serialize_chat_message(other_child, self.plain.pk)
        self.assertTrue(other_payload["sender_is_operator_verified"])
        self.assertFalse(other_payload["reply_to"]["sender_is_operator_verified"])

    def test_trade_chat_partner_and_senders_stay_distinct(self):
        product = Product.objects.create(
            seller=self.verified,
            name="mix trade book",
            price=1200,
            description="d",
            category="未分類",
            faculty="政治経済学部",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.client.force_login(self.plain)
        purchase = self.client.post(f"/api/v1/flea/products/{product.pk}/purchase/")
        self.assertEqual(purchase.status_code, 200, purchase.content)
        room_id = purchase.json()["room_id"]
        room = ChatRoom.objects.get(pk=room_id)
        Message.objects.create(chat_room=room, sender=self.verified, body="seller hi")
        Message.objects.create(chat_room=room, sender=self.plain, body="buyer hi")

        buyer_view = serialize_chat_room(room, self.plain)
        seller_view = serialize_chat_room(room, self.verified)
        self.assertTrue(buyer_view["partner"]["is_operator_verified"])
        self.assertEqual(buyer_view["partner"]["id"], self.verified.pk)
        self.assertFalse(seller_view["partner"]["is_operator_verified"])
        self.assertEqual(seller_view["partner"]["id"], self.plain.pk)

        messages = self.client.get(f"/api/v1/flea/chats/{room_id}/messages/").json()[
            "messages"
        ]
        by_sender = {m["sender_id"]: m["sender_is_operator_verified"] for m in messages}
        self.assertTrue(by_sender[self.verified.pk])
        self.assertFalse(by_sender[self.plain.pk])

        seller_client = Client()
        seller_client.force_login(self.verified)
        seller_room = seller_client.get(f"/api/v1/flea/chats/{room_id}/")
        self.assertEqual(seller_room.status_code, 200)
        self.assertFalse(seller_room.json()["room"]["partner"]["is_operator_verified"])
        self.assertEqual(seller_room.json()["room"]["partner"]["id"], self.plain.pk)
