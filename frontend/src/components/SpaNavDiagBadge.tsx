import { spaNavDiagActive, useSpaNavDiag } from "../lib/spaNavDiag";

/**
 * TestFlight 切り分け中だけ表示。通常時は何も出さない。
 */
export function SpaNavDiagBadge() {
  const diag = useSpaNavDiag();
  if (!spaNavDiagActive(diag)) return null;

  return (
    <div
      className="spa-nav-diag-badge"
      role="status"
      aria-live="polite"
      style={{
        position: "fixed",
        top: "calc(env(safe-area-inset-top, 0px) + 4px)",
        right: 8,
        zIndex: 99999,
        padding: "4px 8px",
        borderRadius: 6,
        background: "rgba(15, 20, 25, 0.82)",
        color: "#fff",
        fontSize: 11,
        fontFamily: "ui-monospace, Menlo, monospace",
        pointerEvents: "none",
        maxWidth: "70vw",
        wordBreak: "break-all",
      }}
    >
      spa_nav_diag={diag.raw || "(on)"}
    </div>
  );
}
