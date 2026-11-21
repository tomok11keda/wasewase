import { useCallback, useEffect, useState } from "react";
import {
  isFirebaseMessagingPluginAvailable,
  requestPushPermissionFromUser,
} from "../lib/nativePush";
import { isNativeCapacitorApp } from "../lib/nativeApp";
import {
  normalizePushPermissionUx,
  shouldOfferPushEnableCta,
  shouldOpenSystemSettingsForPush,
  shouldShowSettingsPushControls,
  type PushPermissionUx,
} from "../lib/pushPrePermission";

function readBridgePermission(): string {
  const status = window.WaseCapacitor?.getPushStatus?.();
  return typeof status?.permission === "string" ? status.permission : "";
}

function openSystemSettings(): void {
  const bridge = window.WaseCapacitor;
  if (typeof bridge?.openSystemSettings === "function") {
    bridge.openSystemSettings();
    return;
  }
  try {
    window.location.href = "app-settings:";
  } catch {
    /* ignore */
  }
}

function labelForUx(ux: PushPermissionUx): string {
  if (ux === "granted") return "オン";
  if (ux === "denied") return "オフ（端末の設定で拒否）";
  if (ux === "prompt") return "未設定";
  return "確認中…";
}

/**
 * Native-only notification controls on Settings.
 * - prompt: request OS permission via the same CTA path as the pre-perm sheet
 * - denied: deep-link to iOS Settings (system sheet cannot be reshown)
 * - granted: status only
 */
export function SettingsPushNotifications() {
  const [visible, setVisible] = useState(false);
  const [permission, setPermission] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    const show = shouldShowSettingsPushControls({
      isNativeApp: isNativeCapacitorApp(),
      pluginAvailable: isFirebaseMessagingPluginAvailable(),
    });
    setVisible(show);
    setPermission(readBridgePermission());
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener("wase:push-permission-ready", refresh);
    const retry = window.setTimeout(refresh, 800);
    return () => {
      window.removeEventListener("wase:push-permission-ready", refresh);
      window.clearTimeout(retry);
    };
  }, [refresh]);

  if (!visible) return null;

  const ux = normalizePushPermissionUx(permission);

  const onEnable = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await requestPushPermissionFromUser();
      if (result?.receive) setPermission(result.receive);
      else setPermission(readBridgePermission());
    } finally {
      setBusy(false);
      refresh();
    }
  };

  return (
    <section className="settings-card">
      <h2>通知</h2>
      <p className="settings-lead">
        メッセージやいいねなどのお知らせを受け取る設定です。
      </p>
      <p className="settings-lead" aria-live="polite">
        状態: <strong>{labelForUx(ux)}</strong>
      </p>
      {shouldOfferPushEnableCta(permission) ? (
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => void onEnable()}
        >
          通知をオンにする
        </button>
      ) : null}
      {shouldOpenSystemSettingsForPush(permission) ? (
        <>
          <p className="settings-lead">
            一度拒否した通知は、アプリからもう一度OSの確認画面を出せません。iPhoneの設定からオンにしてください。
          </p>
          <button
            type="button"
            className="btn"
            onClick={() => openSystemSettings()}
          >
            iPhoneの設定を開く
          </button>
        </>
      ) : null}
    </section>
  );
}
