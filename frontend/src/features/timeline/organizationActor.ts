import { organizationInitial } from "../orgs/orgProfile.ts";

export const ORGANIZATION_ACTOR_TYPE = "organization";
export const ORGANIZATION_KIND_LABEL = "学生団体";

export type TimelineOrganizationActor = {
  id: number;
  name: string;
  slug: string;
  avatar_url: string;
  is_verified: boolean;
};

export type OrganizationPostLike = {
  actor_type?: string | null;
  organization?: TimelineOrganizationActor | null;
  author?: {
    id?: number | null;
    username?: string;
    display_name?: string;
  } | null;
};

export type OrganizationPostDisplay = {
  name: string;
  slug: string;
  href: string | null;
  avatarUrl: string;
  initial: string;
  isVerified: boolean;
  kindLabel: string;
};

export function isOrganizationTimelinePost(
  post: OrganizationPostLike | null | undefined
): boolean {
  if (!post) return false;
  if (post.actor_type === ORGANIZATION_ACTOR_TYPE) return true;
  return Boolean(post.organization && post.organization.id);
}

export function organizationProfilePath(slug: string): string {
  const trimmed = slug.trim();
  return trimmed ? `/orgs/${trimmed}` : "";
}

export function organizationPostDisplay(
  post: OrganizationPostLike | null | undefined
): OrganizationPostDisplay | null {
  if (!isOrganizationTimelinePost(post)) return null;
  const org = post?.organization;
  const name = (org?.name || "").trim();
  if (!org || !name) {
    return {
      name: ORGANIZATION_KIND_LABEL,
      slug: "",
      href: null,
      avatarUrl: "",
      initial: "団",
      isVerified: false,
      kindLabel: "",
    };
  }
  const slug = (org.slug || "").trim();
  return {
    name,
    slug,
    href: slug ? organizationProfilePath(slug) : null,
    avatarUrl: org.avatar_url || "",
    initial: organizationInitial(name),
    isVerified: org.is_verified === true,
    kindLabel: ORGANIZATION_KIND_LABEL,
  };
}

/** 団体投稿を「削除済みユーザー」と誤判定しない。 */
export function isDeletedPersonalAuthor(
  post: OrganizationPostLike | null | undefined
): boolean {
  if (isOrganizationTimelinePost(post)) return false;
  return !post?.author;
}

export function organizationPostLeaksOperator(
  post: OrganizationPostLike | null | undefined
): boolean {
  if (!isOrganizationTimelinePost(post)) return false;
  const author = post?.author;
  if (!author) return false;
  return Boolean(author.id || author.username || author.display_name);
}
