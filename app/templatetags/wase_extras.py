from django import template

from app.mention_services import linkify_mentions as render_mentions_html
from app.services import get_user_avatar_url, user_avatar_initial, user_display_name

register = template.Library()


@register.filter
def display_name(user):
    """ユーザーのアプリ内表示名（ニックネーム）。"""
    return user_display_name(user)


@register.inclusion_tag("includes/user_avatar.html")
def render_user_avatar(user, size=36, extra_class=""):
    """プロフィール画像、または頭文字アバターを表示。"""
    avatar_url = get_user_avatar_url(user)
    return {
        "avatar_url": avatar_url,
        "initial": user_avatar_initial(user),
        "alt_text": user_display_name(user),
        "size": size,
        "extra_class": extra_class,
    }


@register.filter
def linkify_mentions(text):
    """投稿・コメント本文内の @handle をプロフィールリンクに変換する。"""
    return render_mentions_html(text)
