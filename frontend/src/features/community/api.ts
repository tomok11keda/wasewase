import { getCsrfToken } from "../timeline/api";

export type CommunityRef = {
  id: number;
  slug: string;
  name: string;
  description: string;
  faculty: string;
  category: string;
};

export type FacultyTab = { value: string; label: string };

export type CommunityAuthor = {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
} | null;

export type ThreadSummary = {
  id: number;
  title: string;
  body: string;
  body_preview: string;
  created_at: string;
  updated_at: string;
  replies_count: number;
  can_delete: boolean;
  author: CommunityAuthor;
  community: CommunityRef;
};

export type ReplyToPreview = {
  id: number;
  reply_number: number | null;
  display_name: string;
  is_unavailable: boolean;
} | null;

export type ThreadReply = {
  id: number;
  body: string;
  created_at: string;
  is_removed: boolean;
  reply_number: number | null;
  reply_to: ReplyToPreview;
  can_delete: boolean;
  can_edit: boolean;
  author: CommunityAuthor;
};

export type ThreadDetail = {
  id: number;
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
  can_delete: boolean;
  author: CommunityAuthor;
  community: CommunityRef;
  visible_reply_count: number;
  replies: ThreadReply[];
};

export type ThreadsListResponse = {
  threads: ThreadSummary[];
  faculty_tabs: FacultyTab[];
  active_tag: string;
  q: string;
  sort?: "recommended" | "latest";
};

export async function fetchCommunityThreads(query: {
  tag?: string;
  q?: string;
  sort?: "recommended" | "latest";
}): Promise<ThreadsListResponse> {
  const params = new URLSearchParams();
  if (query.tag) params.set("tag", query.tag);
  if (query.q) params.set("q", query.q);
  if (query.sort && query.sort !== "recommended") {
    params.set("sort", query.sort);
  }
  const qs = params.toString();
  const res = await fetch(
    qs ? `/api/v1/communities/threads/?${qs}` : "/api/v1/communities/threads/",
    { credentials: "same-origin", headers: { Accept: "application/json" } }
  );
  if (!res.ok) throw new Error(`threads_${res.status}`);
  return res.json();
}

export async function createCommunityThread(input: {
  title: string;
  body: string;
  tag?: string;
}): Promise<ThreadSummary> {
  const res = await fetch("/api/v1/communities/threads/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "create_failed");
  return data.thread as ThreadSummary;
}

export async function fetchThreadDetail(
  slug: string,
  threadPk: number
): Promise<ThreadDetail> {
  const res = await fetch(
    `/api/v1/communities/${slug}/threads/${threadPk}/`,
    { credentials: "same-origin", headers: { Accept: "application/json" } }
  );
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "detail_failed");
  return data.thread as ThreadDetail;
}

export async function createReply(
  slug: string,
  threadPk: number,
  body: string,
  replyToId?: number | null
): Promise<ThreadReply> {
  const res = await fetch(
    `/api/v1/communities/${slug}/threads/${threadPk}/replies/`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        body,
        ...(replyToId ? { reply_to_id: replyToId } : {}),
      }),
    }
  );
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "reply_failed");
  return data.reply as ThreadReply;
}

export async function deleteThread(slug: string, threadPk: number): Promise<void> {
  const res = await fetch(
    `/api/v1/communities/${slug}/threads/${threadPk}/delete/`,
    {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
    }
  );
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "delete_failed");
}

export async function deleteReply(
  slug: string,
  threadPk: number,
  replyPk: number
): Promise<void> {
  const res = await fetch(
    `/api/v1/communities/${slug}/threads/${threadPk}/replies/${replyPk}/delete/`,
    {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
    }
  );
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "delete_reply_failed");
}

export async function editReply(
  slug: string,
  threadPk: number,
  replyPk: number,
  body: string
): Promise<ThreadReply> {
  const res = await fetch(
    `/api/v1/communities/${slug}/threads/${threadPk}/replies/${replyPk}/`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ body }),
    }
  );
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "edit_failed");
  return data.reply as ThreadReply;
}
