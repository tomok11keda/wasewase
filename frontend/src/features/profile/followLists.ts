import { normalizeSpaPath } from "../../lib/tabs.ts";

export const FOLLOW_LIST_KINDS = ["mutuals", "followers", "following"] as const;

export type FollowListKind = (typeof FOLLOW_LIST_KINDS)[number];

export type FollowListUser = {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
  is_operator_verified?: boolean | null;
};

export const FOLLOW_LIST_TABS: Array<{ kind: FollowListKind; label: string }> = [
  { kind: "mutuals", label: "共通の友達" },
  { kind: "followers", label: "フォロワー" },
  { kind: "following", label: "フォロー中" },
];

export function followListKindFromPath(pathname: string): FollowListKind {
  const p = normalizeSpaPath(pathname);
  if (p.endsWith("/following")) return "following";
  if (p.endsWith("/mutuals")) return "mutuals";
  return "followers";
}

export function followListPath(userId: number, kind: FollowListKind): string {
  return `/users/${userId}/${kind}`;
}

export function followListTitle(kind: FollowListKind): string {
  if (kind === "following") return "フォロー中";
  if (kind === "mutuals") return "共通の友達";
  return "フォロワー";
}

export function followListEmptyCopy(kind: FollowListKind): string {
  if (kind === "following") return "フォロー中はまだいません";
  if (kind === "mutuals") return "共通の友達はまだいません";
  return "フォロワーはまだいません";
}

export function followListForbiddenCopy(): string {
  return "非公開アカウントか、表示できない関係です。";
}

export function followListLoadErrorCopy(error: string | null): string {
  if (
    error === "follow_list_404" ||
    error === "http_404" ||
    error === "not_found"
  ) {
    return "このユーザーは見つかりません。";
  }
  return "一覧を表示できません。";
}
