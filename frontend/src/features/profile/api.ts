import { getCsrfToken } from "../timeline/api";
import type { TimelinePost } from "../timeline/api";
import type { ProductCard } from "../flea/api";

export type FollowState =
  | "self"
  | "following"
  | "requested"
  | "none"
  | "blocked";

export type ProfileUser = {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
  bio: string;
  department: string;
  grade: string;
  department_grade: string;
};

export type ProfilePayload = {
  ok: boolean;
  user: ProfileUser;
  stats: {
    post_count: number;
    product_count: number;
    follower_count: number;
    following_count: number;
    left_label: string;
    left_count: number;
  };
  is_own: boolean;
  is_following: boolean;
  is_private: boolean;
  follow_state: FollowState;
  can_view_content: boolean;
  is_blocked: boolean;
  can_send_dm: boolean;
  dm_room_id: number | null;
  show_safety_menu: boolean;
  can_view_timetable: boolean;
  is_timetable_public: boolean;
  can_view_bookmarks: boolean;
};

export type SearchTab = "all" | "latest" | "users";

export type SearchPageResponse = {
  ok: boolean;
  q: string;
  tab: SearchTab;
  posts: TimelinePost[];
  users: ProfileUser[];
  post_count: number;
  user_count: number;
};

export type ScopedSearchResult = {
  type: "post" | "thread" | "product";
  id: number;
  title: string;
  subtitle: string;
  meta: string;
  url: string;
};

export async function fetchProfile(pk: number): Promise<ProfilePayload> {
  const res = await fetch(`/api/v1/profile/${pk}/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || `profile_${res.status}`);
  const payload = data as ProfilePayload;
  const followState =
    payload.follow_state ||
    (payload.is_own
      ? "self"
      : payload.is_blocked
        ? "blocked"
        : payload.is_following
          ? "following"
          : "none");
  return {
    ...payload,
    is_private: Boolean(payload.is_private),
    follow_state: followState,
    // Missing can_view_content: infer safely (public / own / following → true).
    can_view_content:
      typeof payload.can_view_content === "boolean"
        ? payload.can_view_content
        : Boolean(
            payload.is_own ||
              !payload.is_private ||
              payload.is_following
          ),
  };
}

export async function fetchProfilePosts(pk: number): Promise<TimelinePost[]> {
  const res = await fetch(`/api/v1/profile/${pk}/posts/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "posts_failed");
  return data.posts as TimelinePost[];
}

export async function fetchProfileProducts(pk: number): Promise<ProductCard[]> {
  const res = await fetch(`/api/v1/profile/${pk}/products/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "products_failed");
  return data.products as ProductCard[];
}

export async function fetchProfileBookmarks(pk: number): Promise<TimelinePost[]> {
  const res = await fetch(`/api/v1/profile/${pk}/bookmarks/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "bookmarks_failed");
  return data.posts as TimelinePost[];
}

export async function toggleFollow(pk: number): Promise<{
  is_following: boolean;
  follow_state: FollowState;
  follower_count: number;
  action?: string;
}> {
  const res = await fetch(`/api/v1/profile/${pk}/follow/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "follow_failed");
  return {
    is_following: Boolean(data.is_following),
    follow_state: (data.follow_state ||
      (data.is_following ? "following" : "none")) as FollowState,
    follower_count: Number(data.follower_count || 0),
    action: data.action ? String(data.action) : undefined,
  };
}

export async function toggleBlock(pk: number): Promise<{ is_blocked: boolean }> {
  const res = await fetch(`/api/v1/profile/${pk}/block/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "block_failed");
  return { is_blocked: Boolean(data.is_blocked) };
}

export type FollowRequestItem = {
  id: number;
  created_at: string;
  from_user: {
    id: number;
    username: string;
    display_name: string;
    avatar_url: string;
    initial: string;
  };
};

export async function fetchFollowRequests(): Promise<FollowRequestItem[]> {
  const res = await fetch("/api/v1/follow-requests/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "follow_requests_failed");
  return (data.requests || []) as FollowRequestItem[];
}

export async function acceptFollowRequest(
  id: number
): Promise<{ ok: boolean; follower_count?: number }> {
  const res = await fetch(`/api/v1/follow-requests/${id}/accept/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "accept_failed");
  return data;
}

export async function rejectFollowRequest(id: number): Promise<{ ok: boolean }> {
  const res = await fetch(`/api/v1/follow-requests/${id}/reject/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "reject_failed");
  return data;
}

export async function updatePrivacy(isPrivate: boolean): Promise<{
  is_private: boolean;
  auto_accepted_requests: number;
}> {
  const res = await fetch("/api/v1/me/privacy/", {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
    },
    body: JSON.stringify({ is_private: isPrivate }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "privacy_failed");
  return {
    is_private: Boolean(data.is_private),
    auto_accepted_requests: Number(data.auto_accepted_requests || 0),
  };
}

export async function fetchSearchPage(query: {
  q?: string;
  tab?: SearchTab;
}): Promise<SearchPageResponse> {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.tab) params.set("tab", query.tab);
  const qs = params.toString();
  const res = await fetch(qs ? `/api/v1/search/?${qs}` : "/api/v1/search/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "search_failed");
  return data as SearchPageResponse;
}

/** Existing scoped search used by classic search bar. */
export async function fetchScopedSearch(query: {
  q: string;
  scope?: "home" | "communities" | "flea";
  faculty?: string;
}): Promise<{ results: ScopedSearchResult[]; count: number }> {
  const params = new URLSearchParams();
  params.set("q", query.q);
  if (query.scope) params.set("scope", query.scope);
  if (query.faculty) params.set("faculty", query.faculty);
  const res = await fetch(`/api/search/?${params.toString()}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`scoped_search_${res.status}`);
  return res.json();
}

export function spaPathForScopedResult(item: ScopedSearchResult): string | null {
  if (item.type === "post") return `/#post-${item.id}`;
  if (item.type === "thread") {
    // Classic URL; keep as full navigation if not SPA-mapped easily
    return null;
  }
  if (item.type === "product") return `/flea/products/${item.id}`;
  return null;
}

const SCROLL_KEY = "wase-spa-scroll";

export function saveScrollPosition(pathKey: string): void {
  try {
    sessionStorage.setItem(
      `${SCROLL_KEY}:${pathKey}`,
      String(window.scrollY || 0)
    );
  } catch {
    /* ignore */
  }
}

export function restoreScrollPosition(pathKey: string): void {
  try {
    const raw = sessionStorage.getItem(`${SCROLL_KEY}:${pathKey}`);
    if (raw == null) return;
    const y = Number(raw);
    if (!Number.isFinite(y)) return;
    window.requestAnimationFrame(() => {
      window.scrollTo(0, y);
    });
  } catch {
    /* ignore */
  }
}
