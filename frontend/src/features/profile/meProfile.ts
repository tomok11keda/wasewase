export const OWN_PROFILE_NAME_MAX = 80;
export const OWN_PROFILE_HANDLE_MIN = 3;
export const OWN_PROFILE_HANDLE_MAX = 30;
export const OWN_PROFILE_AVATAR_MAX_BYTES = 5 * 1024 * 1024;
export const OWN_PROFILE_HANDLE_PATTERN = /^[a-zA-Z0-9_]{3,30}$/;

const ALLOWED_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
]);
const ALLOWED_IMAGE_EXTS = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp"]);
const HEIC_EXTS = new Set([".heic", ".heif"]);

export type ProfileChoice = { value: string; label: string };

export type OwnProfileFields = {
  id: number;
  username: string;
  name: string;
  display_name: string;
  bio: string;
  avatar_url: string;
  initial: string;
  department: string;
  grade: string;
  department_grade: string;
};

export type OwnProfilePayload = {
  ok: boolean;
  profile: OwnProfileFields;
  choices: {
    department: ProfileChoice[];
    grade: ProfileChoice[];
  };
};

export type OwnProfileForm = {
  name: string;
  bio: string;
  user_id: string;
  department: string;
  grade: string;
};

export function formFromOwnProfile(profile: OwnProfileFields): OwnProfileForm {
  return {
    name: profile.name || "",
    bio: profile.bio || "",
    user_id: profile.username || "",
    department: profile.department || "",
    grade: profile.grade || "",
  };
}

export function parseOwnProfilePayload(raw: unknown): OwnProfilePayload | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (data.ok === false) return null;
  const profileRaw = data.profile;
  if (!profileRaw || typeof profileRaw !== "object") return null;
  const row = profileRaw as Record<string, unknown>;
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  return {
    ok: true,
    profile: {
      id,
      username: typeof row.username === "string" ? row.username : "",
      name: typeof row.name === "string" ? row.name : "",
      display_name:
        typeof row.display_name === "string" ? row.display_name : "",
      bio: typeof row.bio === "string" ? row.bio : "",
      avatar_url: typeof row.avatar_url === "string" ? row.avatar_url : "",
      initial: typeof row.initial === "string" ? row.initial : "",
      department: typeof row.department === "string" ? row.department : "",
      grade: typeof row.grade === "string" ? row.grade : "",
      department_grade:
        typeof row.department_grade === "string" ? row.department_grade : "",
    },
    choices: {
      department: parseChoices(
        (data.choices as { department?: unknown } | undefined)?.department
      ),
      grade: parseChoices(
        (data.choices as { grade?: unknown } | undefined)?.grade
      ),
    },
  };
}

function parseChoices(raw: unknown): ProfileChoice[] {
  if (!Array.isArray(raw)) return [];
  const items: ProfileChoice[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const row = entry as Record<string, unknown>;
    if (typeof row.value !== "string" || typeof row.label !== "string") continue;
    items.push({ value: row.value, label: row.label });
  }
  return items;
}

export function validateOwnProfileAvatar(file: File): string | null {
  if (file.size > OWN_PROFILE_AVATAR_MAX_BYTES) {
    return "画像は5MB以下にしてください。";
  }
  const name = file.name.toLowerCase();
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
  if (HEIC_EXTS.has(ext) || file.type === "image/heic" || file.type === "image/heif") {
    return "HEIC形式は現在非対応です。JPEG または PNG に変換してからアップロードしてください。";
  }
  if (
    !ALLOWED_IMAGE_TYPES.has(file.type) &&
    !ALLOWED_IMAGE_EXTS.has(ext) &&
    file.type !== "application/octet-stream"
  ) {
    return "JPEG / PNG / GIF / WebP の画像を選んでください。";
  }
  return null;
}

export function validateOwnProfileForm(
  form: OwnProfileForm
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (form.name.length > OWN_PROFILE_NAME_MAX) {
    errors.name = `表示名は${OWN_PROFILE_NAME_MAX}文字以内です。`;
  }
  const handle = form.user_id.trim().replace(/^@/, "");
  if (!handle) {
    errors.user_id = "ユーザー名を入力してください。";
  } else if (!OWN_PROFILE_HANDLE_PATTERN.test(handle)) {
    errors.user_id =
      "ユーザー名は英数字とアンダースコア（_）のみ、3〜30文字で入力してください。";
  }
  return errors;
}

export function isOwnProfileFormDirty(
  current: OwnProfileForm,
  original: OwnProfileForm,
  avatar: File | null
): boolean {
  if (avatar) return true;
  return (
    current.name !== original.name ||
    current.bio !== original.bio ||
    current.user_id !== original.user_id ||
    current.department !== original.department ||
    current.grade !== original.grade
  );
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
