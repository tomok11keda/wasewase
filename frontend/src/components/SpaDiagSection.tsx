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
 */
export function SpaDiagSection() {
  const diag = useSpaNavDiag();
  const [native, setNative] = useState(false);

  useEffect(() => {
    setNative(isNativeCapacitorApp());
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
