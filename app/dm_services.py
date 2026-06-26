"""ユーザー間 DM（UserDirectMessageRoom）のヘルパー。"""

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Prefetch, Q
from django.urls import reverse

from .models import UserDirectMessage, UserDirectMessageRoom


def ordered_user_pair(
    user1: AbstractBaseUser, user2: AbstractBaseUser
) -> tuple[AbstractBaseUser, AbstractBaseUser]:
    if user1.pk == user2.pk:
        raise ValueError("自分自身との DM ルームは作成できません。")
    if user1.pk < user2.pk:
        return user1, user2
    return user2, user1


def get_or_create_dm_room(
    user1: AbstractBaseUser, user2: AbstractBaseUser
) -> tuple[UserDirectMessageRoom, bool]:
    user_a, user_b = ordered_user_pair(user1, user2)
    return UserDirectMessageRoom.objects.get_or_create(user_a=user_a, user_b=user_b)


def find_dm_room(
    user1: AbstractBaseUser, user2: AbstractBaseUser
) -> UserDirectMessageRoom | None:
    try:
        user_a, user_b = ordered_user_pair(user1, user2)
    except ValueError:
        return None
    return UserDirectMessageRoom.objects.filter(user_a=user_a, user_b=user_b).first()


def can_access_dm_room(room: UserDirectMessageRoom, user: AbstractBaseUser) -> bool:
    if not user.is_authenticated:
        return False
    return room.involves_user(user)


def dm_room_link(room: UserDirectMessageRoom) -> str:
    return reverse("user_dm_room", kwargs={"room_pk": room.pk})


def list_dm_rooms_for_user(user: AbstractBaseUser):
    """ログインユーザーが参加する DM ルームを最新順で返す。"""
    latest_message = Prefetch(
        "messages",
        queryset=UserDirectMessage.objects.select_related("sender").order_by("-pk")[:1],
        to_attr="latest_messages",
    )
    return (
        UserDirectMessageRoom.objects.filter(Q(user_a=user) | Q(user_b=user))
        .select_related("user_a", "user_b", "user_a__profile", "user_b__profile")
        .prefetch_related(latest_message)
        .order_by("-updated_at")
    )


def build_dm_conversations(user: AbstractBaseUser) -> list[dict]:
    """インボックス表示用にルーム・相手・最新メッセージをまとめる。"""
    conversations = []
    for room in list_dm_rooms_for_user(user):
        partner = room.other_user(user)
        latest = room.latest_messages[0] if room.latest_messages else None
        conversations.append(
            {
                "room": room,
                "partner": partner,
                "latest_message": latest,
            }
        )
    return conversations
