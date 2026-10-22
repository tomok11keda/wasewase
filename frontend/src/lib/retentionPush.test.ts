import assert from "node:assert/strict";
import test from "node:test";
import { parseRetentionPushOpen } from "./retentionPush.ts";

test("parses popular_post kind and post id from SPA path", () => {
  const parsed = parseRetentionPushOpen("/posts/42?rp=popular_post");
  assert.deepEqual(parsed, { kind: "popular_post", postId: 42 });
});

test("parses /app prefixed FCM links after router conversion", () => {
  const parsed = parseRetentionPushOpen("/posts/9?rp=popular_post#focus");
  assert.equal(parsed?.kind, "popular_post");
  assert.equal(parsed?.postId, 9);
});

test("returns null when rp is missing so in-app notification opens stay untouched", () => {
  assert.equal(parseRetentionPushOpen("/posts/42"), null);
  assert.equal(parseRetentionPushOpen("/notifications"), null);
});
