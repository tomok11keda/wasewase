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

export const FULL_WITHDRAWAL_ORG_WARNING =
  "代表管理者のまま退会すると、他に代表管理者がいない団体は非公開になります。団体そのものと残っているメンバーは削除されません。";

export const LAST_OWNER_PROFILE_DELETE_HINT =
  "このプロフィールが団体の最後の代表管理者の場合、プロフィール削除はできません。先に別の代表管理者へ権限を移してください。";

export function accountDeletionConfirmMessage(input: {
  entireIdentity: boolean;
  hasSibling: boolean;
  currentHandle: string;
}): string {
  if (input.entireIdentity) {
    return `WaseWaseから完全退会しますか？紐づくすべてのプロフィールが削除されます。${FULL_WITHDRAWAL_ORG_WARNING}`;
  }
  if (input.hasSibling) {
    return `@${input.currentHandle} を削除しますか？もう一方のプロフィールは残ります。${LAST_OWNER_PROFILE_DELETE_HINT}`;
  }
  return `@${input.currentHandle} を削除して WaseWase を退会しますか？この操作は取り消せません。${FULL_WITHDRAWAL_ORG_WARNING}`;
}
