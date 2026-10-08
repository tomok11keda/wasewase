import type { TimelineComment } from "./api";

export const TIMELINE_COMMENT_ID_PREFIX = "timeline-comment-";
export const COMMENT_FLASH_MS = 1200;
export const UNAVAILABLE_REPLY_LABEL = "返信先は表示できません";

export type TimelineCommentGroup = {
  root: TimelineComment;
  replies: TimelineComment[];
};

export function timelineCommentDomId(id: number): string {
  return `${TIMELINE_COMMENT_ID_PREFIX}${id}`;
}

export function isDescendantOf(
  comment: TimelineComment,
  ancestorId: number,
  comments: TimelineComment[]
): boolean {
  const byId = new Map(comments.map((row) => [row.id, row]));
  let current: TimelineComment | undefined = comment;
  const seen = new Set<number>();
  while (current?.parent_comment_id) {
    if (seen.has(current.id)) return false;
    seen.add(current.id);
    if (current.parent_comment_id === ancestorId) return true;
    current = byId.get(current.parent_comment_id);
  }
  return false;
}

export function insertThreadedComment(
  comments: TimelineComment[],
  comment: TimelineComment
): TimelineComment[] {
  if (!comment.parent_comment_id) {
    return [...comments, comment];
  }
  const parentIdx = comments.findIndex(
    (row) => row.id === comment.parent_comment_id
  );
  if (parentIdx < 0) {
    return [...comments, comment];
  }
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

/**
 * Group a parent-first DFS comment list into visible roots + descendants.
 * A comment starts a new group when its parent is not in this list
 * (missing / blocked / filtered). Never attaches to a guessed neighbor.
 */
export function groupTimelineComments(
  comments: TimelineComment[]
): TimelineCommentGroup[] {
  const visibleIds = new Set(comments.map((row) => row.id));
  const groups: TimelineCommentGroup[] = [];

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

export function replyToLabel(comment: TimelineComment): string | null {
  if (!comment.parent_comment_id || !comment.reply_to) return null;
  if (comment.reply_to.is_unavailable || !comment.reply_to.username) {
    return UNAVAILABLE_REPLY_LABEL;
  }
  return `@${comment.reply_to.username} への返信`;
}

export function canJumpToReplyParent(comment: TimelineComment): boolean {
  return Boolean(
    comment.parent_comment_id &&
      comment.reply_to &&
      !comment.reply_to.is_unavailable &&
      comment.reply_to.username
  );
}
