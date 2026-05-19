"""
Gmail SMTP 用のメール設定。

組み込み設定（WASE_BUILTIN_EMAIL）が最優先。
環境変数はフォールバックとしてのみ参照し、全角プレースホルダーは無視する。
"""

from __future__ import annotations

import re
import sys

# 起動時・読み込み時に蓄積する警告（settings / views で表示）
EMAIL_ENV_WARNINGS: list[str] = []

# ---------------------------------------------------------------------------
# わせわせ公式 Gmail（最優先・環境変数より常に優先）
# ---------------------------------------------------------------------------
WASE_USE_BUILTIN_GMAIL = True

WASE_BUILTIN_EMAIL = {
    "host_user": "wasewaseofficial@gmail.com",
    "host_password": "qqxwgfaweaclghbv",
    "default_from": "わせわせ公式 <wasewaseofficial@gmail.com>",
}

# 明らかにプレースホルダーと分かる部分文字列（小文字比較）
_PLACEHOLDER_MARKERS = (
    "あなたの",
    "プレースホルダ",
    "さっき取得",
    "ここに",
    "your@",
    "you@gmail",
    "example.com",
    "xxxx",
    "xxxx xxxx",
    "@example.com",
)

_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)
_APP_PASSWORD_RE = re.compile(r"^[a-zA-Z0-9]{8,32}$")
_FROM_HEADER_RE = re.compile(
    r"^(.+?)\s*<([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})>\s*$"
)


def _log_warning(message: str) -> None:
    EMAIL_ENV_WARNINGS.append(message)
    print(f"[WASE EMAIL ENV] {message}", file=sys.stderr, flush=True)


def _log_info(message: str) -> None:
    print(f"[WASE EMAIL ENV] {message}", file=sys.stderr, flush=True)


def is_ascii_only(value: str) -> bool:
    if not value:
        return True
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in value or marker in lowered for marker in _PLACEHOLDER_MARKERS)


def is_plausible_email(value: str) -> bool:
    if not value or not is_ascii_only(value):
        return False
    if "@" not in value:
        return False
    if looks_like_placeholder(value):
        return False
    return bool(_EMAIL_RE.match(value))


def is_plausible_from_header(value: str) -> bool:
    """'表示名 <email@example.com>' またはプレーンなメールアドレス。"""
    cleaned = (value or "").strip()
    if not cleaned:
        return False
    if is_plausible_email(cleaned):
        return True
    match = _FROM_HEADER_RE.match(cleaned)
    if not match:
        return False
    return is_plausible_email(match.group(2))


def is_plausible_app_password(value: str) -> bool:
    if not value or not is_ascii_only(value):
        return False
    if looks_like_placeholder(value):
        return False
    return bool(_APP_PASSWORD_RE.match(value))


def sanitize_email_address(raw: str, env_name: str) -> str:
    """メールアドレス環境変数を ASCII の妥当な形式だけ残す。"""
    cleaned = (raw or "").strip()
    if not cleaned:
        return ""

    if not is_plausible_email(cleaned):
        reason = []
        if not is_ascii_only(cleaned):
            reason.append("ASCII以外の文字を含む")
        elif "@" not in cleaned:
            reason.append("@ が無い")
        elif looks_like_placeholder(cleaned):
            reason.append("プレースホルダー文字列")
        else:
            reason.append("形式が不正")
        _log_warning(
            f"{env_name} を無効と判断しました（{', '.join(reason)}）。"
            " 値は使用しません。"
        )
        return ""

    return cleaned


def sanitize_from_header(raw: str, env_name: str) -> str:
    cleaned = (raw or "").strip()
    if not cleaned:
        return ""
    if is_plausible_from_header(cleaned):
        return cleaned
    _log_warning(f"{env_name} を無効と判断しました。値は使用しません。")
    return ""


def sanitize_app_password(raw: str, env_name: str) -> str:
    """Gmail アプリパスワード（半角英数）のみ受け付ける。"""
    cleaned = (raw or "").strip().replace(" ", "")
    if not cleaned:
        return ""

    if not is_plausible_app_password(cleaned):
        reason = []
        if not is_ascii_only(cleaned):
            reason.append("ASCII以外の文字を含む")
        elif looks_like_placeholder(cleaned):
            reason.append("プレースホルダー文字列")
        else:
            reason.append("形式が不正（半角英数8〜32文字）")
        _log_warning(
            f"{env_name} を無効と判断しました（{', '.join(reason)}）。"
            " 値は使用しません。"
        )
        return ""

    return cleaned


def load_builtin_gmail_config() -> tuple[str, str, str, bool]:
    """組み込み Gmail 設定を返す（常に SMTP 送信可能）。"""
    user = WASE_BUILTIN_EMAIL["host_user"]
    password = WASE_BUILTIN_EMAIL["host_password"]
    default_from = WASE_BUILTIN_EMAIL["default_from"]

    if not is_plausible_email(user) or not is_plausible_app_password(password):
        _log_warning("組み込み Gmail 設定の形式が不正です。SMTP を無効化します。")
        return "", "", "noreply@wasewase.local", False

    if not is_plausible_from_header(default_from):
        default_from = user

    return user, password, default_from, True


def load_sanitized_email_env(
    raw_user: str,
    raw_password: str,
    raw_from: str,
) -> tuple[str, str, str, bool]:
    """
    メール設定を読み込む。組み込み設定が最優先。

    Returns:
        (host_user, host_password, default_from_email, smtp_ready)
    """
    EMAIL_ENV_WARNINGS.clear()

    if WASE_USE_BUILTIN_GMAIL:
        _log_info(
            "組み込み Gmail 設定を使用します（送信元: wasewaseofficial@gmail.com）。"
            " 環境変数の値は無視されます。"
        )
        return load_builtin_gmail_config()

    host_user = sanitize_email_address(raw_user, "WASE_EMAIL_HOST_USER")
    host_password = sanitize_app_password(raw_password, "WASE_EMAIL_HOST_PASSWORD")
    default_from = sanitize_from_header(raw_from, "WASE_DEFAULT_FROM_EMAIL")

    if not default_from and host_user:
        default_from = host_user
    if not default_from:
        default_from = "noreply@wasewase.local"

    smtp_ready = bool(host_user and host_password)
    return host_user, host_password, default_from, smtp_ready
