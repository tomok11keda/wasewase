from urllib.parse import quote

from django.contrib.auth.models import AbstractBaseUser
from django.urls import reverse
from django.utils import timezone

from .models import GodButtonUse, Notification, TimelinePost

GOD_USES_PER_MONTH = 3


def god_uses_this_month(user: AbstractBaseUser) -> int:
    now = timezone.now()
    return GodButtonUse.objects.filter(
        user=user,
        created_at__year=now.year,
        created_at__month=now.month,
    ).count()


def god_uses_remaining(user: AbstractBaseUser) -> int:
    return max(0, GOD_USES_PER_MONTH - god_uses_this_month(user))


def can_use_god_button(user: AbstractBaseUser) -> bool:
    return user.is_authenticated and god_uses_remaining(user) > 0


def timeline_post_link(post: TimelinePost) -> str:
    return f"{reverse('home')}?tab=board&tag={quote(post.course_name)}"


def notify_timeline_post_author(
    post: TimelinePost,
    actor: AbstractBaseUser,
    message: str,
) -> None:
    if not post.author_id:
        return
    if actor.is_authenticated and actor.id == post.author_id:
        return
    Notification.objects.create(
        recipient=post.author,
        message=message,
        link=timeline_post_link(post),
    )
