import {
  apiGetJson,
  apiPatchForm,
  apiPatchJson,
  mutationErrorMessage,
} from "../../lib/http";
import type { TimelinePost } from "../timeline/api";
import {
  parseManagedOrganizationsPayload,
  type ManagedOrganization,
} from "./managedOrganizations";
import {
  firstFieldError,
  parseOrganizationProfilePayload,
  type OrganizationProfileForm,
  type OrganizationProfilePayload,
} from "./orgProfile";

export class OrganizationRequestError extends Error {
  status: number;
  code: string;
  fieldErrors: Record<string, string>;
  extra: Record<string, unknown>;

  constructor(
    code: string,
    status: number,
    message: string,
    fieldErrors: Record<string, string> = {},
    extra: Record<string, unknown> = {}
  ) {
    super(message);
    this.name = "OrganizationRequestError";
    this.code = code;
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.extra = extra;
  }
}

function organizationUrl(slug: string): string {
  return `/api/v1/organizations/${encodeURIComponent(slug)}/`;
}

function throwFromResult(
  status: number,
  error: string | undefined,
  data: Record<string, unknown>,
  fallback: string
): never {
  const fieldErrors = firstFieldError(
    data.errors as Record<string, unknown> | undefined
  );
  const code = error || `http_${status}`;
  throw new OrganizationRequestError(
    code,
    status,
    mutationErrorMessage(code, fallback),
    fieldErrors
  );
}

export async function fetchOrganizationProfile(
  slug: string
): Promise<OrganizationProfilePayload> {
  const result = await apiGetJson(organizationUrl(slug));
  if (result.status === 404 || result.error === "not_found") {
    throw new OrganizationRequestError(
      "not_found",
      404,
      "この団体は見つからないか、表示できません。"
    );
  }
  if (result.status === 401 || result.error === "unauthorized") {
    throw new OrganizationRequestError(
      "unauthorized",
      401,
      "ログインが必要です。"
    );
  }
  if (!result.ok) {
    throwFromResult(
      result.status,
      result.error,
      result.data,
      "団体プロフィールを読み込めませんでした。"
    );
  }
  const payload = parseOrganizationProfilePayload(result.data);
  if (!payload) {
    throw new OrganizationRequestError(
      "invalid_payload",
      result.status,
      "団体プロフィールを読み込めませんでした。"
    );
  }
  return payload;
}

export async function updateOrganizationProfile(
  slug: string,
  form: OrganizationProfileForm,
  avatar: File | null
): Promise<OrganizationProfilePayload> {
  const fields = {
    name: form.name.trim(),
    description: form.description.trim(),
    category: form.category,
    instagram_url: form.instagram_url.trim(),
    website_url: form.website_url.trim(),
  };
  const result = avatar
    ? await apiPatchForm(
        organizationUrl(slug),
        (() => {
          const body = new FormData();
          body.set("name", fields.name);
          body.set("description", fields.description);
          body.set("category", fields.category);
          body.set("instagram_url", fields.instagram_url);
          body.set("website_url", fields.website_url);
          body.set("avatar", avatar);
          return body;
        })()
      )
    : await apiPatchJson(organizationUrl(slug), fields);

  if (result.status === 401 || result.error === "unauthorized") {
    throw new OrganizationRequestError(
      "unauthorized",
      401,
      "ログインが必要です。"
    );
  }
  if (result.error === "csrf_failed") {
    throw new OrganizationRequestError(
      "csrf_failed",
      403,
      "保存に失敗しました。画面を再読み込みしてからもう一度お試しください。"
    );
  }
  if (result.status === 403 || result.error === "forbidden") {
    throw new OrganizationRequestError(
      "forbidden",
      403,
      "この団体を編集する権限がありません。"
    );
  }
  if (result.status === 404 || result.error === "not_found") {
    throw new OrganizationRequestError(
      "not_found",
      404,
      "この団体は見つからないか、表示できません。"
    );
  }
  if (!result.ok) {
    throwFromResult(
      result.status,
      result.error,
      result.data,
      "保存に失敗しました。入力内容を確認してください。"
    );
  }
  const payload = parseOrganizationProfilePayload(result.data);
  if (!payload) {
    throw new OrganizationRequestError(
      "invalid_payload",
      result.status,
      "保存結果を読み込めませんでした。"
    );
  }
  return payload;
}

export type OrganizationPostsPayload = {
  posts: TimelinePost[];
  has_more: boolean;
  next_offset: number;
  total_count: number;
  preview: boolean;
  unpublished: boolean;
  scope?: "public" | "unpublished" | string;
  public_count?: number;
  unpublished_count?: number;
};

export async function fetchOrganizationPosts(
  slug: string,
  offset = 0,
  scope?: "public" | "unpublished" | string
): Promise<OrganizationPostsPayload> {
  const params = new URLSearchParams();
  if (offset > 0) params.set("offset", String(offset));
  if (scope === "unpublished" || scope === "public") {
    params.set("scope", scope);
  }
  const qs = params.toString();
  const result = await apiGetJson(
    `/api/v1/organizations/${encodeURIComponent(slug)}/posts/${qs ? `?${qs}` : ""}`
  );
  if (result.status === 404 || result.error === "not_found") {
    throw new OrganizationRequestError(
      "not_found",
      404,
      "この団体は見つからないか、表示できません。"
    );
  }
  if (result.status === 401 || result.error === "unauthorized") {
    throw new OrganizationRequestError(
      "unauthorized",
      401,
      "ログインが必要です。"
    );
  }
  if (!result.ok) {
    throwFromResult(
      result.status,
      result.error,
      result.data,
      "団体の投稿を読み込めませんでした。"
    );
  }
  const posts = Array.isArray(result.data.posts)
    ? (result.data.posts as TimelinePost[])
    : [];
  return {
    posts,
    has_more: result.data.has_more === true,
    next_offset: Number(result.data.next_offset || 0),
    total_count: Number(result.data.total_count || 0),
    preview: result.data.preview === true,
    unpublished: result.data.unpublished === true,
    scope:
      result.data.scope === "unpublished" || result.data.scope === "public"
        ? result.data.scope
        : undefined,
    public_count:
      typeof result.data.public_count === "number"
        ? result.data.public_count
        : undefined,
    unpublished_count:
      typeof result.data.unpublished_count === "number"
        ? result.data.unpublished_count
        : undefined,
  };
}

export async function fetchManagedOrganizations(): Promise<ManagedOrganization[]> {
  const result = await apiGetJson("/api/v1/me/organizations/");
  if (result.status === 401 || result.error === "unauthorized") {
    throw new OrganizationRequestError(
      "unauthorized",
      401,
      "ログインが必要です。"
    );
  }
  if (!result.ok) {
    throwFromResult(
      result.status,
      result.error,
      result.data,
      "管理団体一覧を読み込めませんでした。"
    );
  }
  const organizations = parseManagedOrganizationsPayload(result.data);
  if (!organizations) {
    throw new OrganizationRequestError(
      "invalid_payload",
      result.status,
      "管理団体一覧を読み込めませんでした。"
    );
  }
  return organizations;
}
