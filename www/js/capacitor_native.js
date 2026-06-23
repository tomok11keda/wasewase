/**
 * Capacitor ネイティブアプリ（iOS）向け: AdMob + プッシュ通知。
 * Web ブラウザでは AdMob は動作しません。
 */
(function (window) {
  "use strict";

  var MIN_INTERSTITIAL_INTERVAL_MS = 90000;
  var BANNER_REPOSITION_DEBOUNCE_MS = 100;
  var BANNER_MARGIN_EPSILON = 4;
  var bannerVisible = false;
  var bannerMode = "none";
  var interstitialPrepared = false;
  var appOpenHandled = false;
  var currentBannerAnchor = null;
  var currentBannerHeight = 50;
  var lastBannerMargin = -1;
  var bannerTrackingReady = false;
  var bannerRepositionTimer = null;
  var bannerRepositionInFlight = false;

  function getAdMobConfig() {
    return window.WASE_ADMOB_CONFIG || {};
  }

  function isProductionAds() {
    return Boolean(getAdMobConfig().useProductionAds);
  }

  function getActiveAdIds() {
    var config = getAdMobConfig();
    return isProductionAds() ? config.production : config.test;
  }

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

  function canShowInterstitialNow() {
    var lastShown = Number(sessionStorage.getItem("wase_last_interstitial_at") || "0");
    return Date.now() - lastShown >= MIN_INTERSTITIAL_INTERVAL_MS;
  }

  function markInterstitialShown() {
    sessionStorage.setItem("wase_last_interstitial_at", String(Date.now()));
  }

  function cleanAdTriggerParams() {
    var params = new URLSearchParams(window.location.search);
    var changed = false;
    ["login_success", "exhibit_success"].forEach(function (key) {
      if (params.has(key)) {
        params.delete(key);
        changed = true;
      }
    });
    if (!changed) {
      return;
    }
    var query = params.toString();
    var nextUrl =
      window.location.pathname + (query ? "?" + query : "") + window.location.hash;
    window.history.replaceState({}, "", nextUrl);
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
      return false;
    }

    var testing = !isProductionAds();
    await AdMob.initialize({
      initializeForTesting: testing,
      requestTrackingAuthorization: true,
    });

    if (typeof AdMob.requestTrackingAuthorization === "function") {
      try {
        var tracking = await AdMob.trackingAuthorizationStatus();
        if (tracking && tracking.status === "notDetermined") {
          await AdMob.requestTrackingAuthorization();
        }
      } catch (error) {
        logNative("ATT request skipped", error);
      }
    }

    logNative("AdMob initialized", { testing: testing });
    return true;
  }

  function setBannerLayoutClass(mode) {
    var root = document.documentElement;
    root.classList.remove("has-native-banner-ad", "has-native-bottom-banner");
    if (mode === "bottom") {
      root.classList.add("has-native-bottom-banner");
    }
  }

  function isAnchorVisible(anchor) {
    if (!anchor || !anchor.getBoundingClientRect) {
      return false;
    }
    var rect = anchor.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) {
      return false;
    }
    var style = window.getComputedStyle(anchor);
    if (style.display === "none" || style.visibility === "hidden") {
      return false;
    }
    var viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    if (rect.bottom < 24 || rect.top > viewportHeight - 16) {
      return false;
    }
    return true;
  }

  function getAnchorIntersectionArea(rect) {
    var viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    var viewportWidth = window.innerWidth || document.documentElement.clientWidth;
    var top = Math.max(rect.top, 0);
    var left = Math.max(rect.left, 0);
    var bottom = Math.min(rect.bottom, viewportHeight);
    var right = Math.min(rect.right, viewportWidth);
    return Math.max(0, bottom - top) * Math.max(0, right - left);
  }

  function getAdAnchorCandidates() {
    var tab = new URLSearchParams(window.location.search).get("tab") || "board";
    if (tab === "flea") {
      return Array.prototype.slice.call(
        document.querySelectorAll(".flea-banner-ad-slot.wase-admob-anchor")
      );
    }
    return Array.prototype.slice.call(
      document.querySelectorAll(".timeline-ad-slot.wase-admob-anchor")
    );
  }

  function findBestAdAnchor() {
    var candidates = getAdAnchorCandidates().filter(isAnchorVisible);
    if (!candidates.length) {
      candidates = Array.prototype.slice
        .call(document.querySelectorAll(".wase-admob-anchor"))
        .filter(isAnchorVisible);
    }
    if (!candidates.length) {
      return null;
    }
    candidates.sort(function (a, b) {
      return (
        getAnchorIntersectionArea(b.getBoundingClientRect()) -
        getAnchorIntersectionArea(a.getBoundingClientRect())
      );
    });
    return candidates[0];
  }

  function computeBannerTopMargin(anchor, bannerHeight) {
    var rect = anchor.getBoundingClientRect();
    var height = bannerHeight || currentBannerHeight || 50;
    var centeredTop = rect.top + Math.max(0, (rect.height - height) / 2);
    return Math.round(Math.max(0, centeredTop));
  }

  function markActiveBannerAnchor(anchor) {
    if (currentBannerAnchor && currentBannerAnchor !== anchor) {
      currentBannerAnchor.classList.remove("is-admob-anchor-active");
    }
    currentBannerAnchor = anchor;
    if (currentBannerAnchor) {
      currentBannerAnchor.classList.add("is-admob-anchor-active");
    }
  }

  async function hideBannerAd() {
    var AdMob = getPlugin("AdMob");
    if (!AdMob || !bannerVisible) {
      return;
    }
    if (typeof AdMob.removeBanner === "function") {
      try {
        await AdMob.removeBanner();
      } catch (error) {
        logNative("removeBanner failed", error);
      }
    }
    bannerVisible = false;
    bannerMode = "none";
    lastBannerMargin = -1;
    setBannerLayoutClass("none");
  }

  async function renderBanner(options) {
    var AdMob = getPlugin("AdMob");
    if (!AdMob) {
      return false;
    }

    if (bannerVisible) {
      await hideBannerAd();
    }

    await AdMob.showBanner(options);
    bannerVisible = true;
    logNative("Banner ad rendered", {
      position: options.position,
      margin: options.margin,
      testing: options.isTesting,
    });
    return true;
  }

  async function showBottomFallbackBanner() {
    var ids = getActiveAdIds();
    var testing = !isProductionAds();
    if (currentBannerAnchor) {
      currentBannerAnchor.classList.remove("is-admob-anchor-active");
      currentBannerAnchor = null;
    }
    await renderBanner({
      adId: ids.banner,
      adSize: "ADAPTIVE_BANNER",
      position: "BOTTOM_CENTER",
      margin: 0,
      isTesting: testing,
    });
    bannerMode = "bottom";
    setBannerLayoutClass("bottom");
  }

  async function positionBannerAtAnchor(anchor) {
    if (!anchor) {
      await showBottomFallbackBanner();
      return;
    }

    var margin = computeBannerTopMargin(anchor, currentBannerHeight);
    if (
      bannerVisible &&
      bannerMode === "inline" &&
      currentBannerAnchor === anchor &&
      Math.abs(margin - lastBannerMargin) < BANNER_MARGIN_EPSILON
    ) {
      return;
    }

    var ids = getActiveAdIds();
    var testing = !isProductionAds();
    markActiveBannerAnchor(anchor);
    await renderBanner({
      adId: ids.banner,
      adSize: "ADAPTIVE_BANNER",
      position: "TOP_CENTER",
      margin: margin,
      isTesting: testing,
    });
    bannerMode = "inline";
    lastBannerMargin = margin;
    setBannerLayoutClass("none");
  }

  async function repositionInlineBanner() {
    if (bannerRepositionInFlight) {
      return;
    }
    bannerRepositionInFlight = true;
    try {
      var anchor = findBestAdAnchor();
      if (!anchor) {
        if (bannerMode === "inline") {
          await hideBannerAd();
          if (currentBannerAnchor) {
            currentBannerAnchor.classList.remove("is-admob-anchor-active");
            currentBannerAnchor = null;
          }
        }
        return;
      }
      await positionBannerAtAnchor(anchor);
    } catch (error) {
      logNative("Banner reposition failed", error);
    } finally {
      bannerRepositionInFlight = false;
    }
  }

  function scheduleBannerReposition() {
    if (!bannerTrackingReady) {
      return;
    }
    if (bannerRepositionTimer) {
      clearTimeout(bannerRepositionTimer);
    }
    bannerRepositionTimer = setTimeout(function () {
      repositionInlineBanner().catch(function (error) {
        logNative("Deferred banner reposition failed", error);
      });
    }, BANNER_REPOSITION_DEBOUNCE_MS);
  }

  function setupInlineBannerTracking() {
    if (bannerTrackingReady) {
      return;
    }
    bannerTrackingReady = true;

    window.addEventListener("scroll", scheduleBannerReposition, { passive: true });
    window.addEventListener("resize", scheduleBannerReposition);
    window.addEventListener("orientationchange", scheduleBannerReposition);

    var AdMob = getPlugin("AdMob");
    if (AdMob && typeof AdMob.addListener === "function") {
      AdMob.addListener("bannerAdSizeChanged", function (size) {
        if (size && size.height) {
          currentBannerHeight = size.height;
          scheduleBannerReposition();
        }
      });
    }

    var timelineList = document.getElementById("timeline-list");
    if (timelineList && "MutationObserver" in window) {
      new MutationObserver(scheduleBannerReposition).observe(timelineList, {
        childList: true,
        subtree: true,
      });
    }
  }

  async function showBannerAd() {
    if (!getPlugin("AdMob")) {
      return;
    }

    setupInlineBannerTracking();
    var anchor = findBestAdAnchor();
    if (anchor) {
      await positionBannerAtAnchor(anchor);
      return;
    }

    await showBottomFallbackBanner();
  }

  async function prepareInterstitialAd() {
    var AdMob = getPlugin("AdMob");
    if (!AdMob) {
      return false;
    }

    var ids = getActiveAdIds();
    await AdMob.prepareInterstitial({
      adId: ids.interstitial,
      isTesting: !isProductionAds(),
    });
    interstitialPrepared = true;
    return true;
  }

  async function showInterstitialAd(reason) {
    if (!canShowInterstitialNow()) {
      logNative("Interstitial skipped (cooldown)", reason || "");
      return false;
    }

    var AdMob = getPlugin("AdMob");
    if (!AdMob) {
      return false;
    }

    try {
      if (!interstitialPrepared) {
        await prepareInterstitialAd();
      }
      await AdMob.showInterstitial();
      interstitialPrepared = false;
      markInterstitialShown();
      logNative("Interstitial shown", reason || "");
      prepareInterstitialAd().catch(function (error) {
        logNative("Interstitial preload failed", error);
      });
      return true;
    } catch (error) {
      interstitialPrepared = false;
      logNative("Interstitial failed", error);
      return false;
    }
  }

  async function showAppOpenAd() {
    if (appOpenHandled) {
      return;
    }
    appOpenHandled = true;

    var AdMob = getPlugin("AdMob");
    if (!AdMob) {
      return;
    }

    var ids = getActiveAdIds();
    var testing = !isProductionAds();

    try {
      if (typeof AdMob.loadAppOpen === "function") {
        await AdMob.loadAppOpen({
          adId: ids.appOpen,
          isTesting: testing,
        });
        var loaded = await AdMob.isAppOpenLoaded();
        if (loaded && loaded.value) {
          await AdMob.showAppOpen();
          logNative("App open ad shown", { testing: testing });
          return;
        }
        logNative("App open ad not loaded in time");
        return;
      }

      logNative("App Open API unavailable; using interstitial fallback");
      await AdMob.prepareInterstitial({
        adId: ids.interstitial,
        isTesting: testing,
      });
      await AdMob.showInterstitial();
      interstitialPrepared = false;
      markInterstitialShown();
      logNative("Launch interstitial fallback shown", { testing: testing });
    } catch (error) {
      logNative("App open ad failed", error);
    }
  }

  function handlePageTriggers() {
    var params = new URLSearchParams(window.location.search);
    var triggers = [];

    if (params.get("login_success") === "1") {
      triggers.push("login_success");
    }
    if (params.get("exhibit_success") === "1") {
      triggers.push("exhibit_success");
    }

    var tab = params.get("tab") || "board";
    var lastTab = sessionStorage.getItem("wase_last_tab");
    if (lastTab && lastTab !== tab && triggers.length === 0) {
      triggers.push("tab_switch:" + lastTab + "->" + tab);
    }
    sessionStorage.setItem("wase_last_tab", tab);

    if (triggers.length === 0) {
      return;
    }

    showInterstitialAd(triggers.join(","))
      .catch(function (error) {
        logNative("Page trigger interstitial failed", error);
      })
      .finally(function () {
        cleanAdTriggerParams();
      });
  }

  async function bootstrap() {
    if (!isNativeApp()) {
      return;
    }

    document.documentElement.classList.add("is-native-capacitor");

    try {
      var adsReady = await initializeAdMob();
      if (adsReady) {
        await showAppOpenAd();
        if (document.readyState === "loading") {
          await new Promise(function (resolve) {
            document.addEventListener("DOMContentLoaded", resolve, { once: true });
          });
        }
        await new Promise(function (resolve) {
          requestAnimationFrame(function () {
            requestAnimationFrame(resolve);
          });
        });
        await showBannerAd();
        prepareInterstitialAd().catch(function (error) {
          logNative("Initial interstitial preload failed", error);
        });
      }

      await initializePushNotifications();

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
    isProductionAds: isProductionAds,
    getActiveAdIds: getActiveAdIds,
    showInterstitialAd: showInterstitialAd,
    showBannerAd: showBannerAd,
    showAppOpenAd: showAppOpenAd,
    repositionBannerAd: repositionInlineBanner,
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
