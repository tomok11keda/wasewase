import { useEffect } from "react";
import { useSession } from "../lib/session";
import { syncNativePushWithUserId } from "../lib/nativePush";

/**
 * SPA ログイン成功・セッション復元後に Push トークンを再登録する。
 * ネイティブ bootstrap 時点で未ログインだと /api/push-token/ が 401/302 になるため。
 */
export function NativePushSessionSync() {
  const { me, loading } = useSession();

  useEffect(() => {
    if (loading) return;
    const userId =
      me?.authenticated && me.user?.id != null ? me.user.id : null;
    void syncNativePushWithUserId(userId);
  }, [loading, me?.authenticated, me?.user?.id]);

  return null;
}
