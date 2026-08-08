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
  const meta = document.querySelector('meta[name="csrf-token"]');
  const fromMeta = meta?.getAttribute("content");
  if (fromMeta) return fromMeta;
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export type FeedQuery = {
  feed?: "all" | "following";
  q?: string;
  faculty?: string;
  tag?: string;
  offset?: number;
};

function buildFeedUrl(query: FeedQuery): string {
  const params = new URLSearchParams();
  if (query.feed) params.set("feed", query.feed);
  if (query.q) params.set("q", query.q);
  if (query.faculty) params.set("faculty", query.faculty);
  if (query.tag) params.set("tag", query.tag);
  if (typeof query.offset === "number") {
    params.set("offset", String(query.offset));
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
    throw new Error(data.error || `compose_${res.status}`);
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
  if (!res.ok || !data.ok) throw new Error(data.error || "like_failed");
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
  if (!res.ok || !data.ok) throw new Error(data.error || "comment_failed");
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
