import logging
import secrets
import sys
import traceback
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail

from django.utils import timezone

from .models import SignupOTP

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_VALID_MINUTES = 10
SIGNUP_PENDING_SESSION_KEY = "signup_pending_user_id"


class EmailConfigurationError(Exception):
    """Gmail SMTP の環境変数が未設定または不正なとき。"""


def _ascii_safe_email(address: str) -> str:
    """SMTP エンベロープ用に ASCII のみのアドレスを返す。"""
    address = (address or "").strip()
    if not address:
        return "noreply@wasewase.local"
    try:
        address.encode("ascii")
        return address
    except UnicodeEncodeError:
        return "noreply@wasewase.local"


def get_email_config_errors() -> list[str]:
    if getattr(settings, "EMAIL_USE_CONSOLE_FALLBACK", False):
        return []

    if getattr(settings, "EMAIL_USE_BUILTIN_GMAIL", False) and getattr(
        settings, "EMAIL_SMTP_READY", False
    ):
        return []

    backend = getattr(settings, "EMAIL_BACKEND", "")
    smtp_backends = (
        "django.core.mail.backends.smtp.EmailBackend",
        "wasewase.settings.UnverifiedTTLEmailBackend",
    )
    if backend not in smtp_backends:
        return []

    errors = []
    if not getattr(settings, "EMAIL_USE_BUILTIN_GMAIL", False):
        warnings = getattr(settings, "EMAIL_ENV_WARNINGS", [])
        if warnings:
            errors.append(
                "メール設定の環境変数にプレースホルダーや全角文字が含まれていました。"
                " ターミナルの [WASE EMAIL ENV] ログを確認してください。"
            )

    if not getattr(settings, "EMAIL_SMTP_READY", False):
        errors.append(
            "WASE_EMAIL_HOST_USER / WASE_EMAIL_HOST_PASSWORD が未設定または無効です。"
            " 開発中はターミナル出力（console backend）に自動切替されます。"
        )
    return errors


def assert_email_configured() -> None:
    if getattr(settings, "EMAIL_USE_CONSOLE_FALLBACK", False):
        return

    errors = get_email_config_errors()
    if errors:
        message = "メール送信設定エラー: " + " ".join(errors)
        logger.error(message)
        if settings.DEBUG:
            print(f"[WASE EMAIL CONFIG] {message}", file=sys.stderr, flush=True)
        raise EmailConfigurationError(message)


def generate_otp_code() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))


def create_and_send_signup_otp(user) -> str:
    """OTPを生成・保存しメール送信する。戻り値は平文コード（テスト用）。"""
    assert_email_configured()

    code = generate_otp_code()
    expires_at = timezone.now() + timedelta(minutes=OTP_VALID_MINUTES)
    SignupOTP.objects.update_or_create(
        user=user,
        defaults={
            "code_hash": make_password(code),
            "expires_at": expires_at,
        },
    )

    from_email = (settings.DEFAULT_FROM_EMAIL or "").strip()
    if not from_email:
        from_email = settings.EMAIL_HOST_USER
    recipient = _ascii_safe_email(user.email)
    use_console = getattr(settings, "EMAIL_USE_CONSOLE_FALLBACK", False)

    logger.info(
        "Sending signup OTP to %s via %s (console=%s, from=%s)",
        recipient,
        settings.EMAIL_BACKEND,
        use_console,
        from_email,
    )

    subject = "【わせわせ】新規登録の認証コード"
    body = (
        f"わせわせへのご登録ありがとうございます。\n\n"
        f"認証コード: {code}\n"
        f"有効期限: {OTP_VALID_MINUTES}分\n\n"
        f"このメールに心当たりがない場合は破棄してください。"
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except UnicodeEncodeError as exc:
        logger.exception("UnicodeEncodeError while sending OTP to %s", recipient)
        if settings.DEBUG:
            traceback.print_exc()
        raise EmailConfigurationError(
            "メール送信時に文字コードエラーが発生しました。"
            " 環境変数に日本語のプレースホルダーが残っていないか確認してください。"
        ) from exc
    except Exception as exc:
        logger.exception("SMTP send failed for %s", recipient)
        if settings.DEBUG:
            print(
                f"[WASE EMAIL SEND FAILED] to={recipient} error={exc}",
                file=sys.stderr,
                flush=True,
            )
            traceback.print_exc()
        raise

    logger.info("Signup OTP sent to %s", recipient)
    if settings.DEBUG:
        backend_note = (
            " (console backend — ターミナルを確認)"
            if use_console
            else ""
        )
        print(
            f"[WASE EMAIL SENT] to={recipient} from={from_email}{backend_note}",
            flush=True,
        )
    return code


def verify_signup_otp(user, code: str) -> str | None:
    """成功時は None、失敗時はエラーメッセージを返す。"""
    try:
        otp = SignupOTP.objects.get(user=user)
    except SignupOTP.DoesNotExist:
        return "認証コードが見つかりません。新規登録からやり直してください。"

    if timezone.now() > otp.expires_at:
        otp.delete()
        return "認証コードの有効期限が切れました。「認証コードを再送信」から新しいコードを取得してください。"

    if not check_password(code, otp.code_hash):
        return "認証コードが正しくありません。"

    otp.delete()
    return None
