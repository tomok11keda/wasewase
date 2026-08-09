import { getCsrfToken } from "../timeline/api";

export type Author = {
  id: number | null;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
};

export type ProductCard = {
  id: number;
  name: string;
  price: number;
  status: string;
  is_sold: boolean;
  is_pending: boolean;
  is_available: boolean;
  faculty: string;
  handover_campus: string;
  handover_campus_label: string;
  course_name: string;
  professor_name: string;
  created_at: string;
  created_at_label: string;
  image_url: string;
  seller: Author | null;
};

export type ProductComment = {
  id: number;
  body: string;
  created_at: string;
  created_at_label: string;
  author: Author | null;
};

export type ProductDetail = ProductCard & {
  description: string;
  like_count: number;
  user_liked: boolean;
  user_has_bookmarked: boolean;
  comments: ProductComment[];
  can_purchase: boolean;
  can_negotiate: boolean;
  can_review: boolean;
  can_delete: boolean;
  user_review: { id: number; rating: number; comment: string } | null;
  partner_review: { id: number; rating: number; comment: string } | null;
  review_partner: Author | null;
  show_trade_link: boolean;
  trade_chat_room_id: number | null;
  can_share_to_timeline: boolean;
  can_contact_seller: boolean;
  user_chat_room: { id: number; deal_status: string } | null;
  seller_chat_rooms: { id: number; deal_status: string; buyer: Author | null }[];
  buyer: Author | null;
};

export type FilterTab = { value: string; label: string };

export type FleaListResponse = {
  products: ProductCard[];
  feed: string;
  q: string;
  faculty: string;
  campus: string;
  campus_label: string;
  order: string;
  order_label: string;
  feed_following_unauthenticated: boolean;
  user_faculty: string;
  faculty_tabs: FilterTab[];
  campus_tabs: FilterTab[];
  order_options: FilterTab[];
};

export type ChatMessage = {
  id: number;
  sender_id: number | null;
  sender_name: string;
  body: string;
  created_at: string;
  is_mine: boolean;
  is_system: boolean;
};

export type ChatRoomDetail = {
  id: number;
  deal_status: string;
  is_seller: boolean;
  can_confirm_trade: boolean;
  can_complete_handover: boolean;
  can_send_message: boolean;
  trade_status_label: string;
  product: ProductCard;
  partner: Author | null;
  buyer: Author | null;
  product_thumbnail_url: string;
};

export type ExhibitMeta = {
  faculty_choices: FilterTab[];
  campus_choices: FilterTab[];
};

export async function fetchFleaList(query: {
  feed?: string;
  q?: string;
  faculty?: string;
  campus?: string;
  order?: string;
}): Promise<FleaListResponse> {
  const params = new URLSearchParams();
  if (query.feed) params.set("feed", query.feed);
  if (query.q) params.set("q", query.q);
  if (query.faculty) params.set("faculty", query.faculty);
  if (query.campus) params.set("campus", query.campus);
  if (query.order) params.set("order", query.order);
  const qs = params.toString();
  const res = await fetch(qs ? `/api/v1/flea/?${qs}` : "/api/v1/flea/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`flea_list_${res.status}`);
  return res.json();
}

export async function fetchProductDetail(pk: number): Promise<ProductDetail> {
  const res = await fetch(`/api/v1/flea/products/${pk}/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "detail_failed");
  return data.product as ProductDetail;
}

export async function fetchExhibitMeta(): Promise<ExhibitMeta> {
  const res = await fetch("/api/v1/flea/products/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`exhibit_meta_${res.status}`);
  return res.json();
}

export async function createProduct(form: FormData): Promise<ProductCard> {
  const res = await fetch("/api/v1/flea/products/", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
    body: form,
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    const fieldErrors = data.errors as
      | Record<string, Array<{ message?: string } | string>>
      | undefined;
    const imageMessages = fieldErrors?.image;
    const firstImage =
      typeof imageMessages?.[0] === "string"
        ? imageMessages[0]
        : imageMessages?.[0]?.message;
    throw new Error(
      firstImage || data.message || data.error || "exhibit_failed"
    );
  }
  return data.product as ProductCard;
}

export async function toggleProductLike(
  pk: number
): Promise<{ liked: boolean; like_count: number }> {
  const res = await fetch(`/api/v1/flea/products/${pk}/like/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "like_failed");
  return { liked: data.liked, like_count: data.like_count };
}

export async function toggleProductBookmark(pk: number): Promise<boolean> {
  const res = await fetch(`/api/v1/flea/products/${pk}/bookmark/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "bookmark_failed");
  return Boolean(data.bookmarked);
}

export async function postProductComment(
  pk: number,
  body: string
): Promise<ProductComment> {
  const res = await fetch(`/api/v1/flea/products/${pk}/comments/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ body }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "comment_failed");
  return data.comment as ProductComment;
}

export async function purchaseProduct(pk: number): Promise<number> {
  const res = await fetch(`/api/v1/flea/products/${pk}/purchase/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "purchase_failed");
  return data.room_id as number;
}

export async function startProductChat(pk: number): Promise<number> {
  const res = await fetch(`/api/v1/flea/products/${pk}/chat/start/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "chat_start_failed");
  return data.room_id as number;
}

export async function deleteProduct(pk: number): Promise<void> {
  const res = await fetch(`/api/v1/flea/products/${pk}/delete/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "delete_failed");
}

export async function shareProductToTimeline(pk: number): Promise<void> {
  const res = await fetch(`/api/v1/flea/products/${pk}/share/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "share_failed");
}

export async function submitProductReview(
  pk: number,
  rating: number,
  comment: string
): Promise<void> {
  const res = await fetch(`/api/v1/flea/products/${pk}/review/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ rating, comment }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "review_failed");
}

export async function fetchChatRoom(roomPk: number): Promise<ChatRoomDetail> {
  const res = await fetch(`/api/v1/flea/chats/${roomPk}/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "chat_failed");
  return data.room as ChatRoomDetail;
}

export async function fetchChatMessages(
  roomPk: number,
  after?: number,
  signal?: AbortSignal
): Promise<{ messages: ChatMessage[]; latest_id: number }> {
  const qs = after ? `?after=${after}` : "";
  const res = await fetch(`/api/v1/flea/chats/${roomPk}/messages/${qs}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) throw new Error(`messages_${res.status}`);
  return res.json();
}

export async function sendChatMessage(
  roomPk: number,
  body: string
): Promise<ChatMessage> {
  const res = await fetch(`/api/v1/flea/chats/${roomPk}/messages/send/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ body }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "send_failed");
  return data.message as ChatMessage;
}

export async function confirmTrade(roomPk: number): Promise<ChatRoomDetail> {
  const res = await fetch(`/api/v1/flea/chats/${roomPk}/confirm/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "confirm_failed");
  return data.room as ChatRoomDetail;
}

export async function completeHandover(roomPk: number): Promise<ChatRoomDetail> {
  const res = await fetch(`/api/v1/flea/chats/${roomPk}/handover-complete/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "handover_failed");
  return data.room as ChatRoomDetail;
}

export function purchaseErrorMessage(code: string): string {
  switch (code) {
    case "sold":
      return "この商品はすでに売却済みです。";
    case "pending":
      return "この商品はすでに取引中です。";
    case "own_product":
      return "自分の商品は購入できません。";
    default:
      return "購入できません。";
  }
}
