import { useEffect, useMemo, useState } from "react";
import { isNativeCapacitorApp } from "../lib/nativeApp";
import {
  applySpaDiagMode,
  SPA_DIAG_MODE_OPTIONS,
  type SpaDiagModeId,
  useSpaNavDiag,
} from "../lib/spaNavDiag";

type ProbeSnapshot = {
  at: string;
  elapsedMs: number;
  capacitorExists: boolean;
  isNativePlatform: string;
  getPlatform: string;
  hasNativeClass: boolean;
  hasWaseIsAppCookie: boolean;
  waseAdmobIsApp: string;
  capacitorReadyFired: boolean;
  isNativeCapacitorApp: boolean;
  webkitMessageHandlers: string;
  userAgentShort: string;
};

type TimelineEntry = {
  label: string;
  at: string;
  elapsedMs: number;
  isNativeCapacitorApp: boolean;
  capacitorExists: boolean;
  isNativePlatform: string;
  getPlatform: string;
  hasNativeClass: boolean;
};

const t0 = Date.now();
let capacitorReadyFiredGlobal = false;

function wall(): string {
  try {
    return new Date().toISOString().slice(11, 23);
  } catch {
    return String(Date.now());
  }
}

function readCap(): {
  exists: boolean;
  isNativePlatform: string;
  getPlatform: string;
} {
  try {
    const Cap = (
      window as Window & {
        Capacitor?: {
          isNativePlatform?: () => boolean;
          getPlatform?: () => string;
        };
      }
    ).Capacitor;
    if (!Cap) {
      return {
        exists: false,
        isNativePlatform: "unknown",
        getPlatform: "unknown",
      };
    }
    let isNativePlatform = "unknown";
    let getPlatform = "unknown";
    try {
      if (typeof Cap.isNativePlatform === "function") {
        isNativePlatform = String(Cap.isNativePlatform());
      }
    } catch {
      isNativePlatform = "error";
    }
    try {
      if (typeof Cap.getPlatform === "function") {
        getPlatform = String(Cap.getPlatform());
      }
    } catch {
      getPlatform = "error";
    }
    return { exists: true, isNativePlatform, getPlatform };
  } catch {
    return {
      exists: false,
      isNativePlatform: "error",
      getPlatform: "error",
    };
  }
}

function takeSnapshot(): ProbeSnapshot {
  const cap = readCap();
  let hasNativeClass = false;
  try {
    hasNativeClass = document.documentElement.classList.contains(
      "is-native-capacitor"
    );
  } catch {
    hasNativeClass = false;
  }
  let hasWaseIsAppCookie = false;
  try {
    hasWaseIsAppCookie = /(?:^|;\s*)wase_is_app=1(?:;|$)/.test(
      document.cookie || ""
    );
  } catch {
    hasWaseIsAppCookie = false;
  }
  let waseAdmobIsApp = "unknown";
  try {
    const cfg = (
      window as Window & { WASE_ADMOB_CONFIG?: { IS_APP?: boolean } }
    ).WASE_ADMOB_CONFIG;
    if (cfg && typeof cfg.IS_APP === "boolean") {
      waseAdmobIsApp = String(cfg.IS_APP);
    } else {
      waseAdmobIsApp = "missing";
    }
  } catch {
    waseAdmobIsApp = "error";
  }
  let webkitMessageHandlers = "none";
  try {
    const handlers = (
      window as Window & {
        webkit?: { messageHandlers?: Record<string, unknown> };
      }
    ).webkit?.messageHandlers;
    if (handlers && typeof handlers === "object") {
      webkitMessageHandlers = Object.keys(handlers).sort().join(",") || "(empty)";
    }
  } catch {
    webkitMessageHandlers = "error";
  }
  let userAgentShort = "";
  try {
    userAgentShort = (navigator.userAgent || "").slice(0, 120);
  } catch {
    userAgentShort = "error";
  }

  return {
    at: wall(),
    elapsedMs: Date.now() - t0,
    capacitorExists: cap.exists,
    isNativePlatform: cap.isNativePlatform,
    getPlatform: cap.getPlatform,
    hasNativeClass,
    hasWaseIsAppCookie,
    waseAdmobIsApp,
    capacitorReadyFired: capacitorReadyFiredGlobal,
    isNativeCapacitorApp: isNativeCapacitorApp(),
    webkitMessageHandlers,
    userAgentShort,
  };
}

function row(label: string, value: string | boolean | number) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        gap: 8,
        fontSize: 11,
        lineHeight: 1.35,
        borderBottom: "1px solid #eee",
        padding: "4px 0",
      }}
    >
      <span style={{ color: "#536471" }}>{label}</span>
      <code style={{ textAlign: "right", wordBreak: "break-all" }}>
        {String(value)}
      </code>
    </div>
  );
}

/**
 * Observation-only probe for TestFlight.
 * Intentionally NOT gated on isNativeCapacitorApp() — otherwise a false
 * native check would hide the very diagnostics we need.
 * Temporary: always visible on More while diagnosing display conditions.
 */
