import assert from "node:assert/strict";
import test from "node:test";
import type { TimelinePost } from "./api.ts";
import {
  compactTimelinePost,
  readInitialTimelinePost,
  timelinePostDetailState,
} from "./postAnchor.ts";

const post = {
  id: 41,
  body: "hello",
  created_at: "2026-10-24T00:00:00Z",
  course_name: "",
  professor_name: "",
  faculty: "",
  image_url: null,
  like_count: 2,
  comment_count: 3,
  quote_count: 0,
  view_count: 9,
  user_has_liked: true,
  user_has_bookmarked: false,
  can_delete: true,
  author: {
    id: 1,
    username: "taro",
    display_name: "太郎",
    avatar_url: "",
    initial: "太",
  },
  quoted_post: null,
  shared_product: null,
  comments: [
    {
      id: 9,
      body: "secret reply",
      created_at: "2026-10-24T00:01:00Z",
      can_delete: true,
      author: null,
      parent_comment_id: null,
      reply_to: null,
      is_deleted: false,
      reply_count: 0,
    },
  ],
} as TimelinePost;

test("compact snapshots drop comments so location.state stays display-only", () => {
  const compact = compactTimelinePost(post);
  assert.deepEqual(compact.comments, []);
  assert.equal(compact.id, 41);
  assert.equal(compact.body, "hello");
});

test("readInitialTimelinePost accepts a matching id and strips comments", () => {
  const state = timelinePostDetailState(post);
  const next = readInitialTimelinePost(state, 41);
  assert.ok(next);
  assert.equal(next?.id, 41);
  assert.deepEqual(next?.comments, []);
});

test("readInitialTimelinePost rejects a snapshot for a different post", () => {
  const state = timelinePostDetailState(post);
  assert.equal(readInitialTimelinePost(state, 99), null);
  assert.equal(readInitialTimelinePost(null, 41), null);
});
