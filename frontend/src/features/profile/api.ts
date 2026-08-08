import { getCsrfToken } from "../timeline/api";
import type { TimelinePost } from "../timeline/api";
import type { ProductCard } from "../flea/api";

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
  return data as ProfilePayload;
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

export async function toggleFollow(
  pk: number
): Promise<{ is_following: boolean; follower_count: number }> {
  const res = await fetch(`/api/v1/profile/${pk}/follow/`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "follow_failed");
  return {
    is_following: Boolean(data.is_following),
    follower_count: Number(data.follower_count || 0),
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
