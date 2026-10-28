import { userFacingMutationError } from "../../lib/rateLimit";

export type TimelineAuthor = {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
  is_operator_verified?: boolean | null;
} | null;

export type TimelineOrganization = {
  id: number;
  name: string;
  slug: string;
  avatar_url: string;
  is_verified: boolean;
};

export type TimelineCommentReplyTo = {
  id: number;
  username: string;
  display_name: string;
  is_unavailable: boolean;
  is_operator_verified?: boolean | null;
};

export type TimelineComment = {
  id: number;
  body: string;
  created_at: string;
  can_delete: boolean;
  author: TimelineAuthor;
  parent_comment_id: number | null;
  reply_to: TimelineCommentReplyTo | null;
  is_deleted: boolean;
  reply_count: number;
};

export type QuotedPost = {
  id: number;
  is_removed: boolean;
  body: string;
  author: TimelineAuthor;
  image_url: string | null;
  course_name: string;
  actor_type?: "organization" | string | null;
  organization?: TimelineOrganization | null;
} | null;

export type SharedProduct = {
  id: number;
  name: string;
  price: number;
  image_url: string;
  status: string;
  is_sold: boolean;
  is_pending: boolean;
};

export type SharedOrganizationEvent = {
  id: number;
  organization_id: number;
  organization_slug: string;
  organization_name: string;
  title: string;
  starts_at: string | null;
  ends_at: string | null;
  venue_name: string;
  signup_mode: string;
  status: string;
  status_label: string;
  path: string;
};

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
  actor_type?: "organization" | string | null;
  organization?: TimelineOrganization | null;
  visibility?: "public" | "draft" | "unlisted" | "organization_preview" | string | null;
  quoted_post: QuotedPost;
  shared_product: SharedProduct | null;
  shared_organization_event?: SharedOrganizationEvent | null;
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

export { HOME_TIMELINE_SORT } from "./homeFeed";

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
  if (query.sort) {
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

export async function fetchTimelinePost(postId: number): Promise<TimelinePost> {
  const res = await fetch(`/api/v1/timeline/${postId}/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  let data: { ok?: boolean; post?: TimelinePost; error?: string } = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (!res.ok || !data.ok || !data.post) {
    throw new Error("この投稿は表示できません");
  }
  const post = data.post;
  return {
    ...post,
    comments: post.comments || [],
  };
}

export async function createTimelinePost(input: {
  body: string;
  image?: File | null;
  quoted_post_id?: number | null;
  organization_id?: number | null;
  visibility?: "public" | "draft" | string | null;
}): Promise<TimelinePost> {
  const form = new FormData();
  form.append("body", input.body);
  if (input.image) form.append("image", input.image);
  if (input.quoted_post_id) {
    form.append("quoted_post_id", String(input.quoted_post_id));
  }
  if (
    typeof input.organization_id === "number" &&
    Number.isInteger(input.organization_id) &&
    input.organization_id > 0
  ) {
    form.append("organization_id", String(input.organization_id));
    if (input.visibility === "public" || input.visibility === "draft") {
      form.append("visibility", input.visibility);
    }
  }
  const res = await fetch("/api/v1/timeline/", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken() },
    body: form,
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    const code = String(data.error || `compose_${res.status}`);
    if (code === "forbidden") {
      throw new Error(
        "この団体名義では投稿できません。権限を確認してください。個人名義への切り替えは自動では行いません。"
      );
    }
    if (code === "organization_not_found") {
      throw new Error(
        "指定された団体が見つかりません。個人名義への切り替えは自動では行いません。"
      );
    }
    if (code === "invalid_visibility") {
      throw new Error("公開範囲を選択してください。");
    }
    throw new Error(
      userFacingMutationError(code, "投稿に失敗しました")
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

export async function fetchTimelineLikers(
  postId: number,
  signal?: AbortSignal
): Promise<{
  users: NonNullable<TimelineAuthor>[];
  count: number;
  has_more: boolean;
}> {
  const res = await fetch(`/api/v1/timeline/${postId}/likers/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  let data: {
    ok?: boolean;
    users?: NonNullable<TimelineAuthor>[];
    count?: number;
    has_more?: boolean;
    error?: string;
  } = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (res.status === 401 || res.status === 403) {
    throw new Error("unauthorized");
  }
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "この投稿は表示できません");
  }
  return {
    users: (data.users || []).filter((u) => u && u.id),
    count: Number(data.count || 0),
    has_more: Boolean(data.has_more),
  };
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
  body: string,
  parentCommentId?: number | null
): Promise<{ comment: TimelineComment; comment_count: number }> {
  const payload: { body: string; parent_comment_id?: number } = { body };
  if (parentCommentId) {
    payload.parent_comment_id = parentCommentId;
  }
  const res = await fetch(`/api/v1/timeline/${postId}/comments/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
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
  if (!res.ok || !data.ok) {
    const code = String(data.error || "delete_failed");
    throw new Error(
      userFacingMutationError(
        code,
        code === "forbidden"
          ? "この投稿を削除する権限がありません。"
          : "削除に失敗しました"
      )
    );
  }
}

export async function updateTimelinePostVisibility(
  postId: number,
  visibility: "public" | "draft"
): Promise<TimelinePost> {
  const res = await fetch(`/api/v1/timeline/${postId}/visibility/`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify({ visibility }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok || !data.post) {
    const code = String(data.error || "visibility_update_failed");
    throw new Error(
      userFacingMutationError(
        code,
        code === "forbidden"
          ? "この投稿の公開範囲を変更する権限がありません。"
          : code === "invalid_visibility"
            ? "公開範囲を選択してください。"
            : "公開範囲の更新に失敗しました"
      )
    );
  }
  return data.post as TimelinePost;
}

export async function deleteComment(
  commentId: number
): Promise<{ comment_count: number; comment: TimelineComment | null }> {
  const res = await fetch(`/api/v1/timeline/comments/${commentId}/`, {
    method: "DELETE",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "delete_comment_failed");
  return {
    comment_count: Number(data.comment_count || 0),
    comment: data.comment ?? null,
  };
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
    | "chat_message"
    | "community_thread"
    | "community_reply",
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
