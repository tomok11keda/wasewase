import {
  apiGetJson,
  apiPatchForm,
  apiPatchJson,
} from "../../lib/http";
import {
  firstFieldError,
  parseOwnProfilePayload,
  type OwnProfileForm,
  type OwnProfilePayload,
} from "./meProfile";

export class OwnProfileRequestError extends Error {
  status: number;
  code: string;
  fieldErrors: Record<string, string>;

  constructor(
    code: string,
    status: number,
    message: string,
    fieldErrors: Record<string, string> = {}
  ) {
    super(message);
    this.name = "OwnProfileRequestError";
    this.code = code;
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

const ME_PROFILE_URL = "/api/v1/me/profile/";

function throwFromResult(
  status: number,
  error: string | undefined,
  data: Record<string, unknown>,
  fallback: string
): never {
  const fieldErrors = firstFieldError(
    data.errors as Record<string, unknown> | undefined
  );
  throw new OwnProfileRequestError(
    error || `http_${status}`,
    status,
    fallback,
    fieldErrors
  );
}

export async function fetchOwnProfile(): Promise<OwnProfilePayload> {
  const result = await apiGetJson(ME_PROFILE_URL);
  if (result.status === 401 || result.error === "unauthorized") {
    throw new OwnProfileRequestError("unauthorized", 401, "ログインが必要です。");
  }
  if (!result.ok) {
    throwFromResult(
      result.status,
      result.error,
      result.data,
      "プロフィールを読み込めませんでした。"
    );
  }
  const payload = parseOwnProfilePayload(result.data);
  if (!payload) {
    throw new OwnProfileRequestError(
      "invalid_payload",
      result.status,
      "プロフィールを読み込めませんでした。"
    );
  }
  return payload;
}

export async function updateOwnProfile(
  form: OwnProfileForm,
  avatar: File | null
): Promise<OwnProfilePayload> {
  const fields = {
    name: form.name,
    bio: form.bio,
    user_id: form.user_id.trim().replace(/^@/, ""),
    department: form.department,
    grade: form.grade,
  };
  const result = avatar
    ? await apiPatchForm(
        ME_PROFILE_URL,
        (() => {
          const body = new FormData();
          body.set("name", fields.name);
          body.set("bio", fields.bio);
          body.set("user_id", fields.user_id);
          body.set("department", fields.department);
          body.set("grade", fields.grade);
          body.set("avatar", avatar);
          return body;
        })()
      )
    : await apiPatchJson(ME_PROFILE_URL, fields);

  if (result.status === 401 || result.error === "unauthorized") {
    throw new OwnProfileRequestError("unauthorized", 401, "ログインが必要です。");
  }
  if (result.error === "csrf_failed") {
    throw new OwnProfileRequestError(
      "csrf_failed",
      403,
      "保存に失敗しました。画面を再読み込みしてからもう一度お試しください。"
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
  const payload = parseOwnProfilePayload(result.data);
  if (!payload) {
    throw new OwnProfileRequestError(
      "invalid_payload",
      result.status,
      "保存結果を読み込めませんでした。"
    );
  }
  return payload;
}
