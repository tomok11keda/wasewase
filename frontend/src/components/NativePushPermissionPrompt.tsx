import { useCallback, useEffect, useId, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  isFirebaseMessagingPluginAvailable,
  requestPushPermissionFromUser,
} from "../lib/nativePush";
import {
  markPrePermissionDismissed,
  readPrePermissionDismissed,
  shouldShowPushPrePermission,
} from "../lib/pushPrePermission";
import { useSession } from "../lib/session";

function readBridgePermission(): string {
  const status = window.WaseCapacitor?.getPushStatus?.();
  return typeof status?.permission === "string" ? status.permission : "";
}

/**
 * In-app explanation before iOS notification permission.
 * Bootstrap never calls requestPermissions; only the primary CTA does.
 */
export function NativePushPermissionPrompt() {
  const { me, loading } = useSession();
  const location = useLocation();
  const titleId = useId();
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);

  const evaluate = useCallback(() => {
    const show = shouldShowPushPrePermission({
      pluginAvailable: isFirebaseMessagingPluginAvailable(),
      permission: readBridgePermission(),
      dismissedThisSession: readPrePermissionDismissed(),
      authenticated: Boolean(me?.authenticated),
      onboardingRequired: Boolean(me?.onboarding_required),
      pathname: location.pathname || "/",
    });
    setVisible(show);
  }, [location.pathname, me?.authenticated, me?.onboarding_required]);

  useEffect(() => {
    if (loading) return;
    evaluate();
    window.addEventListener("wase:push-permission-ready", evaluate);
    const retry = window.setTimeout(evaluate, 800);
    return () => {
      window.removeEventListener("wase:push-permission-ready", evaluate);
      window.clearTimeout(retry);
    };
  }, [evaluate, loading]);

  const onLater = () => {
    if (busy) return;
    markPrePermissionDismissed();
    setVisible(false);
  };

  const onEnable = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await requestPushPermissionFromUser();
    } finally {
      setBusy(false);
      setVisible(false);
    }
  };

  if (!visible) return null;

  return (
    <div className="push-preperm" role="presentation">
      <button
        type="button"
        className="push-preperm__backdrop"
        aria-label="閉じる"
        onClick={onLater}
      />
      <div
        className="push-preperm__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 id={titleId} className="push-preperm__title">
          わせわせを見逃さない
        </h2>
        <p className="push-preperm__body">
          メッセージ、コメント、いいね、フォローなどをリアルタイムでお知らせします。
        </p>
        <button
          type="button"
          className="push-preperm__primary"
          disabled={busy}
          onClick={() => void onEnable()}
        >
          通知を受け取る
        </button>
        <button
          type="button"
          className="push-preperm__secondary"
          disabled={busy}
          onClick={onLater}
        >
          あとで
        </button>
      </div>
    </div>
  );
}
