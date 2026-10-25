import {
  isOrganizationTimelinePost,
  type OrganizationPostLike,
} from "./organizationActor.ts";

export const ORGANIZATION_POST_VISIBILITY = {
  public: "public",
  draft: "draft",
  unlisted: "unlisted",
} as const;

export type OrganizationPostVisibility =
  (typeof ORGANIZATION_POST_VISIBILITY)[keyof typeof ORGANIZATION_POST_VISIBILITY];

export const DEFAULT_ORGANIZATION_COMPOSE_VISIBILITY =
  ORGANIZATION_POST_VISIBILITY.draft;

export type OrganizationPostVisibilityLike = OrganizationPostLike & {
  visibility?: string | null;
};

export function isPublicOrganizationPost(
  post: OrganizationPostVisibilityLike | null | undefined
): boolean {
  return (
    isOrganizationTimelinePost(post) &&
    post?.visibility === ORGANIZATION_POST_VISIBILITY.public
  );
}

export function isUnpublishedOrganizationPost(
  post: OrganizationPostVisibilityLike | null | undefined
): boolean {
  if (!isOrganizationTimelinePost(post)) return false;
  return post?.visibility !== ORGANIZATION_POST_VISIBILITY.public;
}

export function organizationPostVisibilityLabel(
  visibility: string | null | undefined
): string {
  if (visibility === ORGANIZATION_POST_VISIBILITY.public) return "公開";
  if (visibility === ORGANIZATION_POST_VISIBILITY.draft) return "下書き";
  if (visibility === ORGANIZATION_POST_VISIBILITY.unlisted) return "非公開";
  if (visibility === "organization_preview") return "非公開";
  return "";
}

export function composeNoticeForOrganizationPost(input: {
  unpublished: boolean;
  organizationName: string;
}): string {
  const name = input.organizationName.trim() || "団体";
  if (input.unpublished) {
    return `「${name}」の下書きを保存しました。一般のタイムラインと検索には出ません。団体プロフィールの下書き一覧で確認できます。`;
  }
  return `「${name}」として公開しました。タイムラインと検索、団体プロフィールに表示されます。`;
}
