/**
 * Capacitor 起動スプラッシュのマウント補助とフェードアウト制御。
 * 初期化完了後、最短表示を確保してから 1 秒かけて消す。
 */
(function (window, document) {
  "use strict";

  var FADE_MS = 1000;
  var MIN_VISIBLE_MS = 700;
  var MAX_WAIT_MS = 2800;
  var STORAGE_KEY = "wase_splash_done";
  var BRAND = "#891E2B";
  var dismissed = false;

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
      return splash;
    }
    if (!document.body) {
      return null;
    }

    splash = document.createElement("div");
    splash.id = "splash-screen";
    splash.setAttribute("role", "presentation");
    splash.setAttribute("aria-hidden", "true");
    splash.innerHTML =
      '<div class="splash-screen__brand">' +
      '<img class="splash-screen__logo" src="' +
      logoSrc() +
      '" alt="わせわせ" width="220" height="192" decoding="async">' +
      "</div>" +
      '<p class="splash-screen__footer">Anonymous Waseda Developer</p>';
    document.body.appendChild(splash);
    window.__waseSplashMountedAt = Date.now();
    return splash;
  }

  function clearPendingClass() {
    document.documentElement.classList.remove("wase-splash-pending");
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
    var force = options && options.force;
    var mountedAt = window.__waseSplashMountedAt || Date.now();
    var elapsed = Date.now() - mountedAt;
    var wait = force ? 0 : Math.max(0, MIN_VISIBLE_MS - elapsed);

    window.setTimeout(function () {
      splash.classList.add("is-hiding");
      window.setTimeout(function () {
        if (splash.parentNode) {
          splash.parentNode.removeChild(splash);
        }
        clearPendingClass();
        try {
          sessionStorage.setItem(STORAGE_KEY, "1");
        } catch (e) {}
      }, FADE_MS);
    }, wait);
  }

  window.WaseSplashScreen = {
    dismiss: dismissSplashScreen,
    ensureMounted: ensureMounted,
  };

  if (!isNativeApp()) {
    return;
  }

  if (document.body) {
    ensureMounted();
  } else {
    document.addEventListener("DOMContentLoaded", ensureMounted, { once: true });
  }

  window.setTimeout(function () {
    dismissSplashScreen({ force: false });
  }, MAX_WAIT_MS);
})(window, document);
