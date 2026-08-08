import { useEffect, useState } from "react";
import { isNativeCapacitorApp } from "../lib/nativeApp";
import {
  applySpaDiagMode,
  SPA_DIAG_MODE_OPTIONS,
  type SpaDiagModeId,
  useSpaNavDiag,
} from "../lib/spaNavDiag";

/**
 * Capacitor ネイティブ専用。More ページ下部の診断モード切替。
 * 通常の Web ブラウザでは何も描画しない。
 *
 * Note: remote WKWebView では Capacitor 注入が head スクリプトより遅れるため、
 * 初回 false でも capacitor:ready / 短時間ポーリングで再判定する。
 */
export function SpaDiagSection() {
  const diag = useSpaNavDiag();
  const [native, setNative] = useState(() => isNativeCapacitorApp());

  useEffect(() => {
    const update = () => {
      if (isNativeCapacitorApp()) {
        setNative(true);
      }
    };
    update();
    window.addEventListener("capacitor:ready", update);
    const intervalId = window.setInterval(update, 200);
    const timeoutId = window.setTimeout(() => {
      window.clearInterval(intervalId);
      update();
    }, 8000);
    return () => {
      window.removeEventListener("capacitor:ready", update);
      window.clearInterval(intervalId);
      window.clearTimeout(timeoutId);
    };
  }, []);

  if (!native) return null;

  const activeId: SpaDiagModeId | "" = (() => {
    if (!diag.raw) return "normal";
    const match = SPA_DIAG_MODE_OPTIONS.find(
      (m) => m.navDiag && m.navDiag === diag.raw
    );
    return match?.id ?? "";
  })();

  return (
    <section
      className="spa-diag-section"
      data-spa-diag-section="1"
      aria-label="SPA Flash Diagnostic"
      style={{
        marginTop: 28,
        marginBottom: 24,
        padding: "14px 12px",
        border: "1px dashed #c9a0a6",
        borderRadius: 12,
        background: "#faf7f8",
      }}
    >
      <h2
        style={{
          margin: "0 0 4px",
          fontSize: 14,
          fontWeight: 800,
          color: "#891e2b",
        }}
      >
        SPA Flash Diagnostic
      </h2>
      <p style={{ margin: "0 0 10px", fontSize: 11, color: "#536471" }}>
        TestFlight 専用。現在:{" "}
        <code style={{ fontSize: 11 }}>
          spa_nav_diag={diag.raw || "(none)"}
        </code>
      </p>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        {SPA_DIAG_MODE_OPTIONS.map((mode) => {
          const selected = mode.id === activeId;
          return (
            <button
              key={mode.id}
              type="button"
              onClick={() => applySpaDiagMode(mode.id)}
              style={{
                border: selected
                  ? "1px solid #891e2b"
                  : "1px solid #d0d7de",
                borderRadius: 8,
                padding: "8px 10px",
                fontSize: 12,
                fontWeight: selected ? 700 : 500,
                background: selected ? "#f7edf0" : "#fff",
                color: "#0f1419",
                cursor: "pointer",
                WebkitTapHighlightColor: "transparent",
                touchAction: "manipulation",
              }}
            >
              {mode.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}
