from django import template

from app.mention_services import linkify_mentions as render_mentions_html
from app.services import user_display_name

register = template.Library()


@register.filter
def display_name(user):
    """ユーザーのアプリ内表示名（ニックネーム）。"""
    return user_display_name(user)


@register.filter
def linkify_mentions(text):
    """投稿・コメント本文内の @handle をプロフィールリンクに変換する。"""
    return render_mentions_html(text)
