"""ユーザー間 DM（UserDirectMessageRoom）のヘルパー。"""

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Prefetch, Q
from django.urls import reverse

from .models import UserDirectMessage, UserDirectMessageReadState, UserDirectMessageRoom


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


def get_dm_read_state_map(
    user: AbstractBaseUser, room_ids: list[int]
) -> dict[int, int]:
    if not room_ids:
        return {}
    return {
        room_id: last_read_id
        for room_id, last_read_id in UserDirectMessageReadState.objects.filter(
            user=user,
            room_id__in=room_ids,
        ).values_list("room_id", "last_read_message_id")
    }


def count_unread_dm_messages(
    room: UserDirectMessageRoom,
    user: AbstractBaseUser,
    last_read_message_id: int = 0,
) -> int:
    return (
        UserDirectMessage.objects.filter(room=room, pk__gt=last_read_message_id)
        .exclude(sender_id=user.pk)
        .count()
    )


def get_unread_dm_counts_for_rooms(
    user: AbstractBaseUser, rooms: list[UserDirectMessageRoom]
) -> dict[int, int]:
    room_ids = [room.pk for room in rooms]
    read_map = get_dm_read_state_map(user, room_ids)
    return {
        room.pk: count_unread_dm_messages(
            room,
            user,
            read_map.get(room.pk, 0),
        )
        for room in rooms
    }


def mark_dm_room_read(
    room: UserDirectMessageRoom, user: AbstractBaseUser
) -> int:
    latest_id = (
        UserDirectMessage.objects.filter(room=room)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
        or 0
    )
    UserDirectMessageReadState.objects.update_or_create(
        room=room,
        user=user,
        defaults={"last_read_message_id": latest_id},
    )
    return latest_id


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
    """インボックス表示用にルーム・相手・最新メッセージ・未読件数をまとめる。"""
    rooms = list(list_dm_rooms_for_user(user))
    unread_map = get_unread_dm_counts_for_rooms(user, rooms)
    conversations = []
    for room in rooms:
        partner = room.other_user(user)
        latest = room.latest_messages[0] if room.latest_messages else None
        conversations.append(
            {
                "room": room,
                "partner": partner,
                "latest_message": latest,
                "unread_count": unread_map.get(room.pk, 0),
            }
        )
    return conversations


def build_dm_unread_summary(user: AbstractBaseUser) -> dict:
    conversations = build_dm_conversations(user)
    rooms = [
        {"room_pk": item["room"].pk, "unread_count": item["unread_count"]}
        for item in conversations
        if item["unread_count"] > 0
    ]
    return {
        "total_unread": sum(item["unread_count"] for item in rooms),
        "rooms": rooms,
    }
