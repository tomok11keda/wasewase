/**
 * Executable timeline comment grouping / reply-target tests.
 * Keep behavior in sync with frontend/src/features/timeline/commentThread.ts
 */
const UNAVAILABLE_REPLY_LABEL = "返信先は表示できません";

function isDescendantOf(comment, ancestorId, comments) {
  const byId = new Map(comments.map((row) => [row.id, row]));
  let current = comment;
  const seen = new Set();
  while (current?.parent_comment_id) {
    if (seen.has(current.id)) return false;
    seen.add(current.id);
    if (current.parent_comment_id === ancestorId) return true;
    current = byId.get(current.parent_comment_id);
  }
  return false;
}

function groupTimelineComments(comments) {
  const visibleIds = new Set(comments.map((row) => row.id));
  const groups = [];
  for (const comment of comments) {
    const parentId = comment.parent_comment_id;
    const parentVisible = parentId != null && visibleIds.has(parentId);
    const current = groups[groups.length - 1];
    if (
      parentVisible &&
      current &&
      (parentId === current.root.id ||
        isDescendantOf(comment, current.root.id, comments))
    ) {
      current.replies.push(comment);
      continue;
    }
    groups.push({ root: comment, replies: [] });
  }
  return groups;
}

function replyToLabel(comment) {
  if (!comment.parent_comment_id || !comment.reply_to) return null;
  if (comment.reply_to.is_unavailable || !comment.reply_to.username) {
    return UNAVAILABLE_REPLY_LABEL;
  }
  return `@${comment.reply_to.username} への返信`;
}

function canJumpToReplyParent(comment) {
  return Boolean(
    comment.parent_comment_id &&
      comment.reply_to &&
      !comment.reply_to.is_unavailable &&
      comment.reply_to.username
  );
}

function insertThreadedComment(comments, comment) {
  if (!comment.parent_comment_id) return [...comments, comment];
  const parentIdx = comments.findIndex((row) => row.id === comment.parent_comment_id);
  if (parentIdx < 0) return [...comments, comment];
  let insertAt = parentIdx + 1;
  while (
    insertAt < comments.length &&
    isDescendantOf(comments[insertAt], comment.parent_comment_id, comments)
  ) {
    insertAt += 1;
  }
  const next = comments.slice();
  next.splice(insertAt, 0, comment);
  return next;
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  }
}

function bodies(groups) {
  return groups.map((g) => [g.root.body, ...g.replies.map((r) => r.body)]);
}

function c(id, body, parent, replyTo = null) {
  return {
    id,
    body,
    parent_comment_id: parent,
    reply_to: replyTo,
  };
}

const available = (id, username) => ({
  id,
  username,
  display_name: username,
  is_unavailable: false,
});
const unavailable = (id) => ({
  id,
  username: "",
  display_name: "",
  is_unavailable: true,
});

// A → B → C DFS: one group
let comments = [
  c(1, "A", null),
  c(2, "B", 1, available(1, "ayy")),
  c(3, "C", 2, available(2, "garchomp102")),
];
assert(
  JSON.stringify(bodies(groupTimelineComments(comments))) ===
    JSON.stringify([["A", "B", "C"]]),
  "A→B→C stays one group in DFS order"
);
assert(replyToLabel(comments[1]) === "@ayy への返信", "B replies to A username");
assert(replyToLabel(comments[2]) === "@garchomp102 への返信", "C replies to B not A");
assert(canJumpToReplyParent(comments[2]), "C can jump to B");
assert(comments[2].reply_to.id === 2, "target is actual parent id, not previous guess");

// siblings A→B, A→C
comments = [
  c(1, "A", null),
  c(2, "B", 1, available(1, "ayy")),
  c(3, "C", 1, available(1, "ayy")),
];
assert(
  JSON.stringify(bodies(groupTimelineComments(comments))) ===
    JSON.stringify([["A", "B", "C"]]),
  "sibling replies stay under A"
);

// A→B→D plus sibling C: DFS A,B,D,C
comments = [
  c(1, "A", null),
  c(2, "B", 1, available(1, "a")),
  c(4, "D", 2, available(2, "b")),
  c(3, "C", 1, available(1, "a")),
];
assert(
  JSON.stringify(bodies(groupTimelineComments(comments))) ===
    JSON.stringify([["A", "B", "D", "C"]]),
  "DFS A,B,D,C not A,B,C,D"
);

// deep chain
comments = [
  c(1, "A", null),
  c(2, "B", 1, available(1, "a")),
  c(3, "C", 2, available(2, "b")),
  c(4, "D", 3, available(3, "c")),
  c(5, "E", 4, available(4, "d")),
];
assert(
  JSON.stringify(bodies(groupTimelineComments(comments))) ===
    JSON.stringify([["A", "B", "C", "D", "E"]]),
  "deep chain one group"
);

// multiple roots
comments = [
  c(1, "A", null),
  c(2, "A1", 1, available(1, "a")),
  c(3, "B", null),
  c(4, "B1", 3, available(3, "b")),
  c(5, "C", null),
];
assert(
  JSON.stringify(bodies(groupTimelineComments(comments))) ===
    JSON.stringify([["A", "A1"], ["B", "B1"], ["C"]]),
  "multiple roots stay separate"
);

// blocked/missing parent B: C must NOT join A
comments = [
  c(1, "A", null),
  c(3, "C", 2, unavailable(2)),
];
const blocked = groupTimelineComments(comments);
assert(
  JSON.stringify(bodies(blocked)) === JSON.stringify([["A"], ["C"]]),
  "orphan C is its own group, not attached to A"
);
assert(replyToLabel(comments[1]) === UNAVAILABLE_REPLY_LABEL, "no leaked username");
assert(!canJumpToReplyParent(comments[1]), "unavailable parent is no-op jump");

// tombstone parent still visible: keep children in group
comments = [
  c(1, "削除されたコメント", null),
  c(2, "child", 1, unavailable(1)),
];
assert(
  JSON.stringify(bodies(groupTimelineComments(comments))) ===
    JSON.stringify([["削除されたコメント", "child"]]),
  "tombstone parent keeps children"
);
assert(!canJumpToReplyParent(comments[1]), "tombstone jump is no-op");

// do not infer target from previous comment
const prev = c(10, "prev", null);
const reply = c(11, "reply", 99, available(99, "realparent"));
assert(replyToLabel(reply) === "@realparent への返信", "uses reply_to not previous row");
assert(reply.parent_comment_id !== prev.id, "parent is not the previous comment");

// insert after descendants
const seeded = [
  c(1, "A", null),
  c(2, "B", 1),
  c(3, "C", 2),
];
const inserted = insertThreadedComment(seeded, c(4, "B2", 1));
assert(
  inserted.map((row) => row.body).join(",") === "A,B,C,B2",
  "insert after A's descendants"
);

assert(UNAVAILABLE_REPLY_LABEL === "返信先は表示できません", "fallback copy");

if (process.exitCode) {
  console.error("comment thread tests failed");
  process.exit(1);
}
console.log("comment thread tests ok");
