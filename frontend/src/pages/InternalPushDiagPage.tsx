import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchInternalPushDiag,
  type InternalPushDiagResponse,
} from "../lib/api";
import {
  readNativeAppInfo,
  readSafePushDiagnostics,
  type SafePushDiagnostics,
} from "../lib/nativePush";

function yesNo(value: boolean): string {
  return value ? "YES" : "NO";
}

export function InternalPushDiagPage() {
  const [forbidden, setForbidden] = useState(false);
  const [loading, setLoading] = useState(true);
  const [server, setServer] = useState<InternalPushDiagResponse | null>(null);
  const [native, setNative] = useState<SafePushDiagnostics | null>(null);
  const [appInfo, setAppInfo] = useState({ version: "", build: "" });
  const [fetchError, setFetchError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setFetchError("");
    try {
      const data = await fetchInternalPushDiag();
      if (!data) {
        setForbidden(true);
        setServer(null);
        setNative(null);
        return;
      }
      setForbidden(false);
      setServer(data);
      setNative(readSafePushDiagnostics());
      setAppInfo(await readNativeAppInfo());
    } catch {
      setFetchError("load_failed");
      setServer(null);
      setNative(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!server) return;
    const timer = window.setInterval(() => {
      setNative(readSafePushDiagnostics());
    }, 2000);
    const stop = window.setTimeout(() => window.clearInterval(timer), 20000);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(stop);
    };
  }, [server]);

  if (loading) {
    return (
      <div className="settings-page" data-spa-page="Push Diagnostics">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (forbidden || !server) {
    return (
      <div className="settings-page" data-spa-page="Not found">
        <div className="main-inner">
          <p>ページが見つかりません。</p>
          {fetchError ? <p>Error: {fetchError}</p> : null}
          <p>
            <Link to="/">タイムラインへ戻る</Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-page" data-spa-page="Push Diagnostics">
      <div className="main-inner">
        <Link className="profile-back" to="/settings">
          ← 設定へ戻る
        </Link>
        <h1 className="page-title">Push Diagnostics</h1>
        <p className="settings-lead">
          Internal only. Tokens and secrets are never shown.
        </p>

        <section className="settings-card">
          <h2>Account</h2>
          <ul className="more-list">
            <li>Authenticated: {yesNo(server.authenticated)}</li>
            <li>User ID: {server.user_id}</li>
            <li>Staff: {yesNo(server.is_staff)}</li>
            <li>Superuser: {yesNo(server.is_superuser)}</li>
            <li>
              Backend DevicePushToken rows for this user:{" "}
              {server.device_push_token_count}
            </li>
          </ul>
        </section>

        <section className="settings-card">
          <h2>Native / FCM</h2>
          <ul className="more-list">
            <li>Native bridge: {yesNo(Boolean(native?.native_bridge))}</li>
            <li>
              Native platform: {yesNo(Boolean(native?.native_platform))}
            </li>
            <li>
              Firebase Messaging plugin:{" "}
              {yesNo(Boolean(native?.firebase_messaging_plugin))}
            </li>
            <li>
              Notification permission: {native?.permission || "(empty)"}
            </li>
            <li>
              FCM token acquired: {yesNo(Boolean(native?.fcm_token_acquired))}
            </li>
            <li>
              Backend registered (client POST success):{" "}
              {yesNo(Boolean(native?.backend_registered))}
            </li>
            <li>
              APNs (independent check): unavailable — current client only
              infers APNs after FCM token acquisition
            </li>
            <li>
              FCM-inferred APNs flag:{" "}
              {yesNo(Boolean(native?.fcm_inferred_apns_flag))}
            </li>
            <li>Error: {native?.error || "none"}</li>
            <li>App version: {appInfo.version || "unavailable"}</li>
            <li>Build: {appInfo.build || "unavailable"}</li>
          </ul>
          <p>
            <button type="button" onClick={() => void load()}>
              Refresh
            </button>
          </p>
        </section>
      </div>
    </div>
  );
}
