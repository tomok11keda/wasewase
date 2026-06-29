"""タイムライン画像アップロードの検証・診断ログ。"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

MAX_TIMELINE_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }
)
ALLOWED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
HEIC_EXTENSIONS = frozenset({".heic", ".heif"})
ORPHAN_TIMELINEPOST_COLUMNS = frozenset(
    {"god_count", "gad_count", "tip_total"},
)


def log_timelinepost_db_schema() -> None:
    """本番 DB とモデル定義の差分をログに出す。"""
    from django.apps import apps
    from django.db import connection

    model = apps.get_model("app", "TimelinePost")
    model_columns = {field.column for field in model._meta.local_fields}
    table = model._meta.db_table

    try:
        with connection.cursor() as cursor:
            db_columns = {
                column.name: column
                for column in connection.introspection.get_table_description(
                    cursor, table
                )
            }
    except Exception as exc:
        log_media_upload("DB SCHEMA", f"{table} introspection failed: {exc}", exc=exc)
        return

    col_summary = ", ".join(
        f"{name}(null_ok={not col.null_ok}, default={col.default!r})"
        for name, col in sorted(db_columns.items())
    )
    log_media_upload("DB SCHEMA", f"{table} columns=[{col_summary}]")

    missing_in_db = sorted(model_columns - set(db_columns.keys()))
    extra_in_db = sorted(set(db_columns.keys()) - model_columns)
    orphan_not_null = sorted(
        name
        for name in extra_in_db
        if name in ORPHAN_TIMELINEPOST_COLUMNS and not db_columns[name].null_ok
    )
    if missing_in_db:
        log_media_upload("DB SCHEMA", f"missing_in_db={missing_in_db}")
    if extra_in_db:
        log_media_upload("DB SCHEMA", f"extra_in_db={extra_in_db}")
    if orphan_not_null:
        log_media_upload(
            "DB SCHEMA",
            f"orphan_not_null_columns={orphan_not_null} "
            "(モデルに無い NOT NULL カラムが INSERT 失敗の原因になります)",
        )


def rewind_file_field(field_file) -> None:
    """バリデーション後にファイルポインタを先頭へ戻す。"""
    if not field_file:
        return
    try:
        if hasattr(field_file, "seek"):
            field_file.seek(0)
            log_media_upload("IMAGE REWIND", "field_file.seek(0) ok")
            return
        inner = getattr(field_file, "file", None)
        if inner is not None and hasattr(inner, "seek"):
            inner.seek(0)
            log_media_upload("IMAGE REWIND", "field_file.file.seek(0) ok")
    except (OSError, ValueError) as exc:
        log_media_upload("IMAGE REWIND", f"failed: {exc}", exc=exc)


def prepare_image_field_for_save(post) -> None:
    if not getattr(post, "image", None):
        return
    log_media_upload(
        "IMAGE SAVE PREP",
        (
            f"name={getattr(post.image, 'name', '')!r} "
            f"size={getattr(post.image, 'size', '?')} "
            f"closed={getattr(post.image, 'closed', '?')}"
        ),
    )
    rewind_file_field(post.image)


def compose_save_error_message(exc: BaseException) -> str:
    """ユーザー向けの保存失敗メッセージ（詳細はログへ）。"""
    exc_name = type(exc).__qualname__
    exc_text = str(exc)
    if exc_name == "IntegrityError" or "IntegrityError" in exc_name:
        return (
            "投稿の保存に失敗しました（データベース制約エラー）。"
            " しばらくしてから再度お試しください。"
        )
    lowered = exc_text.lower()
    if "cloudinary" in lowered or exc_name.endswith("CloudinaryException"):
        return (
            "投稿の保存に失敗しました（画像アップロード先の設定を確認してください）。"
        )
    if "suspiciousoperation" in exc_name.lower() or "invalid image" in lowered:
        return "投稿の保存に失敗しました。画像形式を JPEG / PNG に変換してお試しください。"
    if "oserror" in exc_name.lower() or "permission" in lowered:
        return "投稿の保存に失敗しました（画像の保存先に書き込めません）。"
    return "投稿の保存に失敗しました。しばらくしてから再度お試しください。"


def log_media_upload(
    label: str,
    detail: str,
    *,
    exc: BaseException | None = None,
) -> None:
    """画像アップロード診断ログ（本番 Render でも stderr に出力）。"""
    message = f"[WASE {label}] {detail}"
    logger.warning(message, exc_info=exc)
    print(message, file=sys.stderr, flush=True)
    if exc:
        traceback.print_exc(file=sys.stderr)


def describe_uploaded_file(uploaded_file) -> str:
    if not uploaded_file:
        return "file=None"
    return (
        f"name={getattr(uploaded_file, 'name', '?')!r} "
        f"size={getattr(uploaded_file, 'size', '?')} "
        f"content_type={getattr(uploaded_file, 'content_type', '')!r} "
        f"charset={getattr(uploaded_file, 'charset', '')!r}"
    )


def log_compose_request(request) -> None:
    files_summary = [
        f"{key}={describe_uploaded_file(uploaded_file)}"
        for key, uploaded_file in request.FILES.items()
    ]
    log_media_upload(
        "BOARD COMPOSE REQUEST",
        (
            f"user_id={getattr(request.user, 'pk', None)} "
            f"POST_keys={list(request.POST.keys())} "
            f"FILES_keys={list(request.FILES.keys())} "
            f"FILES=[{'; '.join(files_summary) or 'none'}] "
            f"content_length={request.META.get('CONTENT_LENGTH', '?')} "
            f"content_type={request.META.get('CONTENT_TYPE', '?')}"
        ),
    )


def log_media_storage_status() -> None:
    backend = settings.STORAGES["default"]["BACKEND"]
    use_cloudinary = getattr(settings, "USE_CLOUDINARY", False)
    log_media_upload(
        "MEDIA STORAGE",
        f"backend={backend} use_cloudinary={use_cloudinary}",
    )
    if use_cloudinary:
        cloud_name = getattr(settings, "CLOUDINARY_CLOUD_NAME", "") or "(unset)"
        has_key = bool(getattr(settings, "CLOUDINARY_API_KEY", ""))
        has_secret = bool(getattr(settings, "CLOUDINARY_API_SECRET", ""))
        storage_config = getattr(settings, "CLOUDINARY_STORAGE", {}) or {}
        log_media_upload(
            "MEDIA STORAGE",
            (
                f"cloudinary_cloud={cloud_name} "
                f"api_key_set={has_key} api_secret_set={has_secret} "
                f"media_url={getattr(settings, 'MEDIA_URL', '')} "
                f"prefix={storage_config.get('PREFIX', '(default)')!r}"
            ),
        )
        return

    media_root = Path(settings.MEDIA_ROOT)
    log_media_upload(
        "MEDIA STORAGE",
        (
            f"media_root={media_root} exists={media_root.exists()} "
            f"is_dir={media_root.is_dir() if media_root.exists() else False}"
        ),
    )
    post_images_dir = media_root / "post_images"
    try:
        post_images_dir.mkdir(parents=True, exist_ok=True)
        writable = os.access(post_images_dir, os.W_OK)
        log_media_upload(
            "MEDIA STORAGE",
            f"post_images_dir={post_images_dir} writable={writable}",
        )
        if not writable:
            log_media_upload(
                "MEDIA STORAGE",
                "post_images ディレクトリに書き込み権限がありません",
            )
    except OSError as exc:
        log_media_upload(
            "MEDIA STORAGE",
            f"post_images_dir の確認に失敗: {exc}",
            exc=exc,
        )


def validate_timeline_image_file(image) -> None:
    """タイムライン投稿用画像のサイズ・形式を検証する。"""
    if not image:
        return

    log_media_upload("IMAGE VALIDATE", describe_uploaded_file(image))

    size = int(getattr(image, "size", 0) or 0)
    if size <= 0:
        raise ValidationError("画像ファイルが空です。")
    if size > MAX_TIMELINE_IMAGE_BYTES:
        raise ValidationError("画像は5MB以下にしてください。")

    content_type = (getattr(image, "content_type", "") or "").lower().split(";")[0].strip()
    extension = Path(getattr(image, "name", "")).suffix.lower()

    if extension in HEIC_EXTENSIONS or content_type in {"image/heic", "image/heif"}:
        raise ValidationError(
            "HEIC形式は現在非対応です。JPEG または PNG に変換してからアップロードしてください。"
        )

    if content_type in ALLOWED_IMAGE_CONTENT_TYPES or extension in ALLOWED_IMAGE_EXTENSIONS:
        log_media_upload(
            "IMAGE VALIDATE",
            f"accepted content_type={content_type!r} extension={extension!r}",
        )
        return

    if content_type in {"", "application/octet-stream", "binary/octet-stream"}:
        if extension in ALLOWED_IMAGE_EXTENSIONS:
            log_media_upload(
                "IMAGE VALIDATE",
                f"content_type missing; accepted by extension {extension!r}",
            )
            return
        raise ValidationError(
            "画像ファイル（JPEG・PNG・GIF・WebP）を選択してください。"
        )

    if content_type.startswith("image/"):
        log_media_upload(
            "IMAGE VALIDATE",
            f"accepting uncommon image content_type={content_type!r}",
        )
        return

    raise ValidationError("画像ファイル（JPEG・PNG・GIF・WebP）を選択してください。")


def ensure_local_post_images_dir() -> Path:
    """ローカル保存時に post_images ディレクトリを用意する。"""
    post_images_dir = Path(settings.MEDIA_ROOT) / "post_images"
    post_images_dir.mkdir(parents=True, exist_ok=True)
    if not os.access(post_images_dir, os.W_OK):
        raise OSError(f"post_images is not writable: {post_images_dir}")
    return post_images_dir
