import { getCsrfToken } from "../timeline/api";
import { unregisterNativePushForSession } from "../../lib/nativePush";

async function postJson(url: string, body: Record<string, unknown>) {
  const res = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

export async function ensureAuthCsrf() {
  await fetch("/api/v1/auth/csrf/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
}

export async function loginRequest(payload: {
  email: string;
  password: string;
  next?: string;
}) {
  return postJson("/api/v1/auth/login/", payload);
}

export async function logoutRequest() {
  return postJson("/api/v1/auth/logout/", {});
}

/**
 * ネイティブ Push 紐付けを外してからセッションを破棄する。
 * ログアウト→別アカウントログイン時に旧ユーザーへ Push が届き続けるのを防ぐ。
 */
export async function performSpaLogout(): Promise<void> {
  try {
    await unregisterNativePushForSession();
  } catch {
    /* ignore push unregister failures */
  }
  await logoutRequest();
}


export async function browseRequest(next?: string) {
  return postJson("/api/v1/auth/browse/", { next: next || "/app/" });
}

export async function fetchSignupMeta(): Promise<{
  faculties: { value: string; label: string }[];
  email_console_fallback: boolean;
  email_config_errors: string[];
}> {
  const res = await fetch("/api/v1/auth/signup-meta/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error("signup_meta_failed");
  return data;
}

export async function signupRequest(payload: Record<string, unknown>) {
  return postJson("/api/v1/auth/signup/", payload);
}

export async function verifyOtpRequest(code: string) {
  return postJson("/api/v1/auth/verify/", { code });
}

export async function verifyOtpResend() {
  return postJson("/api/v1/auth/verify/resend/", {});
}

export async function fetchVerifyStatus() {
  const res = await fetch("/api/v1/auth/verify/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  return res.json();
}

export async function passwordResetRequest(email: string) {
  return postJson("/api/v1/auth/password-reset/", { email });
}

export async function passwordResetVerify(code: string) {
  return postJson("/api/v1/auth/password-reset/verify/", { code });
}

export async function passwordResetResend() {
  return postJson("/api/v1/auth/password-reset/resend/", {});
}

export async function passwordResetSet(password1: string, password2: string) {
  return postJson("/api/v1/auth/password-reset/set/", { password1, password2 });
}

export async function fetchPasswordResetStatus() {
  const res = await fetch("/api/v1/auth/password-reset/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  return res.json();
}

/** Build SPA login path with next (absolute /app/... path). */
export function spaLoginPath(nextAppPath: string): string {
  const next = nextAppPath.startsWith("/app")
    ? nextAppPath
    : `/app${nextAppPath.startsWith("/") ? nextAppPath : `/${nextAppPath}`}`;
  return `/login?next=${encodeURIComponent(next)}`;
}

/** Full URL for hard navigation into SPA login (same origin). */
export function spaLoginHref(nextAppPath: string): string {
  return `/app${spaLoginPath(nextAppPath)}`;
}
