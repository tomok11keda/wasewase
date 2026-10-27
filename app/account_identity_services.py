"""Linked personal profiles: one login identity, multiple User rows."""

from __future__ import annotations

from typing import Any, Iterable

from django.contrib.auth import login
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from .handle_services import clean_unique_handle, public_username
from .models import AccountIdentity, User, UserProfile
from .organization_services import (
    assert_users_can_be_deleted_without_orphaning_organizations,
)
from .timetable_privacy_services import get_or_create_profile

# Raise this to allow more personal profiles per person. Create/switch APIs,
# can_add, and user-facing copy read this constant. Do not scatter literals.
MAX_LINKED_PROFILES = 2
AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"


def linked_profile_limit_message() -> str:
    return f"アカウントは{MAX_LINKED_PROFILES}つまでです。"


class AccountIdentityError(Exception):
    def __init__(self, code: str, *, status: int = 400, message: str = ""):
        self.code = code
        self.status = status
        self.message = message or code
        super().__init__(self.message)


def linked_user_ids(user: AbstractBaseUser | None) -> set[int]:
    if user is None or not getattr(user, "pk", None):
        return set()
    identity_id = getattr(user, "identity_id", None)
    if not identity_id:
        return {int(user.pk)}
    return set(
        User.objects.filter(identity_id=identity_id).values_list("pk", flat=True)
    )


def same_person(
    user_a: AbstractBaseUser | None, user_b: AbstractBaseUser | None
) -> bool:
    if user_a is None or user_b is None:
        return False
    if not getattr(user_a, "pk", None) or not getattr(user_b, "pk", None):
        return False
    if user_a.pk == user_b.pk:
        return True
    a_id = getattr(user_a, "identity_id", None)
    b_id = getattr(user_b, "identity_id", None)
    return bool(a_id and b_id and a_id == b_id)


def credential_user(user: User) -> User:
    """The profile that holds university email + password hash."""
    if (user.email or "").strip():
        return user
    identity_id = getattr(user, "identity_id", None)
    if not identity_id:
        return user
    holder = (
        User.objects.filter(identity_id=identity_id)
        .exclude(email__isnull=True)
        .exclude(email="")
        .order_by("pk")
        .first()
    )
    return holder or user


def ensure_identity(user: User) -> AccountIdentity:
    if user.identity_id:
        identity = user.identity
        if identity is not None:
            return identity
    identity = AccountIdentity.objects.create()
    user.identity = identity
    user.save(update_fields=["identity"])
    return identity


def linked_users(user: User) -> list[User]:
    identity_id = getattr(user, "identity_id", None)
    if not identity_id:
        return [user]
    return list(
        User.objects.filter(identity_id=identity_id)
        .select_related("profile")
        .order_by("pk")
    )


def _display_name(user: User) -> str:
    profile = getattr(user, "profile", None)
    name = (getattr(profile, "name", None) or "").strip()
    if name:
        return name
    return public_username(user) or "ユーザー"


def _avatar_url(user: User) -> str:
    profile = getattr(user, "profile", None)
    avatar = getattr(profile, "avatar", None) if profile is not None else None
    if avatar:
        try:
            return avatar.url
        except ValueError:
            pass
    return ""


def serialize_linked_profile(user: User, *, current_id: int) -> dict[str, Any]:
    display = _display_name(user)
    return {
        "id": user.pk,
        "username": public_username(user),
        "display_name": display,
        "avatar_url": _avatar_url(user),
        "initial": (display[:1] or "?").upper(),
        "is_current": user.pk == current_id,
        "is_credential": bool((user.email or "").strip()),
    }


def serialize_linked_profiles_payload(user: User) -> dict[str, Any]:
    profiles = linked_users(user)
    return {
        "ok": True,
        "profiles": [
            serialize_linked_profile(item, current_id=user.pk) for item in profiles
        ],
        "can_add": len(profiles) < MAX_LINKED_PROFILES,
        "max": MAX_LINKED_PROFILES,
    }


def _login_as(request: HttpRequest, user: User) -> None:
    user.backend = getattr(user, "backend", None) or AUTH_BACKEND
    login(request, user, backend=user.backend)


def switch_linked_profile(request: HttpRequest, target_user_id: int) -> User:
    actor = request.user
    if not actor.is_authenticated:
        raise AccountIdentityError("unauthorized", status=401)
    try:
        target_id = int(target_user_id)
    except (TypeError, ValueError) as exc:
        raise AccountIdentityError("invalid_user") from exc
    target = User.objects.filter(pk=target_id, is_active=True).first()
    if target is None:
        raise AccountIdentityError("not_found", status=404)
    if not same_person(actor, target):
        raise AccountIdentityError("forbidden", status=403, message="切り替えできません。")
    if target.pk != actor.pk:
        _login_as(request, target)
    return target


