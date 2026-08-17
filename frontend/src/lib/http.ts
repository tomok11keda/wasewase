/** Shared same-origin JSON fetch helpers (Django session + CSRF). */

import { getCsrfToken } from "../features/timeline/api";

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

export async function apiGetJson(url: string): Promise<ApiJsonResult> {
  const res = await fetch(url, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await parseJson(res);
  const error = res.ok ? undefined : resolveError(res.status, data);
  return {
    ok: Boolean(res.ok && data.ok !== false),
    status: res.status,
    data,
    error,
  };
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
  const data = await parseJson(res);
  const error = res.ok ? undefined : resolveError(res.status, data);
  return {
    ok: Boolean(res.ok && data.ok !== false),
    status: res.status,
    data,
    error,
  };
}
