import {
  draftsFromLinks,
  parseProfileLinks,
  seedLinksFromLegacyUrls,
  type ProfileLinkDraft,
  type ProfileLinkItem,
  validateProfileLinkDrafts,
} from "../profileLinks/profileLinks.ts";
import type { RecruitingChatSummary } from "./recruitingChat.ts";
import { parseRecruitingChatSummary } from "./recruitingChat.ts";

export const ORGANIZATION_NAME_MAX = 100;
export const ORGANIZATION_DESCRIPTION_MAX = 5000;
export const ORGANIZATION_URL_MAX = 200;
export const ORGANIZATION_AVATAR_MAX_BYTES = 5 * 1024 * 1024;

export const ORGANIZATION_CATEGORIES = [
  { value: "circle", label: "サークル" },
  { value: "student_group", label: "学生団体" },
  { value: "committee", label: "委員会・実行委員会" },
  { value: "project", label: "プロジェクト" },
  { value: "other", label: "その他" },
] as const;

export type OrganizationCategory =
  (typeof ORGANIZATION_CATEGORIES)[number]["value"];

const CATEGORY_VALUES = new Set<string>(
  ORGANIZATION_CATEGORIES.map((item) => item.value)
);

const ALLOWED_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
]);
const ALLOWED_IMAGE_EXTS = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp"]);
const HEIC_EXTS = new Set([".heic", ".heif"]);

export type OrganizationProfile = {
  id: number;
  name: string;
  slug: string;
  description: string;
  avatar_url: string;
  category: string;
  instagram_url: string;
  website_url: string;
  is_verified: boolean;
  links: ProfileLinkItem[];
};

export type OrganizationProfilePayload = {
  ok: boolean;
  organization: OrganizationProfile;
  can_manage: boolean;
  my_role: string | null;
  recruiting_chat: RecruitingChatSummary | null;
  recruiting_chats: RecruitingChatSummary[];
};

export type OrganizationProfileForm = {
  name: string;
  description: string;
  category: string;
  instagram_url: string;
  website_url: string;
  links: ProfileLinkDraft[];
};

export function organizationCategoryLabel(category: string): string {
  const found = ORGANIZATION_CATEGORIES.find((item) => item.value === category);
  return found?.label || category;
}

export function organizationInitial(name: string): string {
  const trimmed = name.trim();
  return trimmed ? trimmed.slice(0, 1) : "?";
}

export function isSafeHttpUrl(value: string): boolean {
  const raw = value.trim();
  if (!raw) return false;
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function organizationExternalHref(value: string): string | null {
  const raw = value.trim();
  if (!raw || raw.length > ORGANIZATION_URL_MAX) return null;
  return isSafeHttpUrl(raw) ? raw : null;
}

function fileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export function validateOrganizationAvatar(
  file: File
): string | null {
  const ext = fileExtension(file.name || "");
  const type = (file.type || "").toLowerCase();
  if (HEIC_EXTS.has(ext) || type === "image/heic" || type === "image/heif") {
    return "HEIC形式は現在非対応です。JPEG または PNG に変換してからアップロードしてください。";
  }
  if (file.size <= 0) {
    return "画像ファイルが空です。";
  }
  if (file.size > ORGANIZATION_AVATAR_MAX_BYTES) {
    return "画像は5MB以下にしてください。";
  }
  if (!ALLOWED_IMAGE_TYPES.has(type) && !ALLOWED_IMAGE_EXTS.has(ext)) {
    return "画像ファイル（JPEG・PNG・GIF・WebP）を選択してください。";
  }
  return null;
}

export function validateOrganizationProfileForm(
  form: OrganizationProfileForm
): Record<string, string> {
  const errors: Record<string, string> = {};
  const name = form.name.trim();
  if (!name) {
    errors.name = "団体名を入力してください。";
  } else if (name.length > ORGANIZATION_NAME_MAX) {
    errors.name = `団体名は${ORGANIZATION_NAME_MAX}文字以内で入力してください。`;
  }

  const description = form.description.trim();
  if (description.length > ORGANIZATION_DESCRIPTION_MAX) {
    errors.description = `団体説明は${ORGANIZATION_DESCRIPTION_MAX}文字以内で入力してください。`;
  }

  if (!CATEGORY_VALUES.has(form.category)) {
    errors.category = "カテゴリを選択してください。";
  }

  const instagram = form.instagram_url.trim();
  if (instagram) {
    if (instagram.length > ORGANIZATION_URL_MAX || !isSafeHttpUrl(instagram)) {
      errors.instagram_url = "Instagram URLの形式が正しくありません。";
    }
  }
  const website = form.website_url.trim();
  if (website) {
    if (website.length > ORGANIZATION_URL_MAX || !isSafeHttpUrl(website)) {
      errors.website_url = "Webサイト URLの形式が正しくありません。";
    }
  }
  Object.assign(errors, validateProfileLinkDrafts(form.links || []));
  return errors;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function parseOrganizationProfilePayload(
  data: Record<string, unknown>
): OrganizationProfilePayload | null {
  const raw = data.organization;
  if (!raw || typeof raw !== "object") return null;
  const org = raw as Record<string, unknown>;
  const id = Number(org.id);
  const name = asString(org.name).trim();
  const slug = asString(org.slug).trim();
  if (!Number.isFinite(id) || !name || !slug) return null;
  const role = data.my_role;
  return {
    ok: true,
    organization: {
      id,
      name,
      slug,
      description: asString(org.description),
      avatar_url: asString(org.avatar_url),
      category: asString(org.category) || "other",
      instagram_url: asString(org.instagram_url),
      website_url: asString(org.website_url),
      is_verified: org.is_verified === true,
      links: Array.isArray(org.links)
        ? parseProfileLinks(org.links)
        : seedLinksFromLegacyUrls(
            asString(org.instagram_url),
            asString(org.website_url)
          ),
    },
    can_manage: data.can_manage === true,
    my_role: typeof role === "string" && role ? role : null,
    recruiting_chat: parseRecruitingChatSummary(data.recruiting_chat),
    recruiting_chats: Array.isArray(data.recruiting_chats)
      ? data.recruiting_chats
          .map(parseRecruitingChatSummary)
          .filter((row): row is RecruitingChatSummary => row != null)
      : [],
  };
}

export function formFromOrganization(
  organization: OrganizationProfile
): OrganizationProfileForm {
  return {
    name: organization.name,
    description: organization.description,
    category: CATEGORY_VALUES.has(organization.category)
      ? organization.category
      : "other",
    instagram_url: organization.instagram_url,
    website_url: organization.website_url,
    links: draftsFromLinks(organization.links || []),
  };
}

export function firstFieldError(
  errors: Record<string, unknown> | undefined
): Record<string, string> {
  const mapped: Record<string, string> = {};
  if (!errors) return mapped;
  for (const [key, value] of Object.entries(errors)) {
    if (Array.isArray(value) && typeof value[0] === "string" && value[0]) {
      mapped[key] = value[0];
    } else if (typeof value === "string" && value) {
      mapped[key] = value;
    }
  }
  return mapped;
}
