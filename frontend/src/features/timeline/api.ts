import { userFacingMutationError } from "../../lib/rateLimit";

export type TimelineAuthor = {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
} | null;

export type TimelineComment = {
  id: number;
  body: string;
  created_at: string;
  can_delete: boolean;
  author: TimelineAuthor;
};

export type QuotedPost = {
  id: number;
  is_removed: boolean;
  body: string;
  author: TimelineAuthor;
  image_url: string | null;
  course_name: string;
} | null;

export type TimelinePost = {
  id: number;
  body: string;
  created_at: string;
  course_name: string;
  professor_name: string;
  faculty: string;
  image_url: string | null;
  like_count: number;
  comment_count: number;
  quote_count: number;
  view_count: number;
  user_has_liked: boolean;
  user_has_bookmarked: boolean;
  can_delete: boolean;
  author: TimelineAuthor;
  quoted_post: QuotedPost;
  comments: TimelineComment[];
};

export type TimelineFeedResponse = {
  posts: TimelinePost[];
  has_more: boolean;
  next_offset: number;
  total_count: number;
  feed: string;
  sort?: "recommended" | "latest";
  q: string;
  faculty: string;
  tag: string;
  feed_following_unauthenticated?: boolean;
  ads: {
    show_infeed: boolean;
    interval: number;
    disabled: boolean;
  };
};

export function getCsrfToken(): string {
  // Django validates X-CSRFToken against the csrftoken *cookie*.
  // Prefer cookie over <meta> so a rotated cookie (e.g. after ensureAuthCsrf)
  // is never overridden by a stale meta token from the initial spa.html render.
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
  if (match) return decodeURIComponent(match[1]);
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta?.getAttribute("content") || "";
}

export type FeedQuery = {
  feed?: "all" | "following";
  sort?: "recommended" | "latest";
  q?: string;
  faculty?: string;
  tag?: string;
  offset?: number;
  seen?: number[];
};

function buildFeedUrl(query: FeedQuery): string {
  const params = new URLSearchParams();
  if (query.feed) params.set("feed", query.feed);
  if (query.sort && query.sort !== "recommended") {
    params.set("sort", query.sort);
  }
  if (query.q) params.set("q", query.q);
  if (query.faculty) params.set("faculty", query.faculty);
  if (query.tag) params.set("tag", query.tag);
  if (typeof query.offset === "number") {
    params.set("offset", String(query.offset));
  }
  if (query.seen?.length) {
    params.set("seen", query.seen.slice(0, 80).join(","));
  }
  const qs = params.toString();
  return qs ? `/api/v1/timeline/?${qs}` : "/api/v1/timeline/";
}

export async function fetchTimeline(
  query: FeedQuery = {}
): Promise<TimelineFeedResponse> {
  const res = await fetch(buildFeedUrl(query), {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`timeline_${res.status}`);
  return res.json();
}

export async function createTimelinePost(input: {
  body: string;
  image?: File | null;
  quoted_post_id?: number | null;
}): Promise<TimelinePost> {
  const form = new FormData();
  form.append("body", input.body);
  if (input.image) form.append("image", input.image);
  if (input.quoted_post_id) {
    form.append("quoted_post_id", String(input.quoted_post_id));
  }
  const res = await fetch("/api/v1/timeline/", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken() },
    body: form,
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(
      userFacingMutationError(
        data.error || `compose_${res.status}`,
        "投稿に失敗しました"
      )
    );
  }
  return data.post as TimelinePost;
}

export async function toggleLike(
  postId: number
): Promise<{ liked: boolean; like_count: number }> {
  const res = await fetch(`/api/v1/timeline/${postId}/like/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(
      userFacingMutationError(data.error || "like_failed", "いいねに失敗しました")
    );
  }
  return { liked: data.liked, like_count: data.like_count };
}

export async function toggleBookmark(postId: number): Promise<boolean> {
  const res = await fetch(`/api/v1/timeline/${postId}/bookmark/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "bookmark_failed");
  return Boolean(data.bookmarked);
}

export async function addComment(
  postId: number,
  body: string
): Promise<{ comment: TimelineComment; comment_count: number }> {
  const res = await fetch(`/api/v1/timeline/${postId}/comments/`, {
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
  if (!res.ok || !data.ok) {
    throw new Error(
      userFacingMutationError(
        data.error || "comment_failed",
        "コメントに失敗しました"
      )
    );
  }
  return { comment: data.comment, comment_count: data.comment_count };
}

export async function deletePost(postId: number): Promise<void> {
  const res = await fetch(`/api/v1/timeline/${postId}/`, {
    method: "DELETE",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "delete_failed");
}

export async function deleteComment(commentId: number): Promise<number> {
  const res = await fetch(`/api/v1/timeline/comments/${commentId}/`, {
    method: "DELETE",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "delete_comment_failed");
  return Number(data.comment_count || 0);
}

export async function fetchQuotable(
  postId: number
): Promise<TimelinePost> {
  const res = await fetch(`/api/v1/timeline/${postId}/quote/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "quote_failed");
  return data.quoted_post as TimelinePost;
}

/** Classic UGC report reasons (matches static/js/ugc_report.js). */
export const REPORT_REASONS = [
  { value: "spam", label: "スパム・宣伝" },
  { value: "harassment", label: "嫌がらせ・誹謗中傷" },
  { value: "inappropriate", label: "不適切な内容" },
  { value: "fraud", label: "詐欺・虚偽出品" },
  { value: "other", label: "その他" },
] as const;

export type ReportReason = (typeof REPORT_REASONS)[number]["value"];

/**
 * POST /report/<type>/<id>/ — reuses classic submit_report (JSON).
 * Sends moderation email via existing notify_moderation_team_of_report.
 */
export async function submitContentReport(
  targetType:
    | "post"
    | "comment"
    | "user"
    | "product"
    | "course_offering"
    | "course_review"
    | "chat_message",
  targetId: number,
  reason: ReportReason | string
): Promise<string> {
  const body = new URLSearchParams();
  body.set("reason", reason);
  const res = await fetch(`/report/${targetType}/${targetId}/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
      "X-CSRFToken": getCsrfToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body,
  });
  let data: { ok?: boolean; message?: string; error?: string } = {};
  try {
    data = await res.json();
  } catch {
    throw new Error(
      "通報に失敗しました。時間をおいてもう一度お試しください。"
    );
  }
  if (!res.ok || !data.ok) {
    throw new Error(
      userFacingMutationError(
        data.error || data.message || "通報に失敗しました。時間をおいてもう一度お試しください。",
        "通報に失敗しました。時間をおいてもう一度お試しください。"
      )
    );
  }
  return data.message || "通報しました";
}
