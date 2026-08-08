/**
 * Tab-switch flash diagnosis timeline.
 * Observation only — does not change SPA / AdMob / Analytics behavior.
 *
 * Enable: ?spa_flash_diag=1  or localStorage.wase_flash_diag=1
 * Dump:   window.WaseFlashDiag.exportTraces()
 * Clear:  window.WaseFlashDiag.clear()
 */
(function (window) {
  "use strict";

  var STORAGE_KEY = "wase_flash_diag";
  var MAX_TRACES = 40;
  var MAX_EVENTS_PER_TRACE = 200;
  var traces = [];
  var active = null;
  var seq = 0;
  var enabledCache = null;

  function nowMs() {
    return window.performance && typeof window.performance.now === "function"
      ? window.performance.now()
      : Date.now();
  }

  function wallIso() {
    try {
      return new Date().toISOString();
    } catch (e) {
      return String(Date.now());
    }
  }

  function readEnabled() {
    if (enabledCache !== null) {
      return enabledCache;
    }
    var on = false;
    try {
      var params = new URLSearchParams(window.location.search || "");
      if (params.has("spa_flash_diag")) {
        var v = (params.get("spa_flash_diag") || "1").toLowerCase();
        on = !(v === "0" || v === "off" || v === "false");
        try {
          if (on) {
            window.localStorage.setItem(STORAGE_KEY, "1");
          } else {
            window.localStorage.removeItem(STORAGE_KEY);
          }
        } catch (e0) {
          /* ignore */
        }
      } else {
        on = window.localStorage.getItem(STORAGE_KEY) === "1";
      }
    } catch (e1) {
      on = false;
    }
    if (window.WASE_FLASH_DIAG_FORCE === true) {
      on = true;
    }
    enabledCache = on;
    return on;
  }

  function refreshEnabled() {
    enabledCache = null;
    return readEnabled();
  }

  function pushEvent(type, payload) {
    if (!readEnabled() || !active) {
      return null;
    }
    if (active.events.length >= MAX_EVENTS_PER_TRACE) {
      return null;
    }
    var t = nowMs();
    var ev = {
      i: active.events.length,
      t: Math.round(t * 1000) / 1000,
      dt: Math.round((t - active.t0) * 1000) / 1000,
      wall: wallIso(),
      type: type,
      data: payload || null,
    };
    active.events.push(ev);
    try {
      if (window.console && typeof window.console.debug === "function") {
        window.console.debug(
          "[WaseFlashDiag]",
          "+" + ev.dt + "ms",
          type,
          payload || ""
        );
      }
    } catch (e2) {
      /* ignore */
    }
    return ev;
  }

  function beginTrace(meta) {
    if (!readEnabled()) {
      return null;
    }
    if (active) {
      endTrace({ reason: "auto-close-before-next" });
    }
    seq += 1;
    var id =
      "trace-" +
      seq +
      "-" +
      Date.now().toString(36) +
      "-" +
      Math.floor(Math.random() * 1e4).toString(36);
    active = {
      id: id,
      t0: nowMs(),
      wall0: wallIso(),
      meta: meta || {},
      events: [],
      nativeSnapshots: [],
      nativeEvents: [],
      ended: false,
    };
    pushEvent("trace_begin", meta || {});
    try {
      var plugin = getFlashDiagPlugin();
      if (plugin && typeof plugin.beginTrace === "function") {
        plugin
          .beginTrace({
            traceId: id,
            path: window.location.pathname,
            mode: (meta && meta.spaNavDiag) || "",
            sampleMs: 500,
          })
          .catch(function () {
            /* ignore */
          });
      }
    } catch (eBegin) {
      /* ignore */
    }
    return id;
  }

  function endTrace(meta) {
    if (!active) {
      return null;
    }
    pushEvent("trace_end", meta || {});
    active.ended = true;
    active.durationMs =
      Math.round((nowMs() - active.t0) * 1000) / 1000;
    var done = active;
    active = null;
    try {
      var pluginEnd = getFlashDiagPlugin();
      if (pluginEnd && typeof pluginEnd.endTrace === "function") {
        pluginEnd
          .endTrace({ traceId: done.id })
          .then(function (result) {
            if (result && result.events) {
              done.nativeEvents = result.events;
            }
          })
          .catch(function () {
            /* ignore */
          });
      }
    } catch (eEnd) {
      /* ignore */
    }
    traces.push(done);
    if (traces.length > MAX_TRACES) {
      traces.shift();
    }
    return done;
  }

  function mark(type, payload) {
    return pushEvent(type, payload);
  }

  function getFlashDiagPlugin() {
    try {
      if (
        window.Capacitor &&
        typeof window.Capacitor.getPlugin === "function"
      ) {
        var p = window.Capacitor.getPlugin("FlashDiag");
        if (p) {
          return p;
        }
      }
      if (
        window.Capacitor &&
        window.Capacitor.Plugins &&
        window.Capacitor.Plugins.FlashDiag
      ) {
        return window.Capacitor.Plugins.FlashDiag;
      }
    } catch (e) {
      /* ignore */
    }
    return null;
  }

  function snapshotNative(reason) {
    if (!readEnabled()) {
      return Promise.resolve(null);
    }
    var plugin = getFlashDiagPlugin();
    var jsSide = {
      reason: reason || "snapshot",
      path: window.location.pathname,
      search: window.location.search,
      visualViewport: null,
      rootBg: null,
      bodyBg: null,
    };
    try {
      if (window.visualViewport) {
        jsSide.visualViewport = {
          width: window.visualViewport.width,
          height: window.visualViewport.height,
          offsetTop: window.visualViewport.offsetTop,
          scale: window.visualViewport.scale,
        };
      }
      var csHtml = window.getComputedStyle(document.documentElement);
      var csBody = document.body
        ? window.getComputedStyle(document.body)
        : null;
      var root = document.getElementById("root");
      jsSide.htmlBg = csHtml ? csHtml.backgroundColor : null;
      jsSide.bodyBg = csBody ? csBody.backgroundColor : null;
      jsSide.rootBg = root
        ? window.getComputedStyle(root).backgroundColor
        : null;
    } catch (e3) {
      /* ignore */
    }
    pushEvent("js_snapshot", jsSide);

    if (!plugin || typeof plugin.snapshot !== "function") {
      pushEvent("native_snapshot_unavailable", { reason: reason || null });
      return Promise.resolve(null);
    }

    return plugin
      .snapshot({
        reason: reason || "snapshot",
        traceId: active ? active.id : null,
        path: window.location.pathname,
      })
      .then(function (result) {
        if (active) {
          active.nativeSnapshots.push({
            dt: Math.round((nowMs() - active.t0) * 1000) / 1000,
            result: result,
          });
        }
        pushEvent("native_snapshot", result || null);
        return result;
      })
      .catch(function (err) {
        pushEvent("native_snapshot_error", {
          message: String(err && err.message ? err.message : err),
        });
        return null;
      });
  }

  function summarizeTrace(trace) {
    var counts = {};
    (trace.events || []).forEach(function (ev) {
      counts[ev.type] = (counts[ev.type] || 0) + 1;
    });
    var types = Object.keys(counts).sort();
    return {
      id: trace.id,
      durationMs: trace.durationMs,
      meta: trace.meta,
      eventCounts: counts,
      eventTypes: types,
      hasNotifySpaNavigation: Boolean(counts.notify_spa_navigation),
      hasScheduleBannerReposition: Boolean(counts.schedule_banner_reposition),
      hasRepositionInlineBanner: Boolean(counts.reposition_inline_banner),
      hasRenderBanner: Boolean(counts.render_banner || counts.admob_show_banner),
      hasAnalytics: Boolean(counts.analytics_track_page_view),
      hasTabTransition: Boolean(
        counts.tab_transition_start || counts.tab_transition_end
      ),
      hasKeepAliveMount: Boolean(
        counts.keepalive_pane_mount || counts.keepalive_pane_unmount
      ),
      nativeSnapshotCount: (trace.nativeSnapshots || []).length,
    };
  }

  function exportTraces() {
    return {
      enabled: readEnabled(),
      exportedAt: wallIso(),
      activeTraceId: active ? active.id : null,
      traces: traces.slice(),
      summaries: traces.map(summarizeTrace),
    };
  }

  function clear() {
    traces = [];
    active = null;
  }

  function getActiveTraceId() {
    return active ? active.id : null;
  }

  window.WaseFlashDiag = {
    isEnabled: readEnabled,
    refreshEnabled: refreshEnabled,
    beginTrace: beginTrace,
    endTrace: endTrace,
    mark: mark,
    snapshotNative: snapshotNative,
    exportTraces: exportTraces,
    summarizeTrace: summarizeTrace,
    clear: clear,
    getActiveTraceId: getActiveTraceId,
    getTraces: function () {
      return traces.slice();
    },
  };
})(window);
