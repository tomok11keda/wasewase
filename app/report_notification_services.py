"""通報受理時の運営向けメール通知。"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Comment, ContentReport, Product, TimelinePost

logger = logging.getLogger(__name__)


def _moderation_recipient() -> str:
    return (
        getattr(settings, "MODERATION_NOTIFICATION_EMAIL", "").strip()
        or "wasewaseofficial@gmail.com"
    )


def _from_email() -> str:
    from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if from_email:
        return from_email
    return (getattr(settings, "EMAIL_HOST_USER", "") or "").strip() or _moderation_recipient()


def _target_type_label(target_type: str) -> str:
    return dict(ContentReport.TargetType.choices).get(target_type, target_type)


def _reason_label(reason: str) -> str:
    return dict(ContentReport.Reason.choices).get(reason, reason)


def _build_target_summary(
    *,
    target_type: str,
    target_id: int,
    target,
    reported_user_id: int | None,
) -> str:
    lines = [
        f"対象種別: {_target_type_label(target_type)}",
        f"対象ID: {target_id}",
    ]

    if reported_user_id:
        lines.append(f"通報対象ユーザーID: {reported_user_id}")

    if target is None:
        lines.append("対象コンテンツ: （取得時点で未確認）")
        return "\n".join(lines)

    if target_type == ContentReport.TargetType.POST and isinstance(target, TimelinePost):
        lines.append(f"投稿本文（抜粋）: {target.body[:200]}")
        if target.author_id:
            lines.append(f"投稿者ユーザーID: {target.author_id}")
    elif target_type == ContentReport.TargetType.PRODUCT and isinstance(target, Product):
        lines.append(f"出品名: {target.name}")
        if target.seller_id:
            lines.append(f"出品者ユーザーID: {target.seller_id}")
    elif target_type == ContentReport.TargetType.COMMENT and isinstance(target, Comment):
        lines.append(f"コメント本文（抜粋）: {target.body[:200]}")
        if target.author_id:
            lines.append(f"コメント投稿者ユーザーID: {target.author_id}")
    elif target_type == ContentReport.TargetType.USER:
        lines.append(f"対象ユーザー名: {getattr(target, 'username', '')}")
        lines.append(f"対象ユーザーメール: {getattr(target, 'email', '')}")

    return "\n".join(lines)


def notify_moderation_team_of_report(
    report: ContentReport,
    *,
    target=None,
    reported_user_id: int | None = None,
) -> None:
    """通報内容を運営メールアドレスへ通知する。"""
    reporter = report.reporter
    recipient = _moderation_recipient()
    subject = (
        f"[わせわせ 通報] {_target_type_label(report.target_type)} "
        f"ID={report.target_id}"
    )
    body = (
        "わせわせで新しい通報が届きました。\n\n"
        "【通報者】\n"
        f"ユーザーID: {reporter.pk}\n"
        f"ユーザー名: {reporter.username}\n"
        f"メールアドレス: {reporter.email}\n\n"
        "【通報内容】\n"
        f"通報ID: {report.pk}\n"
        f"通報理由: {_reason_label(report.reason)}\n"
        f"詳細: {report.detail.strip() or '（未入力）'}\n"
        f"通報日時: {report.created_at:%Y-%m-%d %H:%M:%S}\n\n"
        "【通報対象】\n"
        f"{_build_target_summary(target_type=report.target_type, target_id=report.target_id, target=target, reported_user_id=reported_user_id)}\n\n"
        "管理画面またはデータベースで内容を確認し、24時間以内の対応を行ってください。"
    )

    send_mail(
        subject=subject,
        message=body,
        from_email=_from_email(),
        recipient_list=[recipient],
        fail_silently=False,
    )
    logger.info(
        "Moderation report email sent report_id=%s to=%s",
        report.pk,
        recipient,
    )
