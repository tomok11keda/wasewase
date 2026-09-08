"""退会時の Firestore / 画像削除、ログ、規約同意履歴のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .account_deletion_services import delete_user_account
from .constants import CURRENT_TERMS_VERSION
from .models import Product, TimelinePost, UserProfile

_MINIMAL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\x00\x00\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x01D\x00;"
)


def _fake_doc(doc_id: str) -> MagicMock:
    doc = MagicMock()
    doc.id = doc_id
    doc.reference = MagicMock()
    return doc


def _firestore_db_for_users(user_docs: dict[str, dict[str, list]]) -> MagicMock:
    """users/{uid}/{collection} をユーザーごとに分離したモック。"""

    def document(user_key):
        user_mock = MagicMock()

        def collection(name):
            col = MagicMock()
            col.stream.return_value = list(
                user_docs.get(str(user_key), {}).get(name, [])
            )
            return col

        user_mock.collection.side_effect = collection
        return user_mock

    users_col = MagicMock()
    users_col.document.side_effect = document
    db = MagicMock()
    db.collection.return_value = users_col
    db._users_collection = users_col
    return db


class TermsAcceptanceHistoryTests(TestCase):
    def test_existing_profile_does_not_invent_acceptance_time_or_version(self):
        User = get_user_model()
        user = User.objects.create_user(
            email="legacy-terms@example.com",
            password="pass12345",
            username="legacy_terms",
        )
        profile = UserProfile.objects.create(user=user, terms_accepted=True)
        self.assertTrue(profile.terms_accepted)
        self.assertIsNone(profile.terms_accepted_at)
        self.assertEqual(profile.terms_version, "")

    def test_signup_saves_terms_version_and_time(self):
        before = timezone.now()
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            DEFAULT_FROM_EMAIL="test@example.com",
        ):
            response = self.client.post(
                reverse("signup"),
                {
                    "email": "terms-new@waseda.jp",
                    "nickname": "同意太郎",
                    "username": "terms_new",
                    "password1": "newpass123",
                    "password2": "newpass123",
                    "faculty": "法学部",
                    "accept_terms": "on",
                },
            )
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(email="terms-new@waseda.jp")
        profile = UserProfile.objects.get(user=user)
        self.assertTrue(profile.terms_accepted)
        self.assertEqual(profile.terms_version, CURRENT_TERMS_VERSION)
        self.assertIsNotNone(profile.terms_accepted_at)
        self.assertGreaterEqual(profile.terms_accepted_at, before)


class AccountDeletionPrivacyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="privacy-delete@example.com",
            password="pass12345",
            username="privacy_delete",
        )
        self.other = User.objects.create_user(
            email="privacy-other@example.com",
            password="pass12345",
            username="privacy_other",
        )

    @patch("app.bookmark_services.get_firestore_client", return_value=None)
    def test_delete_account_without_firestore(self, _mock_client):
        delete_user_account(self.user)
        self.assertFalse(
            get_user_model().objects.filter(pk=self.user.pk).exists()
        )
        self.assertTrue(
            get_user_model().objects.filter(pk=self.other.pk).exists()
        )

    @patch("app.bookmark_services.get_firestore_client")
    def test_delete_account_removes_only_that_users_firestore_bookmarks(
        self, mock_get_client
    ):
        own_bookmark = _fake_doc("11")
        own_product = _fake_doc("22")
        other_bookmark = _fake_doc("99")
        db = _firestore_db_for_users(
            {
                str(self.user.pk): {
                    "bookmarks": [own_bookmark],
                    "product_bookmarks": [own_product],
                },
                str(self.other.pk): {"bookmarks": [other_bookmark]},
            }
        )
        mock_get_client.return_value = db
        user_id = self.user.pk

        delete_user_account(self.user)

        self.assertFalse(
            get_user_model().objects.filter(pk=user_id).exists()
        )
        own_bookmark.reference.delete.assert_called_once()
        own_product.reference.delete.assert_called_once()
        other_bookmark.reference.delete.assert_not_called()
        called_ids = [
            call.args[0] for call in db._users_collection.document.call_args_list
        ]
        self.assertEqual(set(called_ids), {str(user_id)})

    @patch("app.bookmark_services.get_firestore_client")
    def test_delete_account_succeeds_when_firestore_delete_fails(
        self, mock_get_client
    ):
        db = MagicMock()
        user_doc = MagicMock()
        collection = MagicMock()
        collection.stream.side_effect = RuntimeError("firestore down")
        user_doc.collection.return_value = collection
        db.collection.return_value.document.return_value = user_doc
        mock_get_client.return_value = db

        delete_user_account(self.user)
        self.assertFalse(
            get_user_model().objects.filter(pk=self.user.pk).exists()
        )

    @patch("app.bookmark_services.get_firestore_client", return_value=None)
    def test_delete_account_removes_owned_images_not_others(self, _mock_client):
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.avatar.save("del_avatar.gif", ContentFile(_MINIMAL_GIF), save=True)
        avatar_name = profile.avatar.name

        post = TimelinePost.objects.create(author=self.user, body="画像付き")
        post.image.save("del_post.gif", ContentFile(_MINIMAL_GIF), save=True)
        post_name = post.image.name

        product = Product.objects.create(
            seller=self.user,
            name="画像出品",
            price=100,
            category="本",
        )
        product.image.save("del_product.gif", ContentFile(_MINIMAL_GIF), save=True)
        product_name = product.image.name

        other_profile, _ = UserProfile.objects.get_or_create(user=self.other)
        other_profile.avatar.save(
            "keep_avatar.gif", ContentFile(_MINIMAL_GIF), save=True
        )
        other_name = other_profile.avatar.name

        self.assertTrue(default_storage.exists(avatar_name))
        self.assertTrue(default_storage.exists(post_name))
        self.assertTrue(default_storage.exists(product_name))

        delete_user_account(self.user)

        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFalse(default_storage.exists(avatar_name))
        self.assertFalse(default_storage.exists(post_name))
        self.assertFalse(default_storage.exists(product_name))
        self.assertTrue(default_storage.exists(other_name))
        other_profile.avatar.delete(save=False)

    @patch("app.bookmark_services.get_firestore_client", return_value=None)
    def test_delete_account_skips_shared_image_name(self, _mock_client):
        product = Product.objects.create(
            seller=self.user,
            name="共有元",
            price=100,
            category="本",
        )
        product.image.save("shared.gif", ContentFile(_MINIMAL_GIF), save=True)
        shared_name = product.image.name

        other_product = Product.objects.create(
            seller=self.other,
            name="共有先",
            price=200,
            category="本",
        )
        other_product.image = shared_name
        other_product.save(update_fields=["image"])

        delete_user_account(self.user)

        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertTrue(default_storage.exists(shared_name))
        other_product.refresh_from_db()
        self.assertEqual(other_product.image.name, shared_name)
        other_product.image.delete(save=False)

    @patch("app.bookmark_services.get_firestore_client", return_value=None)
    def test_delete_account_succeeds_when_storage_delete_fails(self, _mock_client):
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.avatar.save(
            "storage_fail.gif", ContentFile(_MINIMAL_GIF), save=True
        )
        avatar_name = profile.avatar.name

        with patch(
            "django.core.files.storage.default_storage.delete",
            side_effect=OSError("cloudinary unavailable"),
        ):
            delete_user_account(self.user)

        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        if default_storage.exists(avatar_name):
            default_storage.delete(avatar_name)

    @patch("app.bookmark_services.get_firestore_client", return_value=None)
    def test_deletion_logs_do_not_include_email(self, _mock_client):
        email = self.user.email
        user_id = self.user.pk
        with self.assertLogs("app.account_deletion_services", level="INFO") as cm:
            delete_user_account(self.user)
        joined = "\n".join(cm.output)
        self.assertNotIn(email, joined)
        self.assertIn(f"user_id={user_id}", joined)

    @patch("app.bookmark_services.get_firestore_client", return_value=None)
    def test_delete_account_view_logs_do_not_include_email(self, _mock_client):
        email = self.user.email
        self.client.force_login(self.user)
        with self.assertLogs("app.views", level="INFO") as cm:
            response = self.client.post(
                reverse("delete_account"),
                {"confirm_delete": "DELETE"},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        joined = "\n".join(cm.output)
        self.assertNotIn(email, joined)
        self.assertFalse(get_user_model().objects.filter(email=email).exists())