export function SpaNativeProbe() {
  const diag = useSpaNavDiag();
  const [snap, setSnap] = useState<ProbeSnapshot>(() => takeSnapshot());
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);

  const pushTimeline = (label: string) => {
    const s = takeSnapshot();
    const entry: TimelineEntry = {
      label,
      at: s.at,
      elapsedMs: s.elapsedMs,
      isNativeCapacitorApp: s.isNativeCapacitorApp,
      capacitorExists: s.capacitorExists,
      isNativePlatform: s.isNativePlatform,
      getPlatform: s.getPlatform,
      hasNativeClass: s.hasNativeClass,
    };
    setTimeline((prev) => {
      if (prev.some((p) => p.label === label && p.elapsedMs === entry.elapsedMs)) {
        return prev;
      }
      return [...prev, entry].slice(-20);
    });
    try {
      console.info("[SpaNativeProbe]", label, entry);
    } catch {
      /* ignore */
    }
    setSnap(s);
  };

  useEffect(() => {
    pushTimeline("mount/render");
    const onReady = () => {
      capacitorReadyFiredGlobal = true;
      pushTimeline("capacitor:ready");
    };
    window.addEventListener("capacitor:ready", onReady);

    const bootId = window.setTimeout(() => pushTimeline("boot+0ms"), 0);
    const t1s = window.setTimeout(() => pushTimeline("t+1s"), 1000);
    const t3s = window.setTimeout(() => pushTimeline("t+3s"), 3000);
    const t8s = window.setTimeout(() => pushTimeline("t+8s"), 8000);

    const intervalId = window.setInterval(() => {
      setSnap(takeSnapshot());
    }, 500);

    return () => {
      window.removeEventListener("capacitor:ready", onReady);
      window.clearTimeout(bootId);
      window.clearTimeout(t1s);
      window.clearTimeout(t3s);
      window.clearTimeout(t8s);
      window.clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- observation mount once
  }, []);

  const renderGate = useMemo(() => {
    return {
      spaDiagSectionWouldShow: snap.isNativeCapacitorApp,
      probeAlwaysShown: true,
      reasonIfHidden:
        "SpaDiagSection requires isNativeCapacitorApp()===true; this probe ignores that gate",
    };
  }, [snap.isNativeCapacitorApp]);

  const activeId: SpaDiagModeId | "" = (() => {
    if (!diag.raw) return "normal";
    const match = SPA_DIAG_MODE_OPTIONS.find(
      (m) => m.navDiag && m.navDiag === diag.raw
    );
    return match?.id ?? "";
  })();

  return (
    <section
      className="spa-native-probe"
      data-spa-native-probe="1"
      aria-label="SPA Native Probe"
      style={{
        marginTop: 28,
        marginBottom: 24,
        padding: "14px 12px",
        border: "2px solid #891e2b",
        borderRadius: 12,
        background: "#fff8f8",
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
        SPA Native Probe (temporary)
      </h2>
      <p style={{ margin: "0 0 10px", fontSize: 11, color: "#536471" }}>
        観測専用。native 判定に依存せず More に常時表示。白フラッシュ修正は含みません。
      </p>

      {row("window.Capacitor exists", snap.capacitorExists)}
      {row("Capacitor.isNativePlatform()", snap.isNativePlatform)}
      {row("Capacitor.getPlatform()", snap.getPlatform)}
      {row("html.is-native-capacitor", snap.hasNativeClass)}
      {row("cookie wase_is_app=1", snap.hasWaseIsAppCookie)}
      {row("WASE_ADMOB_CONFIG.IS_APP", snap.waseAdmobIsApp)}
      {row("capacitor:ready fired", snap.capacitorReadyFired)}
      {row("isNativeCapacitorApp()", snap.isNativeCapacitorApp)}
      {row("SpaDiagSection would render", renderGate.spaDiagSectionWouldShow)}
      {row("webkit.messageHandlers", snap.webkitMessageHandlers)}
      {row("UA", snap.userAgentShort)}
      {row("snapshot age", `${snap.elapsedMs}ms @ ${snap.at}`)}

      <h3 style={{ margin: "12px 0 6px", fontSize: 12, fontWeight: 700 }}>
        Timeline
      </h3>
      <ul
        style={{
          margin: 0,
          padding: "0 0 0 16px",
          fontSize: 11,
          color: "#0f1419",
        }}
      >
        {timeline.map((e) => (
          <li key={`${e.label}-${e.elapsedMs}`}>
            <code>
              {e.label} +{e.elapsedMs}ms nativeFn=
              {String(e.isNativeCapacitorApp)} Cap=
              {String(e.capacitorExists)} isNative=
              {e.isNativePlatform} platform={e.getPlatform} class=
              {String(e.hasNativeClass)}
            </code>
          </li>
        ))}
      </ul>

      <h3 style={{ margin: "14px 0 6px", fontSize: 12, fontWeight: 700 }}>
        SPA Flash Diagnostic (always available here)
      </h3>
      <p style={{ margin: "0 0 8px", fontSize: 11, color: "#536471" }}>
        現在: <code>spa_nav_diag={diag.raw || "(none)"}</code>
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {SPA_DIAG_MODE_OPTIONS.map((mode) => {
          const selected = mode.id === activeId;
          return (
            <button
              key={mode.id}
              type="button"
              onClick={() => applySpaDiagMode(mode.id)}
              style={{
                border: selected ? "1px solid #891e2b" : "1px solid #d0d7de",
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
