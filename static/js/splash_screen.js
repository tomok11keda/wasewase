/**
 * Capacitor 起動スプラッシュ。
 * - 約 1.35 秒で自動フェードアウト
 * - それ以前のタップ / クリックで即座にフェードアウト
 */
(function (window, document) {
  "use strict";

  var FADE_MS = 380;
  var AUTO_DISMISS_MS = 1350;
  var TAP_MIN_VISIBLE_MS = 80;
  var STORAGE_KEY = "wase_splash_done";
  var BRAND = "#891E2B";
  var dismissed = false;
  var autoTimer = null;
  var listenersBound = false;

  function isNativeApp() {
    return (
      window.Capacitor &&
      typeof window.Capacitor.isNativePlatform === "function" &&
      window.Capacitor.isNativePlatform()
    );
  }

  function logoSrc() {
    var existing = document.querySelector("#splash-screen .splash-screen__logo");
    if (existing && existing.getAttribute("src")) {
      return existing.getAttribute("src");
    }
    var link = document.querySelector('link[rel="stylesheet"][href*="splash_screen"]');
    if (link && link.href) {
      return link.href.replace(/css\/splash_screen\.css.*$/, "assets/splash-logo.svg");
    }
    return "/static/assets/splash-logo.svg";
  }

  function splashMarkup() {
    return (
      '<div class="splash-screen__brand">' +
      '<img class="splash-screen__logo" src="' +
      logoSrc() +
      '" alt="わせわせ" width="220" height="192" decoding="async">' +
      "</div>" +
      '<div class="splash-screen__footer-block">' +
      '<p class="splash-screen__footer">Anonymous Waseda Developer</p>' +
      '<p class="splash-screen__hint">タップしてはじめる</p>' +
      "</div>"
    );
  }

  function clearAutoTimer() {
    if (autoTimer !== null) {
      window.clearTimeout(autoTimer);
      autoTimer = null;
    }
  }

  function clearPendingClass() {
    document.documentElement.classList.remove("wase-splash-pending");
  }

  function finishRemove(splash) {
    if (splash && splash.parentNode) {
      splash.parentNode.removeChild(splash);
    }
    clearPendingClass();
    try {
      sessionStorage.setItem(STORAGE_KEY, "1");
    } catch (e) {}
  }

  function startFade(splash) {
    splash.classList.add("is-hiding");
    window.setTimeout(function () {
      finishRemove(splash);
    }, FADE_MS);
  }

  function dismissSplashScreen(options) {
    if (dismissed) {
      return;
    }
    if (!isNativeApp()) {
      return;
    }

    var splash = ensureMounted() || document.getElementById("splash-screen");
    if (!splash) {
      clearPendingClass();
      try {
        sessionStorage.setItem(STORAGE_KEY, "1");
      } catch (e) {}
      return;
    }

    dismissed = true;
    clearAutoTimer();
    unbindInteraction(splash);

    var immediate = options && (options.immediate || options.force || options.fromTap);
    var mountedAt = window.__waseSplashMountedAt || Date.now();
    var elapsed = Date.now() - mountedAt;
    var wait = immediate ? Math.max(0, TAP_MIN_VISIBLE_MS - elapsed) : 0;

    window.setTimeout(function () {
      startFade(splash);
    }, wait);
  }

  function onUserInteract(event) {
    if (dismissed) {
      return;
    }
    if (event) {
      event.preventDefault();
    }
    dismissSplashScreen({ fromTap: true });
  }

  function bindInteraction(splash) {
    if (!splash || listenersBound) {
      return;
    }
    listenersBound = true;
    splash.addEventListener("pointerdown", onUserInteract, { passive: false });
    splash.addEventListener("click", onUserInteract, { passive: false });
    splash.setAttribute("role", "button");
    splash.setAttribute("aria-label", "タップしてはじめる");
    splash.removeAttribute("aria-hidden");
    splash.tabIndex = 0;
    splash.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        onUserInteract(event);
      }
    });
  }

  function unbindInteraction(splash) {
    if (!splash || !listenersBound) {
      return;
    }
    listenersBound = false;
    splash.removeEventListener("pointerdown", onUserInteract);
    splash.removeEventListener("click", onUserInteract);
  }

  function scheduleAutoDismiss() {
    clearAutoTimer();
    autoTimer = window.setTimeout(function () {
      dismissSplashScreen({ immediate: true });
    }, AUTO_DISMISS_MS);
  }

  function ensureMounted() {
    if (!isNativeApp()) {
      return null;
    }
    try {
      if (sessionStorage.getItem(STORAGE_KEY) === "1") {
        return null;
      }
    } catch (e) {}

    document.documentElement.classList.add("is-native-capacitor", "wase-splash-pending");
    document.documentElement.style.backgroundColor = BRAND;

    var splash = document.getElementById("splash-screen");
    if (splash) {
      if (!splash.querySelector(".splash-screen__hint")) {
        var footer = splash.querySelector(".splash-screen__footer");
        if (footer && footer.parentNode === splash) {
          var block = document.createElement("div");
          block.className = "splash-screen__footer-block";
          footer.parentNode.insertBefore(block, footer);
          block.appendChild(footer);
          var hint = document.createElement("p");
          hint.className = "splash-screen__hint";
          hint.textContent = "タップしてはじめる";
          block.appendChild(hint);
        }
      }
      bindInteraction(splash);
      return splash;
    }
    if (!document.body) {
      return null;
    }

    splash = document.createElement("div");
    splash.id = "splash-screen";
    splash.innerHTML = splashMarkup();
    document.body.appendChild(splash);
    window.__waseSplashMountedAt = Date.now();
    bindInteraction(splash);
    return splash;
  }

  window.WaseSplashScreen = {
    dismiss: function () {
      // 初期化完了通知は受け取るが、ブランド表示の自動タイマーを優先する
    },
    dismissNow: function () {
      dismissSplashScreen({ immediate: true });
    },
    ensureMounted: ensureMounted,
  };

  if (!isNativeApp()) {
    return;
  }

  function boot() {
    if (!ensureMounted()) {
      return;
    }
    scheduleAutoDismiss();
  }

  if (document.body) {
    boot();
  } else {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  }
})(window, document);