def create_linked_profile(
    actor: User,
    *,
    username: str,
    display_name: str,
) -> User:
    if not actor.is_authenticated:
        raise AccountIdentityError("unauthorized", status=401)
    try:
        handle = clean_unique_handle(username)
    except ValidationError as exc:
        raise AccountIdentityError(
            "invalid_username",
            message=exc.messages[0] if exc.messages else "ユーザー名が不正です。",
        ) from exc
    name = (display_name or "").strip()
    if not name:
        raise AccountIdentityError("invalid_name", message="表示名を入力してください。")
    if len(name) > 80:
        raise AccountIdentityError("invalid_name", message="表示名が長すぎます。")

    with transaction.atomic():
        identity = ensure_identity(actor)
        locked = User.objects.select_for_update().filter(identity=identity)
        if locked.count() >= MAX_LINKED_PROFILES:
            raise AccountIdentityError(
                "limit_reached",
                message=linked_profile_limit_message(),
            )
        parent_profile = get_or_create_profile(actor)
        alt = User(
            email=None,
            username=handle,
            identity=identity,
            is_active=True,
            is_staff=False,
            is_superuser=False,
            is_operator_verified=False,
        )
        alt.set_unusable_password()
        alt.save()
        now = timezone.now()
        UserProfile.objects.update_or_create(
            user=alt,
            defaults={
                "name": name,
                "department": parent_profile.department or "",
                "grade": parent_profile.grade or "",
                "terms_accepted": bool(parent_profile.terms_accepted),
                "terms_accepted_at": parent_profile.terms_accepted_at,
                "terms_version": parent_profile.terms_version or "",
                "onboarding_step": UserProfile.ONBOARDING_STEP_WELCOME,
                "onboarding_completed_at": now,
                "onboarding_exempt": True,
            },
        )
    return alt


def _move_credentials(source: User, destination: User) -> None:
    email = source.email
    password = source.password
    source.email = None
    source.set_unusable_password()
    source.save(update_fields=["email", "password"])
    destination.email = email
    destination.password = password
    destination.save(update_fields=["email", "password"])


def delete_current_linked_profile(request: HttpRequest) -> User | None:
    """Delete the current profile. Returns remaining user, or None if fully gone."""
    from .account_deletion_services import SuperuserDeletionDenied, delete_user_account

    actor = request.user
    if not actor.is_authenticated:
        raise AccountIdentityError("unauthorized", status=401)
    if getattr(actor, "is_superuser", False):
        raise SuperuserDeletionDenied()
    others = [item for item in linked_users(actor) if item.pk != actor.pk]
    remaining = others[0] if others else None
    identity_id = actor.identity_id
    with transaction.atomic():
        assert_users_can_be_deleted_without_orphaning_organizations([actor.pk])
        if remaining is not None and (actor.email or "").strip() and not (
            remaining.email or ""
        ).strip():
            _move_credentials(actor, remaining)
        delete_user_account(actor)
        if remaining is None and identity_id:
            AccountIdentity.objects.filter(pk=identity_id).delete()
    if remaining is not None:
        remaining = User.objects.filter(pk=remaining.pk, is_active=True).first()
        if remaining is not None:
            _login_as(request, remaining)
    return remaining


def delete_entire_identity(request: HttpRequest) -> None:
    from .account_deletion_services import SuperuserDeletionDenied, delete_user_account

    actor = request.user
    if not actor.is_authenticated:
        raise AccountIdentityError("unauthorized", status=401)
    members = linked_users(actor)
    if any(getattr(item, "is_superuser", False) for item in members):
        raise SuperuserDeletionDenied()
    assert_users_can_be_deleted_without_orphaning_organizations(
        item.pk for item in members
    )
    identity = actor.identity
    # Delete non-credential profiles first so login email survives until the last row.
    ordered = sorted(
        members,
        key=lambda item: (1 if (item.email or "").strip() else 0, item.pk),
    )
    for item in ordered:
        delete_user_account(item)
    if identity is not None:
        AccountIdentity.objects.filter(pk=identity.pk).delete()


def authenticate_identifier(identifier: str, password: str) -> User | None:
    """Email → credential user. Username → that profile, password checked on credential."""
    ident = (identifier or "").strip()
    if not ident or not password:
        return None
    if "@" in ident:
        user = User.objects.filter(email__iexact=ident.lower(), is_active=True).first()
        if user is None:
            return None
        cred = credential_user(user)
        if not cred.has_usable_password() or not cred.check_password(password):
            return None
        return cred

    user = User.objects.filter(username__iexact=ident, is_active=True).first()
    if user is None:
        return None
    cred = credential_user(user)
    if not cred.has_usable_password() or not cred.check_password(password):
        return None
    return user


def expand_user_ids(ids: Iterable[int]) -> set[int]:
    base = {int(item) for item in ids if item}
    if not base:
        return set()
    identity_ids = list(
        User.objects.filter(pk__in=base)
        .exclude(identity_id=None)
        .values_list("identity_id", flat=True)
    )
    if not identity_ids:
        return base
    return base | set(
        User.objects.filter(identity_id__in=identity_ids).values_list("pk", flat=True)
    )


def users_matching_block_subjects(
    users: Iterable[AbstractBaseUser],
) -> set[int]:
    ids: set[int] = set()
    for user in users:
        ids.update(linked_user_ids(user))
    return ids
