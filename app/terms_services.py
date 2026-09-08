"""利用規約への同意記録。版番号は constants.CURRENT_TERMS_VERSION に集約する。"""

from __future__ import annotations

from django.utils import timezone

from .constants import CURRENT_TERMS_VERSION


def terms_acceptance_defaults() -> dict:
    """新規同意時に UserProfile へ保存するフィールド。"""
    return {
        "terms_accepted": True,
        "terms_accepted_at": timezone.now(),
        "terms_version": CURRENT_TERMS_VERSION,
    }
