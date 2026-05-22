"""Stripe Connect（Destination Charges）による Checkout 決済。"""

from __future__ import annotations

import logging

import stripe
from stripe import RequestsClient
from django.conf import settings
from django.db import transaction
from django.urls import reverse

from .models import Product
from .services import notify_seller

logger = logging.getLogger(__name__)


class StripeConfigurationError(Exception):
    """Stripe または Connect の設定不足。"""


class StripeCheckoutError(Exception):
    """Checkout Session 作成・完了処理の失敗。"""


_http_client_configured = False


def _stripe_obj_get(obj, key: str, default=None):
    """StripeObject / dict からキーを取得（.get() は StripeObject に無い）。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _setup_stripe_http_client() -> None:
    """
    Stripe API 用 HTTP クライアント。
    Windows 開発環境の CERTIFICATE_VERIFY_FAILED 対策:
    - STRIPE_SSL_VERIFY=False のとき verify_ssl_certs=False
    - それ以外は certifi の CA バンドルで検証
    """
    global _http_client_configured
    if _http_client_configured:
        return

    verify_ssl = getattr(settings, "STRIPE_SSL_VERIFY", True)

    if not verify_ssl:
        stripe.default_http_client = RequestsClient(verify_ssl_certs=False)
        if settings.DEBUG:
            logger.warning(
                "[WASE DEV] Stripe: SSL証明書検証を無効化しています（テスト環境専用）。"
            )
    else:
        try:
            import certifi

            stripe.ca_bundle_path = certifi.where()
        except ImportError:
            logger.warning("certifi が未インストールのため Stripe デフォルト CA を使用します。")
        stripe.default_http_client = RequestsClient(verify_ssl_certs=True)

    _http_client_configured = True


def _configure_stripe() -> None:
    secret = getattr(settings, "STRIPE_SECRET_KEY", "") or ""
    if not secret:
        raise StripeConfigurationError("STRIPE_SECRET_KEY が未設定です。")
    _setup_stripe_http_client()
    stripe.api_key = secret


def calc_application_fee_yen(price_yen: int) -> int:
    """プラットフォーム手数料（円）。キャンペーン時は 0。"""
    if getattr(settings, "CAMPAIGN_FEE_FREE", False):
        return 0
    percent = int(getattr(settings, "STRIPE_PLATFORM_FEE_PERCENT", 10))
    return int(price_yen * percent / 100)


def get_seller_connect_account_id(seller) -> str:
    """出品者の Connect アカウント。未設定時は開発用フォールバック。"""
    if seller and seller.stripe_connect_account_id:
        return seller.stripe_connect_account_id.strip()
    fallback = getattr(settings, "STRIPE_CONNECT_DESTINATION_ACCOUNT", "") or ""
    return fallback.strip()


def create_product_checkout_session(*, product: Product, buyer, request) -> str:
    """
    Checkout Session を作成し、リダイレクト用 URL を返す。

    STRIPE_USE_STANDARD_CHARGES=True（開発デフォルト）:
        プラットフォーム口座へ全額入金（Connect transfers 不要）。
    False:
        Destination Charges（出品者 Connect へ送金 + application_fee）。
    """
    _configure_stripe()

    if not product.seller_id:
        raise StripeCheckoutError("出品者が設定されていません。")
    if product.seller_id == buyer.id:
        raise StripeCheckoutError("自分の商品は購入できません。")
    if product.status != Product.Status.AVAILABLE:
        raise StripeCheckoutError("この商品は現在購入できません。")

    use_standard = getattr(settings, "STRIPE_USE_STANDARD_CHARGES", False)
    destination = ""
    fee_amount = 0

    if not use_standard:
        destination = get_seller_connect_account_id(product.seller)
        if not destination:
            raise StripeConfigurationError(
                "出品者の Stripe Connect アカウントが未登録です。"
                " settings.py の STRIPE_CONNECT_DESTINATION_ACCOUNT にテスト用 acct_... を設定するか、"
                " 出品者の stripe_connect_account_id を登録してください。"
            )
        fee_amount = calc_application_fee_yen(product.price)
    elif settings.DEBUG:
        logger.warning(
            "[WASE DEV] Stripe: Standard Charges（Connect 送金なし）で Checkout を作成します。"
        )

    success_url = (
        request.build_absolute_uri(
            reverse("stripe_payment_success", kwargs={"pk": product.pk})
        )
        + "?session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = request.build_absolute_uri(
        reverse("stripe_payment_cancel", kwargs={"pk": product.pk})
    )

    session_metadata = {
        "product_id": str(product.pk),
        "buyer_id": str(buyer.pk),
    }

    session_params = {
        "mode": "payment",
        "client_reference_id": str(product.pk),
        "line_items": [
            {
                "price_data": {
                    "currency": "jpy",
                    "unit_amount": product.price,
                    "product_data": {
                        "name": product.name[:120],
                        "metadata": {"product_id": str(product.pk)},
                    },
                },
                "quantity": 1,
            }
        ],
        "metadata": session_metadata,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }

    if use_standard:
        session_params["payment_intent_data"] = {"metadata": session_metadata}
    else:
        session_params["payment_intent_data"] = {
            "application_fee_amount": fee_amount,
            "transfer_data": {"destination": destination},
            "metadata": session_metadata,
        }

    try:
        session = stripe.checkout.Session.create(**session_params)
    except stripe.error.StripeError as exc:
        logger.exception("Stripe Checkout create failed product=%s", product.pk)
        raise StripeCheckoutError(str(exc)) from exc

    product.stripe_checkout_session_id = session.id
    product.save(update_fields=["stripe_checkout_session_id"])
    return session.url


@transaction.atomic
def fulfill_checkout_session(*, session_id: str, expected_buyer_id: int) -> Product:
    """決済成功後に商品を取引中へ更新する。"""
    _configure_stripe()

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as exc:
        raise StripeCheckoutError(f"セッションの取得に失敗しました: {exc}") from exc

    if session.payment_status != "paid":
        raise StripeCheckoutError("決済が完了していません。")

    metadata = session.metadata
    product_id = _stripe_obj_get(metadata, "product_id") or session.client_reference_id
    buyer_id = _stripe_obj_get(metadata, "buyer_id")
    if not product_id:
        raise StripeCheckoutError("注文情報が見つかりません。")
    if str(expected_buyer_id) != str(buyer_id):
        raise StripeCheckoutError("購入者情報が一致しません。")

    product = Product.objects.select_for_update().select_related("seller").get(
        pk=int(product_id)
    )

    if product.status == Product.Status.AVAILABLE:
        product.status = Product.Status.TRADING
        product.buyer_id = int(buyer_id)
        product.seller_trade_completed = False
        product.buyer_trade_completed = False
        product.stripe_checkout_session_id = session.id
        product.save(
            update_fields=[
                "status",
                "buyer",
                "seller_trade_completed",
                "buyer_trade_completed",
                "stripe_checkout_session_id",
            ]
        )
        notify_seller(
            product,
            f"「{product.name}」が購入されました（¥{product.price:,}・決済済み）。",
            actor_id=int(buyer_id),
        )
    elif product.status == Product.Status.TRADING and product.buyer_id == int(
        buyer_id
    ):
        pass
    else:
        raise StripeCheckoutError("この商品はすでに他の購入者と取引中です。")

    return product
