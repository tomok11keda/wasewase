import type { MeResponse } from "../../lib/api";
import type { LinkedProfile } from "./api";

export function linkedProfilesFromMe(me: MeResponse | null | undefined): LinkedProfile[] {
  const rows = me?.linked_profiles;
  if (!Array.isArray(rows)) {
    const user = me?.user;
    if (!user) return [];
    return [
      {
        id: user.id,
        username: user.username,
        display_name: user.display_name,
        avatar_url: user.avatar_url,
        initial: user.initial,
        is_current: true,
        is_credential: true,
      },
    ];
  }
  return rows;
}

export function canAddLinkedProfile(me: MeResponse | null | undefined): boolean {
  return Boolean(me?.can_add_linked_profile);
}

/** Display-only. The server enforces the real cap via can_add / create. */
export function linkedProfileMax(me: MeResponse | null | undefined): number {
  const n = me?.linked_profile_max;
  if (typeof n === "number" && Number.isInteger(n) && n > 0) return n;
  return 2;
}

export function shouldOpenOwnProfileAfterSwitch(
  pathname: string,
  previousUserId: number | null | undefined,
  nextUserId: number
): boolean {
  if (!previousUserId || previousUserId === nextUserId) return false;
  return pathname.startsWith(`/users/${previousUserId}`);
}
