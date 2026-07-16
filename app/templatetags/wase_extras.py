from django import template

from app.mention_services import linkify_mentions as render_mentions_html
from app.services import get_user_avatar_url, user_avatar_initial, user_display_name

DELETED_TIMELINE_AUTHOR_LABEL = "退会済みユーザー"


register = template.Library()


@register.filter
def display_name(user):
    """ユーザーのアプリ内表示名（ニックネーム）。"""
    return user_display_name(user)


@register.filter
def timeline_author_label(author):
    """タイムライン投稿者の表示名。退会済みは専用ラベル。"""
    if author is None:
        return DELETED_TIMELINE_AUTHOR_LABEL
    return user_display_name(author)


@register.simple_tag
def deleted_timeline_author_label():
    return DELETED_TIMELINE_AUTHOR_LABEL


@register.inclusion_tag("includes/user_avatar.html")
def render_user_avatar(user, size=36, extra_class="", fallback="initial"):
    """プロフィール画像、またはフォールバック（頭文字 / person アイコン）を表示。"""
    avatar_url = get_user_avatar_url(user)
    return {
        "avatar_url": avatar_url,
        "initial": user_avatar_initial(user),
        "alt_text": user_display_name(user),
        "size": size,
        "extra_class": extra_class,
        "fallback": fallback or "initial",
    }


@register.filter
def linkify_mentions(text):
    """投稿・コメント本文内の @handle をプロフィールリンクに変換する。"""
    return render_mentions_html(text)
