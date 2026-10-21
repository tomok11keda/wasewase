import { getCsrfToken } from "../features/timeline/api";
import { userFacingMutationError } from "./rateLimit";

export type ApiJsonResult<T = Record<string, unknown>> = {
  ok: boolean;
  status: number;
  data: T;
  error?: string;
};

async function parseJson(res: Response): Promise<Record<string, unknown>> {
  try {
    const data = await res.json();
    return data && typeof data === "object" ? (data as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function resolveError(
  status: number,
  data: Record<string, unknown>
): string | undefined {
  if (typeof data.error === "string" && data.error) {
    return data.error;
  }
  if (status === 401) return "unauthorized";
  if (status === 403) return "csrf_failed";
  if (status === 429) return "rate_limited";
  if (status >= 400) return `http_${status}`;
  return undefined;
}

async function jsonResult(res: Response): Promise<ApiJsonResult> {
  const data = await parseJson(res);
  const error = res.ok ? undefined : resolveError(res.status, data);
  return {
    ok: Boolean(res.ok && data.ok !== false),
    status: res.status,
    data,
    error,
  };
}

export async function apiGetJson(url: string): Promise<ApiJsonResult> {
  const res = await fetch(url, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  return jsonResult(res);
}

export async function apiPostJson(
  url: string,
  body: unknown = {}
): Promise<ApiJsonResult> {
  const res = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(body ?? {}),
  });
  return jsonResult(res);
}

export async function apiPatchJson(
  url: string,
  body: unknown = {}
): Promise<ApiJsonResult> {
  const res = await fetch(url, {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(body ?? {}),
  });
  return jsonResult(res);
}

/** Multipart PATCH. Do not set Content-Type — the browser must keep the boundary. */
export async function apiPatchForm(
  url: string,
  body: FormData
): Promise<ApiJsonResult> {
  const res = await fetch(url, {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body,
  });
  return jsonResult(res);
}

/** Prefer Japanese message when the API returned rate_limited. */
export function mutationErrorMessage(
  error: string | undefined,
  fallback: string
): string {
  return userFacingMutationError(error, fallback);
}
