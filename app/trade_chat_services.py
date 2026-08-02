"""商品専用チャットでの即決購入・値下げ交渉・受け渡し完了。"""
from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from .models import ChatRoom, Message, Product

SYSTEM_MSG_INSTANT_BUY = (
    "即決購入が成立しました。受け渡し場所と時間を相談してください"
)
SYSTEM_MSG_TRADE_CONFIRMED = "取引が確定しました"
SYSTEM_MSG_OTHER_INSTANT_BUY = (
    "別の方が即決購入したため、取引終了です"
)
SYSTEM_MSG_OTHER_CONFIRMED = (
    "別の方との取引が確定したため、この交渉は終了です"
)
SYSTEM_MSG_HANDOVER_DONE = "受け渡しが完了し、商品は売り切れになりました"


def post_system_message(room: ChatRoom, body: str) -> Message:
    message = Message.objects.create(
        chat_room=room,
        sender=None,
        body=body,
        is_system=True,
    )
    ChatRoom.objects.filter(pk=room.pk).update(updated_at=timezone.now())
    return message


def close_other_negotiation_rooms(
    product: Product,
    *,
    except_room: ChatRoom | None,
    system_body: str,
) -> int:
    """他の交渉中ルームを終了し、システムメッセージを投稿する。"""
    qs = ChatRoom.objects.filter(
        product=product,
        kind=ChatRoom.Kind.PRODUCT,
        deal_status=ChatRoom.DealStatus.NEGOTIATING,
    )
    if except_room is not None:
        qs = qs.exclude(pk=except_room.pk)

    closed = 0
    for room in qs:
        room.deal_status = ChatRoom.DealStatus.CLOSED
        room.save(update_fields=["deal_status", "updated_at"])
        post_system_message(room, system_body)
        closed += 1
    return closed


@transaction.atomic
def start_instant_purchase(product: Product, buyer: AbstractBaseUser) -> ChatRoom:
    """即決購入: ルーム作成 + pending + 他交渉ルームへ終了通知。"""
    locked = Product.objects.select_for_update().get(pk=product.pk)
    if locked.is_sold:
        raise ValueError("sold")
    if locked.is_pending:
        raise ValueError("pending")
    if locked.seller_id == buyer.id:
        raise ValueError("own_product")

    room, _created = ChatRoom.objects.get_or_create(
        product=locked,
        buyer=buyer,
        defaults={"deal_status": ChatRoom.DealStatus.CONFIRMED},
    )
    if room.deal_status != ChatRoom.DealStatus.CONFIRMED:
        room.deal_status = ChatRoom.DealStatus.CONFIRMED
        room.save(update_fields=["deal_status", "updated_at"])

    locked.status = Product.Status.PENDING
    locked.buyer = buyer
    locked.seller_trade_completed = False
    locked.buyer_trade_completed = False
    locked.save(
        update_fields=[
            "status",
            "buyer",
            "seller_trade_completed",
            "buyer_trade_completed",
        ]
    )

    post_system_message(room, SYSTEM_MSG_INSTANT_BUY)
    close_other_negotiation_rooms(
        locked,
        except_room=room,
        system_body=SYSTEM_MSG_OTHER_INSTANT_BUY,
    )
    return room


@transaction.atomic
def start_negotiation(product: Product, buyer: AbstractBaseUser) -> tuple[ChatRoom, bool]:
    """値下げ交渉: ルーム作成（商品は available のまま）。"""
    locked = Product.objects.select_for_update().get(pk=product.pk)
    if locked.is_sold:
        raise ValueError("sold")
    if locked.is_pending:
        raise ValueError("pending")
    if locked.seller_id == buyer.id:
        raise ValueError("own_product")

    room, created = ChatRoom.objects.get_or_create(
        product=locked,
        buyer=buyer,
        defaults={"deal_status": ChatRoom.DealStatus.NEGOTIATING},
    )
    if room.deal_status == ChatRoom.DealStatus.CLOSED:
        room.deal_status = ChatRoom.DealStatus.NEGOTIATING
        room.save(update_fields=["deal_status", "updated_at"])
        created = True
    return room, created


@transaction.atomic
def confirm_negotiation_trade(room: ChatRoom, seller: AbstractBaseUser) -> ChatRoom:
    """出品者が交渉ルームで取引開始 → pending。"""
    room = (
        ChatRoom.objects.select_for_update()
        .select_related("product")
        .get(pk=room.pk)
    )
    product = Product.objects.select_for_update().get(pk=room.product_id)

    if product.seller_id != seller.id:
        raise ValueError("not_seller")
    if room.deal_status != ChatRoom.DealStatus.NEGOTIATING:
        raise ValueError("not_negotiating")
    if not product.is_available:
        raise ValueError("not_available")

    room.deal_status = ChatRoom.DealStatus.CONFIRMED
    room.save(update_fields=["deal_status", "updated_at"])

    product.status = Product.Status.PENDING
    product.buyer = room.buyer
    product.seller_trade_completed = False
    product.buyer_trade_completed = False
    product.save(
        update_fields=[
            "status",
            "buyer",
            "seller_trade_completed",
            "buyer_trade_completed",
        ]
    )

    post_system_message(room, SYSTEM_MSG_TRADE_CONFIRMED)
    close_other_negotiation_rooms(
        product,
        except_room=room,
        system_body=SYSTEM_MSG_OTHER_CONFIRMED,
    )
    return room


@transaction.atomic
def complete_handover_by_seller(room: ChatRoom, seller: AbstractBaseUser) -> Product:
    """出品者が受け渡し完了 → sold。"""
    room = (
        ChatRoom.objects.select_for_update()
        .select_related("product")
        .get(pk=room.pk)
    )
    product = Product.objects.select_for_update().get(pk=room.product_id)

    if product.seller_id != seller.id:
        raise ValueError("not_seller")
    if product.is_sold:
        raise ValueError("already_sold")
    if not product.is_pending:
        raise ValueError("not_pending")
    if room.deal_status != ChatRoom.DealStatus.CONFIRMED:
        raise ValueError("not_confirmed")
    if product.buyer_id != room.buyer_id:
        raise ValueError("buyer_mismatch")

    product.status = Product.Status.SOLD
    product.seller_trade_completed = True
    product.buyer_trade_completed = True
    product.save(
        update_fields=["status", "seller_trade_completed", "buyer_trade_completed"]
    )
    post_system_message(room, SYSTEM_MSG_HANDOVER_DONE)
    return product


def get_confirmed_room_for_product(product: Product) -> ChatRoom | None:
    if not product.buyer_id:
        return None
    return (
        ChatRoom.objects.filter(
            product=product,
            buyer_id=product.buyer_id,
            deal_status=ChatRoom.DealStatus.CONFIRMED,
        )
        .order_by("-updated_at")
        .first()
    )
