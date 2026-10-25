import assert from "node:assert/strict";
import test from "node:test";
import type { ProductCard } from "./api.ts";
import {
  productDetailFromCard,
  productDetailState,
  readInitialProduct,
} from "./productNav.ts";

const card: ProductCard = {
  id: 12,
  name: "微分積分の教科書",
  price: 1500,
  status: "available",
  is_sold: false,
  is_pending: false,
  is_available: true,
  faculty: "政経",
  handover_campus: "waseda",
  handover_campus_label: "早稲田",
  course_name: "",
  professor_name: "",
  created_at: "2026-10-24T00:00:00Z",
  created_at_label: "1時間前",
  image_url: "https://example.com/book.jpg",
  seller: {
    id: 4,
    username: "seller",
    display_name: "出品者",
    avatar_url: "",
    initial: "出",
  },
};

test("card previews keep visuals but zero every trade permission", () => {
  const detail = productDetailFromCard(card);
  assert.equal(detail.id, 12);
  assert.equal(detail.name, card.name);
  assert.equal(detail.price, 1500);
  assert.equal(detail.image_url, card.image_url);
  assert.equal(detail.can_purchase, false);
  assert.equal(detail.can_negotiate, false);
  assert.equal(detail.can_delete, false);
  assert.equal(detail.can_review, false);
  assert.equal(detail.can_share_to_timeline, false);
  assert.equal(detail.can_contact_seller, false);
  assert.equal(detail.user_chat_room, null);
  assert.deepEqual(detail.seller_chat_rooms, []);
  assert.deepEqual(detail.comments, []);
});

test("readInitialProduct accepts a matching product and rejects a different id", () => {
  const state = productDetailState(card);
  const next = readInitialProduct(state, 12);
  assert.ok(next);
  assert.equal(next?.id, 12);
  assert.equal(next?.can_purchase, false);
  assert.equal(readInitialProduct(state, 99), null);
  assert.equal(readInitialProduct(undefined, 12), null);
});
