"""ユーザー間 DM（UserDirectMessageRoom）のヘルパー。"""

from django.contrib.auth.models import AbstractBaseUser
from django.urls import reverse

from .models import UserDirectMessageRoom


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
