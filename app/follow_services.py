"""Follow / privacy / follow-request domain logic (shared by classic + API)."""

from __future__ import annotations

from typing import Any, Literal

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from .handle_services import public_username
from .models import Follow, FollowRequest, Notification, UserProfile
from .services import count_followers, is_following, user_display_name
from .spa_canonical import app_absolute
from .timetable_privacy_services import get_or_create_profile
from .ugc_services import is_either_blocked

FollowState = Literal["self", "following", "requested", "none", "blocked"]

# React Router path (basename=/app) for the follow-request inbox.
FOLLOW_REQUESTS_SPA_PATH = "/settings/follow-requests"


class FollowForbidden(Exception):
    """Block relationship — HTTP 403."""

    def __init__(self, code: str = "blocked"):
        self.code = code
        super().__init__(code)


def follow_requests_app_url() -> str:
    """Absolute site path for notifications (e.g. /app/settings/follow-requests)."""
    return app_absolute(FOLLOW_REQUESTS_SPA_PATH)


def is_account_private(owner: AbstractBaseUser | None) -> bool:
    if owner is None or not getattr(owner, "pk", None):
        return False
    profile = getattr(owner, "profile", None)
    if profile is None:
        profile = UserProfile.objects.filter(user_id=owner.pk).only("is_private").first()
    if profile is None:
        return False
    return bool(getattr(profile, "is_private", False))


def can_view_private_content(
    viewer: AbstractBaseUser | None,
    owner: AbstractBaseUser | None,
) -> bool:
    """Whether viewer may see owner's posts / products / private-gated content."""
    if owner is None:
        return True
    if (
        viewer is not None
        and getattr(viewer, "is_authenticated", False)
        and viewer.pk == owner.pk
    ):
        return True
    if is_either_blocked(viewer, owner):
        return False
    if not is_account_private(owner):
        return True
    if viewer is None or not getattr(viewer, "is_authenticated", False):
        return False
    return is_following(viewer, owner)


def get_follow_state(
    viewer: AbstractBaseUser | None,
    owner: AbstractBaseUser | None,
) -> FollowState:
    if owner is None:
        return "none"
    if viewer is None or not getattr(viewer, "is_authenticated", False):
        return "none"
    if viewer.pk == owner.pk:
        return "self"
    if is_either_blocked(viewer, owner):
        return "blocked"
    if is_following(viewer, owner):
        return "following"
    if FollowRequest.objects.filter(from_user=viewer, to_user=owner).exists():
        return "requested"
    return "none"


def can_view_timetable_for(
    viewer: AbstractBaseUser | None,
    owner: AbstractBaseUser,
    *,
    is_timetable_public: bool,
) -> bool:
    """本人、または（時間割公開 AND 非公開コンテンツ閲覧可）。"""
    if (
        viewer is not None
        and getattr(viewer, "is_authenticated", False)
        and viewer.pk == owner.pk
    ):
        return True
    if not is_timetable_public:
        return False
    return can_view_private_content(viewer, owner)


def _notify_followed(actor: AbstractBaseUser, target: AbstractBaseUser) -> None:
    from .spa_canonical import user_profile_url

    Notification.objects.create(
        recipient=target,
        message=f"「{actor.username}さんにフォローされました！」",
        link=user_profile_url(actor.pk),
    )


def _notify_follow_request(actor: AbstractBaseUser, target: AbstractBaseUser) -> None:
    Notification.objects.create(
        recipient=target,
        message=f"「{actor.username}さんからフォローリクエストが届きました」",
        link=follow_requests_app_url(),
    )


