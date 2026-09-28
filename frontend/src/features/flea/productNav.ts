import type { SearchProductResult } from "../profile/api";
import type { FleaShareContent } from "../share/api";
import type { SharedProduct } from "../timeline/api";
import type { ProductCard, ProductDetail } from "./api";

export type ProductDetailNavState = {
  initialProduct?: ProductCard;
};

export function productCardFromSearch(
  product: SearchProductResult
): ProductCard {
  return {
    id: product.id,
    name: product.name,
    price: product.price,
    status: product.status,
    is_sold: product.is_sold,
    is_pending: product.is_pending,
    is_available: product.is_available,
    faculty: product.faculty,
    handover_campus: "",
    handover_campus_label: product.handover_campus_label,
    course_name: product.course_name,
    professor_name: product.professor_name,
    created_at: product.created_at,
    created_at_label: product.created_at_label,
    image_url: product.image_url,
    seller: product.seller,
  };
}

export function productCardFromFleaShare(content: FleaShareContent): ProductCard {
  return {
    id: content.id,
    name: content.name,
    price: content.price,
    status: "",
    is_sold: false,
    is_pending: false,
    is_available: true,
    faculty: "",
    handover_campus: "",
    handover_campus_label: "",
    course_name: "",
    professor_name: "",
    created_at: "",
    created_at_label: "",
    image_url: content.image_url,
    seller: content.seller,
  };
}

export function productCardFromShared(product: SharedProduct): ProductCard {
  return {
    id: product.id,
    name: product.name,
    price: product.price,
    status: product.status,
    is_sold: product.is_sold,
    is_pending: product.is_pending,
    is_available: !product.is_sold && !product.is_pending,
    faculty: "",
    handover_campus: "",
    handover_campus_label: "",
    course_name: "",
    professor_name: "",
    created_at: "",
    created_at_label: "",
    image_url: product.image_url,
    seller: null,
  };
}

export function productDetailState(card: ProductCard): ProductDetailNavState {
  return { initialProduct: { ...card } };
}

/** Card visuals only — every privileged flag stays false until the detail API. */
export function productDetailFromCard(card: ProductCard): ProductDetail {
  return {
    ...card,
    description: "",
    like_count: 0,
    user_liked: false,
    user_has_bookmarked: false,
    comments: [],
    can_purchase: false,
    can_negotiate: false,
    can_review: false,
    can_delete: false,
    user_review: null,
    partner_review: null,
    review_partner: null,
    show_trade_link: false,
    trade_chat_room_id: null,
    can_share_to_timeline: false,
    can_contact_seller: false,
    user_chat_room: null,
    seller_chat_rooms: [],
    buyer: null,
  };
}

export function readInitialProduct(
  state: unknown,
  productId: number
): ProductDetail | null {
  if (!state || typeof state !== "object") return null;
  const raw = (state as ProductDetailNavState).initialProduct;
  if (!raw || raw.id !== productId) return null;
  return productDetailFromCard(raw);
}
