import type { SearchThreadResult } from "../profile/api";
import type { ThreadDetail, ThreadSummary } from "./api";

export type CommunityThreadNavState = {
  initialThread?: ThreadSummary;
};

/** Strip permission flags; keep only fields the list already showed publicly. */
export function publicThreadPreview(thread: ThreadSummary): ThreadSummary {
  return {
    ...thread,
    can_delete: false,
    is_mine: false,
    can_report: false,
  };
}

export function communityThreadDetailState(
  thread: ThreadSummary
): CommunityThreadNavState {
  return { initialThread: publicThreadPreview(thread) };
}

export function threadSummaryFromSearch(
  thread: SearchThreadResult
): ThreadSummary {
  return publicThreadPreview({
    id: thread.id,
    title: thread.title,
    body: thread.body,
    body_preview: thread.body_preview,
    created_at: thread.created_at,
    updated_at: thread.updated_at,
    replies_count: thread.replies_count,
    can_delete: false,
    is_mine: false,
    can_report: Boolean(thread.can_report),
    anonymous_number: thread.anonymous_number,
    anonymous_label: thread.anonymous_label || "",
    community: {
      id: thread.community.id,
      slug: thread.community.slug,
      name: thread.community.name,
      description: "",
      faculty: thread.community.faculty || "",
      category: "",
    },
  });
}

export function threadDetailFromSummary(thread: ThreadSummary): ThreadDetail {
  return {
    id: thread.id,
    title: thread.title,
    body: thread.body || thread.body_preview,
    created_at: thread.created_at,
    updated_at: thread.updated_at,
    can_delete: false,
    is_mine: false,
    can_report: false,
    anonymous_number: thread.anonymous_number,
    anonymous_label: thread.anonymous_label,
    community: thread.community,
    visible_reply_count: thread.replies_count,
    replies: [],
  };
}

export function readInitialThread(
  state: unknown,
  threadPk: number
): ThreadDetail | null {
  if (!state || typeof state !== "object") return null;
  const raw = (state as CommunityThreadNavState).initialThread;
  if (!raw || raw.id !== threadPk) return null;
  return threadDetailFromSummary(publicThreadPreview(raw));
}
