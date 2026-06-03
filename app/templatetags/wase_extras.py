from django import template

from app.services import user_display_name

register = template.Library()


@register.filter
def display_name(user):
    """ユーザーのアプリ内表示名（ニックネーム）。"""
    return user_display_name(user)