def toggle_follow_relationship(
    actor: AbstractBaseUser,
    target: AbstractBaseUser,
) -> dict[str, Any]:
    """Public follow / private request toggle. Raises ValueError or FollowForbidden."""
    if actor.pk == target.pk:
        raise ValueError("own_user")
    if is_either_blocked(actor, target):
        raise FollowForbidden("blocked")

    follow = Follow.objects.filter(follower=actor, following=target).first()
    if follow:
        follow.delete()
        FollowRequest.objects.filter(from_user=actor, to_user=target).delete()
        return {
            "ok": True,
            "is_following": False,
            "follow_state": "none",
            "follower_count": count_followers(target),
            "action": "unfollowed",
        }

    pending = FollowRequest.objects.filter(from_user=actor, to_user=target).first()
    if pending:
        pending.delete()
        return {
            "ok": True,
            "is_following": False,
            "follow_state": "none",
            "follower_count": count_followers(target),
            "action": "request_cancelled",
        }

    if is_account_private(target):
        try:
            FollowRequest.objects.create(from_user=actor, to_user=target)
        except IntegrityError as exc:
            raise ValueError("duplicate_request") from exc
        _notify_follow_request(actor, target)
        return {
            "ok": True,
            "is_following": False,
            "follow_state": "requested",
            "follower_count": count_followers(target),
            "action": "requested",
        }

    Follow.objects.create(follower=actor, following=target)
    _notify_followed(actor, target)
    return {
        "ok": True,
        "is_following": True,
        "follow_state": "following",
        "follower_count": count_followers(target),
        "action": "followed",
    }


def list_incoming_follow_requests(
    user: AbstractBaseUser,
) -> QuerySet[FollowRequest]:
    return (
        FollowRequest.objects.filter(to_user=user)
        .select_related("from_user", "from_user__profile")
        .order_by("-created_at")
    )


def serialize_follow_request(req: FollowRequest) -> dict[str, Any]:
    from .services import get_user_avatar_url, user_avatar_initial

    u = req.from_user
    return {
        "id": req.pk,
        "created_at": req.created_at.isoformat(),
        "from_user": {
            "id": u.pk,
            "username": public_username(u),
            "display_name": user_display_name(u),
            "avatar_url": get_user_avatar_url(u) or "",
            "initial": user_avatar_initial(u),
        },
    }


@transaction.atomic
def accept_follow_request(
    recipient: AbstractBaseUser,
    request_id: int,
) -> dict[str, Any]:
    try:
        req = (
            FollowRequest.objects.select_for_update()
            .select_related("from_user")
            .get(pk=request_id, to_user=recipient)
        )
    except FollowRequest.DoesNotExist as exc:
        raise ValueError("not_found") from exc

    actor = req.from_user
    if is_either_blocked(recipient, actor):
        req.delete()
        raise FollowForbidden("blocked")

    Follow.objects.get_or_create(follower=actor, following=recipient)
    req.delete()
    # Clean any reverse pending noise
    FollowRequest.objects.filter(from_user=actor, to_user=recipient).delete()
    _notify_followed(actor, recipient)
    return {
        "ok": True,
        "action": "accepted",
        "follower_count": count_followers(recipient),
        "from_user_id": actor.pk,
    }


@transaction.atomic
def reject_follow_request(
    recipient: AbstractBaseUser,
    request_id: int,
) -> dict[str, Any]:
    deleted, _ = FollowRequest.objects.filter(
        pk=request_id, to_user=recipient
    ).delete()
    if not deleted:
        raise ValueError("not_found")
    return {"ok": True, "action": "rejected"}


@transaction.atomic
def set_account_privacy(
    user: AbstractBaseUser,
    *,
    is_private: bool,
) -> dict[str, Any]:
    profile = get_or_create_profile(user)
    was_private = bool(getattr(profile, "is_private", False))
    profile.is_private = bool(is_private)
    profile.save(update_fields=["is_private"])

    auto_accepted = 0
    if was_private and not is_private:
        # Private → public: convert pending requests into Follow (no notify flood).
        pending = list(
            FollowRequest.objects.select_for_update()
            .filter(to_user=user)
            .select_related("from_user")
        )
        for req in pending:
            if is_either_blocked(user, req.from_user):
                req.delete()
                continue
            Follow.objects.get_or_create(
                follower=req.from_user, following=user
            )
            req.delete()
            auto_accepted += 1

    return {
        "ok": True,
        "is_private": bool(profile.is_private),
        "auto_accepted_requests": auto_accepted,
    }
