import { getCsrfToken } from "../timeline/api";
import type { MeResponse } from "../../lib/api";

export type LinkedProfile = {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
  is_current: boolean;
  is_credential: boolean;
};

export type LinkedProfilesPayload = {
  ok: boolean;
  profiles?: LinkedProfile[];
  can_add?: boolean;
  max?: number;
  me?: MeResponse;
  deleted?: boolean;
  error?: string;
  message?: string;
};

async function postJson(
  url: string,
  body: Record<string, unknown>
): Promise<{ res: Response; data: LinkedProfilesPayload }> {
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
  const data = (await res.json().catch(() => ({}))) as LinkedProfilesPayload;
  return { res, data };
}

export async function createLinkedProfile(payload: {
  username: string;
  display_name: string;
}) {
  return postJson("/api/v1/me/linked-profiles/create/", payload);
}

export async function switchLinkedProfile(userId: number) {
  return postJson("/api/v1/me/linked-profiles/switch/", { user_id: userId });
}

export async function deleteLinkedProfile(options?: {
  entireIdentity?: boolean;
}) {
  return postJson("/api/v1/me/linked-profiles/delete/", {
    entire_identity: Boolean(options?.entireIdentity),
  });
}
