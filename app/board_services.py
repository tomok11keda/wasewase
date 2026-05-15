from datetime import datetime

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from .models import GodButtonUse

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
