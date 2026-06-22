/**
 * Capacitor ネイティブアプリ（iOS）向け: AdMob + プッシュ通知の初期化。
 * Web ブラウザでは何もしません。
 */
(function (window) {
  "use strict";

  var ADMOB_TEST_IDS = {
    banner: "ca-app-pub-3940256099942544/2934735716",
    interstitial: "ca-app-pub-3940256099942544/4411468910",
  };

  function isNativeApp() {
    return (
      window.Capacitor &&
      typeof window.Capacitor.isNativePlatform === "function" &&
      window.Capacitor.isNativePlatform()
    );
  }

  function getPlugin(name) {
    if (!window.Capacitor || !window.Capacitor.Plugins) {
      return null;
    }
    return window.Capacitor.Plugins[name] || null;
  }

  function logNative(label, detail) {
    if (window.console && console.info) {
      console.info("[WaseCapacitor] " + label, detail || "");
    }
  }

  function getCsrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function getPushPlatform() {
    if (!window.Capacitor || !window.Capacitor.getPlatform) {
      return "ios";
    }
    var platform = window.Capacitor.getPlatform();
    return platform === "android" ? "android" : "ios";
  }

  async function registerTokenWithBackend(token) {
    if (!token) {
      return;
    }

    try {
      var response = await fetch("/api/push-token/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        credentials: "same-origin",
        body: JSON.stringify({
          token: token,
          platform: getPushPlatform(),
        }),
      });

      if (!response.ok) {
        logNative("Push token registration failed", response.status);
        return;
      }

      logNative("Push token registered with backend");
    } catch (error) {
      logNative("Push token registration error", error);
    }
  }

  async function initializePushNotifications() {
    var PushNotifications = getPlugin("PushNotifications");
    if (!PushNotifications) {
      logNative("PushNotifications plugin not found");
      return;
    }

    await PushNotifications.addListener("registration", function (token) {
      window.WASE_PUSH_TOKEN = token.value;
      logNative("Push token acquired", token.value);
      window.dispatchEvent(
        new CustomEvent("wase:push-token", { detail: token.value })
      );
      registerTokenWithBackend(token.value);
    });

    await PushNotifications.addListener("registrationError", function (error) {
      logNative("Push registration error", error);
    });

    await PushNotifications.addListener("pushNotificationReceived", function (notification) {
      logNative("Push received (foreground)", notification);
    });

    await PushNotifications.addListener("pushNotificationActionPerformed", function (action) {
      logNative("Push action performed", action);
    });

    var permission = await PushNotifications.requestPermissions();
    logNative("Push permission", permission);

    if (permission.receive === "granted") {
      await PushNotifications.register();
    }
  }

  async function initializeAdMob() {
    var AdMob = getPlugin("AdMob");
    if (!AdMob) {
      logNative("AdMob plugin not found");
      return;
    }

    await AdMob.initialize({
      initializeForTesting: true,
      requestTrackingAuthorization: true,
    });

    await AdMob.showBanner({
      adId: ADMOB_TEST_IDS.banner,
      adSize: "ADAPTIVE_BANNER",
      position: "BOTTOM_CENTER",
      margin: 64,
      isTesting: true,
    });

    document.documentElement.classList.add("has-native-banner-ad");
    logNative("Banner ad requested");
  }

  async function showInterstitialAd() {
    var AdMob = getPlugin("AdMob");
    if (!AdMob) {
      return;
    }

    await AdMob.prepareInterstitial({
      adId: ADMOB_TEST_IDS.interstitial,
      isTesting: true,
    });
    await AdMob.showInterstitial();
    logNative("Interstitial ad shown");
  }

  function handlePageTriggers() {
    var params = new URLSearchParams(window.location.search);
    if (params.get("exhibit_success") === "1") {
      showInterstitialAd().catch(function (error) {
        logNative("Interstitial failed", error);
      });
    }
  }

  async function bootstrap() {
    if (!isNativeApp()) {
      return;
    }

    try {
      await initializePushNotifications();
      await initializeAdMob();
      if (window.WASE_PUSH_TOKEN) {
        await registerTokenWithBackend(window.WASE_PUSH_TOKEN);
      }
      handlePageTriggers();
    } catch (error) {
      logNative("bootstrap failed", error);
    }
  }

  window.WaseCapacitor = {
    isNativeApp: isNativeApp,
    showInterstitialAd: showInterstitialAd,
    getPushToken: function () {
      return window.WASE_PUSH_TOKEN || null;
    },
    registerPushToken: registerTokenWithBackend,
  };

  function startWhenReady() {
    if (window.Capacitor) {
      bootstrap();
      return;
    }
    window.addEventListener("capacitor:ready", bootstrap, { once: true });
    document.addEventListener("DOMContentLoaded", function () {
      if (window.Capacitor) {
        bootstrap();
      }
    });
  }

  startWhenReady();
})(window);
