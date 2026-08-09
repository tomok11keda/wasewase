/**
 * Capacitor ネイティブアプリ（iOS）向け: AdMob + プッシュ通知 + Firebase Analytics。
 * Web ブラウザでは AdMob は動作しません。
 */
(function (window) {
  "use strict";

  var MIN_INTERSTITIAL_INTERVAL_MS = 90000;
  var BANNER_REPOSITION_DEBOUNCE_MS = 100;
  var BANNER_MARGIN_EPSILON = 4;
  var APP_OPEN_STORAGE_KEY = "wase_app_open_ad_day";
  var CREATION_AD_PARAMS = [
    "post_success",
    "exhibit_success",
    "thread_success",
    "thread_reply_success",
  ];
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
  var bannerFailureListenersReady = false;
  var lastTrackedAnalyticsScreen = "";

  /**
   * TestFlight 切り分け用フラグ。通常時はすべて false（本番挙動を変えない）。
   *
   * URL: /app/?spa_nav_diag=off|no_banner|no_ads|no_analytics|no_bridge|no_keepalive|no_transition
   * 解除: ?spa_nav_diag=clear
   * または localStorage.wase_spa_nav_diag / window.WASE_SPA_NAV_DIAG
   */
  function readSpaNavDiag() {
    var flags = {
      disableAll: false,
      disableAnalytics: false,
      disableAds: false,
      disableBannerReposition: false,
      disableBridge: false,
    };
    try {
      if (window.WASE_SPA_NAV_DIAG && typeof window.WASE_SPA_NAV_DIAG === "object") {
        flags.disableAll = Boolean(window.WASE_SPA_NAV_DIAG.disableAll);
        flags.disableAnalytics = Boolean(window.WASE_SPA_NAV_DIAG.disableAnalytics);
        flags.disableAds = Boolean(window.WASE_SPA_NAV_DIAG.disableAds);
        flags.disableBannerReposition = Boolean(
          window.WASE_SPA_NAV_DIAG.disableBannerReposition
        );
        flags.disableBridge = Boolean(window.WASE_SPA_NAV_DIAG.disableBridge);
      }
      var stored = null;
      try {
        stored = window.localStorage.getItem("wase_spa_nav_diag");
      } catch (e) {
        stored = null;
      }
      var raw = stored || "";
      try {
        var params = new URLSearchParams(window.location.search || "");
        if (params.has("spa_nav_diag")) {
          raw = params.get("spa_nav_diag") || "";
          try {
            if (!raw || raw === "clear" || raw === "default" || raw === "reset") {
              window.localStorage.removeItem("wase_spa_nav_diag");
              raw = "";
            } else {
              window.localStorage.setItem("wase_spa_nav_diag", raw);
            }
          } catch (ePersist) {
            /* ignore */
          }
        }
      } catch (e2) {
        /* ignore */
      }
      if (raw) {
        var parts = String(raw)
          .toLowerCase()
          .split(/[,+\s]+/)
          .filter(Boolean);
        parts.forEach(function (p) {
          if (p === "off" || p === "no_all" || p === "all") {
            flags.disableAll = true;
          }
          if (p === "no_analytics" || p === "analytics") {
            flags.disableAnalytics = true;
          }
          if (p === "no_ads" || p === "ads") {
            flags.disableAds = true;
          }
          if (p === "no_banner" || p === "banner") {
            flags.disableBannerReposition = true;
          }
          if (p === "no_bridge" || p === "bridge") {
            flags.disableBridge = true;
          }
        });
      }
    } catch (err) {
      /* ignore */
    }
    if (flags.disableAll) {
      flags.disableAnalytics = true;
      flags.disableAds = true;
      flags.disableBannerReposition = true;
      flags.disableBridge = true;
    }
    return flags;
  }

  var DEFAULT_ADMOB_IDS = {
    test: {
      appId: "ca-app-pub-3940256099942544~1458002511",
      banner: "ca-app-pub-3940256099942544/2934735716",
      interstitial: "ca-app-pub-3940256099942544/4411468910",
      appOpen: "ca-app-pub-3940256099942544/5575463023",
    },
    production: {
      appId: "ca-app-pub-3330130877204303~8437918867",
      banner: "ca-app-pub-3330130877204303/8624675602",
      interstitial: "ca-app-pub-3330130877204303/5502432638",
      appOpen: "ca-app-pub-3330130877204303/9431324966",
    },
  };

  function flashDiagMark(type, payload) {
    try {
      if (window.WaseFlashDiag && typeof window.WaseFlashDiag.mark === "function") {
        window.WaseFlashDiag.mark(type, payload || null);
      }
    } catch (e) {
      /* ignore */
    }
  }

  function flashDiagSnapshot(reason) {
    try {
      if (
        window.WaseFlashDiag &&
        typeof window.WaseFlashDiag.snapshotNative === "function"
      ) {
        return window.WaseFlashDiag.snapshotNative(reason);
      }
    } catch (e) {
      /* ignore */
    }
    return Promise.resolve(null);
  }

  function getAdMobConfig() {
    return window.WASE_ADMOB_CONFIG || {};
  }

  function areAdsDisabled() {
    return Boolean(getAdMobConfig().DISABLE_ADS);
  }

  function isProductionAds() {
    return Boolean(getAdMobConfig().useProductionAds);
  }

  function getActiveAdIds() {
    var config = getAdMobConfig();
    if (isProductionAds()) {
      return config.production || DEFAULT_ADMOB_IDS.production;
    }
    return config.test || DEFAULT_ADMOB_IDS.test;
  }

  function isNativeApp() {
    return (
      window.Capacitor &&
      typeof window.Capacitor.isNativePlatform === "function" &&
      window.Capacitor.isNativePlatform()
    );
  }

  /**
   * WKWebView で env(safe-area-inset-top) が 0 / 過小になる場合の補完。
   * Dynamic Island 機では最低 59px を確保し、計測値との大きい方を採用する。
   */
  function getNativeSafeAreaTopMinimum() {
    var screenHeight = window.screen ? window.screen.height || 0 : 0;
    var screenWidth = window.screen ? window.screen.width || 0 : 0;
    var longSide = Math.max(screenHeight, screenWidth);
    var shortSide = Math.min(screenHeight, screenWidth);

    // iPhone 14 Pro / 15 / 16 系（Dynamic Island）
    if (longSide >= 852 && shortSide >= 390) {
      return 59;
    }
    // Face ID ノッチ機
    if (longSide >= 812) {
      return 47;
    }
    return 20;
  }

  function measureEnvSafeAreaTop() {
    try {
      var probe = document.createElement("div");
      probe.style.cssText =
        "position:absolute;visibility:hidden;pointer-events:none;" +
        "padding-top:env(safe-area-inset-top, 0px);";
      document.documentElement.appendChild(probe);
      var measured = window.getComputedStyle(probe).paddingTop;
      document.documentElement.removeChild(probe);
      return parseFloat(measured) || 0;
    } catch (error) {
      logNativeError("safe-area-top probe failed", error);
      return 0;
    }
  }

  function ensureSafeAreaTopCssVar() {
    try {
      var measured = measureEnvSafeAreaTop();
      var minimum = isNativeApp() ? getNativeSafeAreaTopMinimum() : 0;
      var value = Math.max(measured, minimum);
      var root = document.documentElement;
      // 一度決めた値はスクロール中に揺らさない（ヘッダー高さの再計算を防ぐ）
      root.style.setProperty("--wase-sat-fallback", minimum + "px");
      root.style.setProperty("--wase-sat", value + "px");
      // ネイティブでは :root の env() ベース計算を上書きし、固定 px にロック
      if (isNativeApp()) {
        var padY = 10;
        var contentMin = 44;
        var headerH = value + contentMin + padY * 2;
        root.style.setProperty("--wase-header-h", headerH + "px");
      }
      if (value > measured) {
        logNative("safe-area-top raised to device minimum", {
          measured: measured,
          minimum: minimum,
          applied: value,
        });
      }
    } catch (error) {
      logNativeError("safe-area-top update failed", error);
    }
  }

  function bindSafeAreaTopListeners() {
    if (!isNativeApp() || window.__waseSafeAreaBound) {
      return;
    }
    window.__waseSafeAreaBound = true;
    // 回転時のみ再計測する。
    // resize / visualViewport は iOS のアドレスバー伸縮やスクロール中にも発火し、
    // --wase-sat が揺れてヘッダーがガタつくため購読しない。
    window.addEventListener("orientationchange", function () {
      window.setTimeout(ensureSafeAreaTopCssVar, 300);
    });
  }

  function getPlugin(name) {
    if (!window.Capacitor) {
      return null;
    }
    // Capacitor 3+ は getPlugin が正式。Plugins 辞書だけだと見つからないことがある。
    if (typeof window.Capacitor.getPlugin === "function") {
      try {
        var viaGet = window.Capacitor.getPlugin(name);
        if (viaGet) {
          return viaGet;
        }
      } catch (error) {
        logNativeError("Capacitor.getPlugin(" + name + ") failed", error);
      }
    }
    if (window.Capacitor.Plugins && window.Capacitor.Plugins[name]) {
      return window.Capacitor.Plugins[name];
    }
    return null;
  }

  var CAMERA_PERMISSION_REQUIRED_MESSAGE =
    "設定からカメラの使用を許可してください";
  var PHOTOS_PERMISSION_REQUIRED_MESSAGE =
    "設定から写真ライブラリの使用を許可してください";

  function showCameraAlert(message) {
    if (typeof window.alert === "function") {
      window.alert(message);
    }
  }

  /**
   * 実機デバッグ用: Safari コンソール無しでもエラー内容を alert で確認する。
   * Error は JSON.stringify だと {} になるため、主要フィールドを展開する。
   */
  function alertCameraDebugError(e, context, extra) {
    var payload = e;
    if (e instanceof Error) {
      payload = {
        context: context || null,
        name: e.name,
        message: e.message,
        stack: e.stack,
        code: e.code,
      };
      try {
        Object.keys(e).forEach(function (key) {
          payload[key] = e[key];
        });
      } catch (_ignore) {}
    } else if (e && typeof e === "object") {
      payload = { context: context || null };
      try {
        Object.keys(e).forEach(function (key) {
          payload[key] = e[key];
        });
      } catch (_ignore) {
        payload.raw = String(e);
      }
      if (e.message) payload.message = e.message;
      if (e.code) payload.code = e.code;
      if (e.errorMessage) payload.errorMessage = e.errorMessage;
    } else {
      payload = { context: context || null, value: e, raw: String(e) };
    }
    if (extra && typeof extra === "object") {
      try {
        Object.keys(extra).forEach(function (key) {
          payload[key] = extra[key];
        });
      } catch (_ignoreExtra) {}
    }
    try {
      console.error("[WASE Camera]", context || "error", e, extra || null);
    } catch (_consoleIgnore) {}
    try {
      alert(JSON.stringify(payload, null, 2));
    } catch (_stringifyError) {
      alert(String(context || "camera-debug") + ": " + String(e));
    }
  }

  function dataUrlToFile(dataUrl, filename) {
    var parts = String(dataUrl || "").split(",");
    if (parts.length < 2) {
      throw new Error("invalid dataUrl");
    }
    var mimeMatch = parts[0].match(/:(.*?);/);
    var mime = (mimeMatch && mimeMatch[1]) || "image/jpeg";
    var binary = atob(parts[1]);
    var len = binary.length;
    var bytes = new Uint8Array(len);
    for (var i = 0; i < len; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return new File([bytes], filename, { type: mime });
  }

  function base64ToFile(base64, filename, mimeType) {
    var binary = atob(String(base64 || ""));
    var len = binary.length;
    var bytes = new Uint8Array(len);
    for (var i = 0; i < len; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return new File([bytes], filename, { type: mimeType || "image/jpeg" });
  }

  async function photoResultToFile(photo, stepMeta) {
    var filename = "camera_" + Date.now() + ".jpg";
    if (photo && photo.dataUrl) {
      stepMeta.step = "dataUrlToFile";
      return dataUrlToFile(photo.dataUrl, filename);
    }
    if (photo && photo.base64String) {
      stepMeta.step = "base64ToFile";
      var format = String(photo.format || "jpeg").toLowerCase();
      var mime = format === "png" ? "image/png" : "image/jpeg";
      return base64ToFile(photo.base64String, filename, mime);
    }

    // 最終手段: webPath / path を fetch（iOS では TypeError: Load failed になりやすい）
    var src = photo && (photo.webPath || photo.path);
    if (
      photo &&
      photo.path &&
      window.Capacitor &&
      typeof window.Capacitor.convertFileSrc === "function"
    ) {
      try {
        src = window.Capacitor.convertFileSrc(photo.path);
        stepMeta.convertFileSrc = src;
      } catch (convertError) {
        stepMeta.convertFileSrcError = String(
          (convertError && convertError.message) || convertError
        );
      }
    }
    if (!src) {
      throw new Error("photo has no dataUrl/base64/webPath");
    }
    stepMeta.step = "fetch(webPath)";
    stepMeta.fetchUrl = src;
    var response = await fetch(src);
    if (!response || !response.ok) {
      throw new Error(
        "failed to fetch camera photo status=" +
          (response && response.status)
      );
    }
    stepMeta.step = "response.blob";
    var blob = await response.blob();
    if (!blob || !blob.size) {
      throw new Error("empty camera photo");
    }
    stepMeta.step = "new File(blob)";
    return new File([blob], filename, { type: blob.type || "image/jpeg" });
  }

  function isCameraAuthorizationGranted(status) {
    return status === "authorized" || status === "granted" || status === "limited";
  }

  function isCameraAuthorizationBlocked(status) {
    return status === "denied" || status === "restricted";
  }

  function mapCapacitorCameraPermission(status) {
    if (status === "granted" || status === "limited") {
      return "authorized";
    }
    if (status === "denied") {
      return "denied";
    }
    if (status === "prompt") {
      return "notDetermined";
    }
    return status || "unknown";
  }

  function isPermissionDeniedError(error) {
    var message = String(
      (error && (error.message || error.localizedDescription || error.code)) ||
        error ||
        ""
    ).toLowerCase();
    return (
      message.indexOf("permission") >= 0 ||
      message.indexOf("denied") >= 0 ||
      message.indexOf("access") >= 0 ||
      message.indexOf("authorized") >= 0 ||
      message.indexOf("os-plug-camr-0003") >= 0 ||
      message.indexOf("os-plug-camr-0005") >= 0
    );
  }

  async function requestCapacitorCameraPermissions(permissions) {
    var Camera = getPlugin("Camera");
    if (!Camera || typeof Camera.requestPermissions !== "function") {
      alertCameraDebugError(
        {
          step: "requestPermissions",
          hasCameraPlugin: !!Camera,
          hasRequestPermissions: !!(Camera && Camera.requestPermissions),
          pluginKeys: Camera ? Object.keys(Camera) : [],
          capacitorPlugins:
            window.Capacitor && window.Capacitor.Plugins
              ? Object.keys(window.Capacitor.Plugins)
              : [],
          hasGetPlugin: !!(window.Capacitor && window.Capacitor.getPlugin),
        },
        "Camera.requestPermissions unavailable"
      );
      return null;
    }
    try {
      var permission = await Camera.requestPermissions({
        permissions: permissions || ["camera", "photos"],
      });
      // デバッグ: 権限 status を画面と console の両方に出す
      console.log("[WASE Camera] requestPermissions status", permission);
      alert(JSON.stringify({ step: "requestPermissions", status: permission }, null, 2));
      return permission;
    } catch (e) {
      logNativeError("Camera.requestPermissions failed", e);
      alert(JSON.stringify(e, null, 2));
      alertCameraDebugError(e, "Camera.requestPermissions catch");
      return null;
    }
  }

  async function checkNativeCameraAuthorization() {
    var Camera = getPlugin("Camera");
    if (Camera && typeof Camera.checkPermissions === "function") {
      try {
        var permission = await Camera.checkPermissions();
        console.log("[WASE Camera] checkPermissions status", permission);
        return mapCapacitorCameraPermission(permission && permission.camera);
      } catch (e) {
        logNativeError("Camera.checkPermissions failed", e);
        alert(JSON.stringify(e, null, 2));
        alertCameraDebugError(e, "Camera.checkPermissions catch");
        return "unknown";
      }
    }

    var NativePermission = getPlugin("CameraPermission");
    if (
      NativePermission &&
      typeof NativePermission.checkAuthorization === "function"
    ) {
      try {
        var nativeResult = await NativePermission.checkAuthorization();
        console.log("[WASE Camera] CameraPermission.checkAuthorization", nativeResult);
        return (nativeResult && nativeResult.status) || "unknown";
      } catch (e) {
        logNativeError("CameraPermission.checkAuthorization failed", e);
        alert(JSON.stringify(e, null, 2));
        alertCameraDebugError(e, "CameraPermission.checkAuthorization catch");
        return "unknown";
      }
    }

    return "unknown";
  }

  async function requestNativePhotosAuthorization() {
    var permission = await requestCapacitorCameraPermissions(["photos"]);
    if (!permission) {
      return "unknown";
    }
    return mapCapacitorCameraPermission(permission.photos);
  }

  async function ensurePhotosAccess() {
    try {
      var Camera = getPlugin("Camera");
      if (!Camera || typeof Camera.checkPermissions !== "function") {
        return { ok: true };
      }
      var permission = await Camera.checkPermissions();
      console.log("[WASE Camera] photos checkPermissions status", permission);
      var status = mapCapacitorCameraPermission(permission && permission.photos);
      if (isCameraAuthorizationGranted(status)) {
        return { ok: true };
      }
      if (!isCameraAuthorizationBlocked(status)) {
        status = await requestNativePhotosAuthorization();
        if (isCameraAuthorizationGranted(status)) {
          return { ok: true };
        }
      }
      showCameraAlert(PHOTOS_PERMISSION_REQUIRED_MESSAGE);
      return { ok: false, reason: "photos_denied" };
    } catch (e) {
      logNativeError("Photos permission check failed", e);
      alert(JSON.stringify(e, null, 2));
      alertCameraDebugError(e, "ensurePhotosAccess catch");
      return { ok: false, reason: "photos_error" };
    }
  }

  async function requestNativeCameraAuthorization() {
    // まず Capacitor Camera 公式 API で要求（戻り値を alert / console に出す）
    var permission = await requestCapacitorCameraPermissions(["camera", "photos"]);
    if (permission) {
      return mapCapacitorCameraPermission(permission.camera);
    }

    var NativePermission = getPlugin("CameraPermission");
    if (
      NativePermission &&
      typeof NativePermission.requestAuthorization === "function"
    ) {
      try {
        var nativeResult = await NativePermission.requestAuthorization();
        console.log("[WASE Camera] CameraPermission.requestAuthorization", nativeResult);
        alert(
          JSON.stringify(
            { step: "CameraPermission.requestAuthorization", result: nativeResult },
            null,
            2
          )
        );
        return (nativeResult && nativeResult.status) || "unknown";
      } catch (e) {
        logNativeError("CameraPermission.requestAuthorization failed", e);
        alert(JSON.stringify(e, null, 2));
        alertCameraDebugError(e, "CameraPermission.requestAuthorization catch");
        return "unknown";
      }
    }

    return "unknown";
  }

  /**
   * UIImagePickerController.isSourceTypeAvailable(.camera) 相当のチェック。
   * シミュレーターやカメラ非搭載端末では false。
   */
  async function isNativeCameraHardwareAvailable() {
    try {
      var NativePermission = getPlugin("CameraPermission");
      if (
        NativePermission &&
        typeof NativePermission.isCameraAvailable === "function"
      ) {
        var result = await NativePermission.isCameraAvailable();
        if (result && typeof result.available === "boolean") {
          return result.available;
        }
        if (result && typeof result.camera === "boolean") {
          return result.camera;
        }
      }
    } catch (error) {
      logNativeError("Camera availability check failed", error);
    }
    // ネイティブ API が無い古いビルドでは安全側に倒す
    return false;
  }

  async function ensureCameraAccess() {
    try {
      var cameraAvailable = await isNativeCameraHardwareAvailable();
      if (!cameraAvailable) {
        // 権限ダイアログ前にハード可否を判定し、未対応環境での起動クラッシュを防ぐ
        return { ok: false, reason: "unavailable" };
      }

      var status = await checkNativeCameraAuthorization();
      if (isCameraAuthorizationGranted(status)) {
        return { ok: true, reason: "authorized" };
      }

      if (status === "notDetermined" || status === "prompt" || status === "unknown") {
        status = await requestNativeCameraAuthorization();
        if (isCameraAuthorizationGranted(status)) {
          return { ok: true, reason: "authorized" };
        }
      }

      showCameraAlert(CAMERA_PERMISSION_REQUIRED_MESSAGE);
      return { ok: false, reason: "permission" };
    } catch (e) {
      logNativeError("Camera permission check failed", e);
      alert(JSON.stringify(e, null, 2));
      alertCameraDebugError(e, "ensureCameraAccess catch");
      return { ok: false, reason: "error" };
    }
  }

  /**
   * Prefer explicit data-image-source from dual-button UI.
   * Falls back to capture attribute, then legacy "prompt".
   */
  function resolveNativePhotoSource(input) {
    var attr = String(input.getAttribute("data-image-source") || "")
      .trim()
      .toLowerCase();
    if (attr === "camera" || attr === "environment") {
      return "camera";
    }
    if (attr === "photos" || attr === "library" || attr === "photo") {
      return "photos";
    }
    if (input.hasAttribute("capture")) {
      return "camera";
    }
    return "prompt";
  }

  async function attachNativeCameraPhoto(input) {
    if (input.disabled) {
      return true;
    }

    var preferred = resolveNativePhotoSource(input);
    var photoSource = preferred;
    var access = { ok: true, reason: "skip" };

    if (preferred === "photos") {
      var photosOnly = await ensurePhotosAccess();
      if (!photosOnly.ok) {
        return true;
      }
    } else if (preferred === "camera") {
      access = await ensureCameraAccess();
      if (!access.ok) {
        if (access.reason === "unavailable") {
          photoSource = "photos";
          var photosFallback = await ensurePhotosAccess();
          if (!photosFallback.ok) {
            return true;
          }
        } else {
          return true;
        }
      }
    } else {
      // Legacy single file input: prompt (camera or library)
      access = await ensureCameraAccess();
      photoSource = "prompt";

      if (!access.ok) {
        if (access.reason === "unavailable") {
          photoSource = "photos";
          var photosAccess = await ensurePhotosAccess();
          if (!photosAccess.ok) {
            return true;
          }
        } else {
          return true;
        }
      } else {
        try {
          await requestNativePhotosAuthorization();
        } catch (e) {
          logNativeError("Photos permission request failed", e);
          alert(JSON.stringify(e, null, 2));
          alertCameraDebugError(e, "requestNativePhotosAuthorization catch");
        }
      }
    }

    var Camera = getPlugin("Camera");
    if (!Camera || typeof Camera.getPhoto !== "function") {
      // 「最新版」メッセージは出さず、プラグイン未検出の技術情報を表示
      alert(
        JSON.stringify(
          {
            step: "getPhoto unavailable",
            hasCameraPlugin: !!Camera,
            hasGetPhoto: !!(Camera && Camera.getPhoto),
            pluginKeys: Camera ? Object.keys(Camera) : [],
            capacitorPlugins:
              window.Capacitor && window.Capacitor.Plugins
                ? Object.keys(window.Capacitor.Plugins)
                : [],
            hasCapacitor: !!window.Capacitor,
            hasGetPlugin: !!(window.Capacitor && window.Capacitor.getPlugin),
            platform:
              window.Capacitor && window.Capacitor.getPlatform
                ? window.Capacitor.getPlatform()
                : null,
            photoSource: photoSource,
            access: access,
          },
          null,
          2
        )
      );
      return true;
    }

    var stepMeta = {
      step: "before getPhoto",
      photoSource: photoSource,
      resultType: "dataUrl",
    };
    try {
      stepMeta.step = "Camera.getPhoto";
      // dataUrl なら fetch(webPath) が不要。iOS WKWebView の TypeError: Load failed を回避する。
      var photo = await Camera.getPhoto({
        quality: 85,
        resultType: "dataUrl",
        // ハード確認済みなら prompt。カメラ不可時は photos のみ（カメラ起動クラッシュ防止）。
        source: photoSource,
        saveToGallery: false,
        correctOrientation: true,
      });
      if (!photo || !(photo.dataUrl || photo.base64String || photo.webPath)) {
        alertCameraDebugError(
          new Error("getPhoto empty result"),
          "Camera.getPhoto empty",
          { photo: photo, photoSource: photoSource, step: stepMeta.step }
        );
        return true;
      }

      stepMeta.step = "photoResultToFile";
      stepMeta.hasDataUrl = !!photo.dataUrl;
      stepMeta.hasBase64 = !!photo.base64String;
      stepMeta.hasWebPath = !!photo.webPath;
      stepMeta.webPath = photo.webPath || null;
      var file = await photoResultToFile(photo, stepMeta);
      if (typeof DataTransfer === "undefined") {
        alertCameraDebugError(
          new Error("DataTransfer unavailable"),
          "Camera.assign file",
          stepMeta
        );
        return true;
      }
      stepMeta.step = "assign input.files";
      var dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      input.files = dataTransfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    } catch (e) {
      var message = String(
        (e && (e.message || e.localizedDescription)) || e || ""
      ).toLowerCase();
      if (message.indexOf("cancel") >= 0 || message.indexOf("user cancelled") >= 0) {
        return true;
      }
      logNativeError("Camera getPhoto failed", e);
      try {
        console.error("[WASE Camera] Camera.getPhoto/catch", e, stepMeta);
      } catch (_ignore) {}
      alertCameraDebugError(e, "Camera.getPhoto catch", {
        hint:
          e && e.message === "Load failed"
            ? "Likely fetch(webPath) failed in WKWebView; prefer dataUrl resultType"
            : null,
        photoSource: photoSource,
        access: access,
        stepMeta: stepMeta,
        name: e && e.name,
        message: e && e.message,
        stack: e && e.stack,
      });
      return true;
    }
  }

  function setupNativeCameraInputGuard() {
    if (!isNativeApp()) {
      return;
    }

    document.addEventListener(
      "click",
      function (event) {
        var input = event.target.closest('input[type="file"][accept*="image"]');
        if (!input || input.disabled) {
          return;
        }

        // ネイティブカメラ経路でクラッシュしないよう、まず既定の file picker を止める
        event.preventDefault();
        event.stopPropagation();

        attachNativeCameraPhoto(input).catch(function (e) {
          logNativeError("Camera guard failed", e);
          alert(JSON.stringify(e, null, 2));
          alertCameraDebugError(e, "setupNativeCameraInputGuard catch");
        });
      },
      true
    );
  }

  function logNative(label, detail) {
    if (window.console && console.info) {
      console.info("[WaseCapacitor] " + label, detail || "");
    }
  }

  function logNativeError(label, detail) {
    if (window.console && console.error) {
      console.error("[WaseCapacitor] " + label, detail || "");
    }
  }

  function getAnalyticsScreenName() {
    var path = window.location.pathname || "/";
    var search = window.location.search || "";
    return path + search;
  }

  async function trackPageView(reason) {
    if (!isNativeApp()) {
      return;
    }

    var Analytics = getPlugin("FirebaseAnalytics");
    if (!Analytics) {
      return;
    }

    var screenName = getAnalyticsScreenName();
    if (screenName === lastTrackedAnalyticsScreen) {
      return;
    }

    try {
      if (typeof Analytics.setCurrentScreen === "function") {
        await Analytics.setCurrentScreen({
          screenName: screenName,
          screenClassOverride: "WaseWebView",
        });
      }
      if (typeof Analytics.logEvent === "function") {
        await Analytics.logEvent({
          name: "screen_view",
          params: {
            firebase_screen: screenName,
            firebase_screen_class: "WaseWebView",
            page_reason: reason || "navigation",
          },
        });
      }
      lastTrackedAnalyticsScreen = screenName;
      logNative("Analytics page view", { screenName: screenName, reason: reason || "navigation" });
    } catch (error) {
      logNativeError("Analytics page view failed", error);
    }
  }

  function wait(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function getAdMobPlugin() {
    if (!window.Capacitor) {
      return null;
    }
    if (typeof window.Capacitor.getPlugin === "function") {
      var viaGet = window.Capacitor.getPlugin("AdMob");
      if (viaGet) {
        return viaGet;
      }
    }
    if (window.Capacitor.Plugins && window.Capacitor.Plugins.AdMob) {
      return window.Capacitor.Plugins.AdMob;
    }
    return null;
  }

  async function waitForAdMobPlugin(maxAttempts) {
    var attempts = maxAttempts || 50;
    for (var i = 0; i < attempts; i++) {
      var plugin = getAdMobPlugin();
      if (plugin) {
        logNative("AdMob plugin ready", { attempt: i + 1 });
        return plugin;
      }
      await wait(100);
    }
    return null;
  }

  function waitForDomLayout() {
    function afterFrames() {
      return new Promise(function (resolve) {
        requestAnimationFrame(function () {
          requestAnimationFrame(resolve);
        });
      });
    }
    if (document.readyState === "loading") {
      return new Promise(function (resolve) {
        document.addEventListener("DOMContentLoaded", resolve, { once: true });
      }).then(afterFrames);
    }
    return afterFrames();
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

  function getLocalDateKey() {
    var now = new Date();
    var y = now.getFullYear();
    var m = String(now.getMonth() + 1).padStart(2, "0");
    var d = String(now.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + d;
  }

  function canShowAppOpenAdToday() {
    try {
      return localStorage.getItem(APP_OPEN_STORAGE_KEY) !== getLocalDateKey();
    } catch (error) {
      return true;
    }
  }

  function markAppOpenAdShownToday() {
    try {
      localStorage.setItem(APP_OPEN_STORAGE_KEY, getLocalDateKey());
    } catch (error) {
      // ignore quota / private mode
    }
  }

  function cleanAdTriggerParams() {
    var params = new URLSearchParams(window.location.search);
    var changed = false;
    CREATION_AD_PARAMS.forEach(function (key) {
      if (params.has(key)) {
        params.delete(key);
        changed = true;
      }
    });
    // 旧トリガー（ログイン成功）も URL から掃除
    if (params.has("login_success")) {
      params.delete("login_success");
      changed = true;
    }
    if (!changed) {
      return;
    }
    var query = params.toString();
    var nextUrl =
      window.location.pathname + (query ? "?" + query : "") + window.location.hash;
    window.history.replaceState({}, "", nextUrl);
  }

  function dispatchPushReceivedEvent(notification) {
    window.dispatchEvent(
      new CustomEvent("wase:push-received", { detail: notification || null })
    );
    if (
      window.WaseNotifications &&
      typeof window.WaseNotifications.refresh === "function"
    ) {
      window.WaseNotifications.refresh();
    }
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
      dispatchPushReceivedEvent(notification);
    });

    await PushNotifications.addListener("pushNotificationActionPerformed", function (action) {
      logNative("Push action performed", action);
      dispatchPushReceivedEvent(action && action.notification);
    });

    var permission = await PushNotifications.requestPermissions();
    logNative("Push permission", permission);

    if (permission.receive === "granted") {
      await PushNotifications.register();
    }
  }

  async function initializeAdMob() {
    if (areAdsDisabled()) {
      logNative("AdMob skipped (DISABLE_ADS=true)");
      return false;
    }

    var AdMob = getAdMobPlugin();
    if (!AdMob) {
      logNativeError("AdMob plugin not found during initialize");
      return false;
    }

    var testing = !isProductionAds();
    try {
      await AdMob.initialize({
        initializeForTesting: testing,
      });
    } catch (error) {
      logNativeError("AdMob.initialize failed", error);
      return false;
    }

    logNative("AdMob initialized", { testing: testing });
    return true;
  }

  function setupBannerFailureListeners() {
    var AdMob = getAdMobPlugin();
    if (!AdMob || typeof AdMob.addListener !== "function" || bannerFailureListenersReady) {
      return;
    }
    bannerFailureListenersReady = true;

    AdMob.addListener("bannerAdFailedToLoad", function (error) {
      logNativeError("bannerAdFailedToLoad", error);
      hideBannerAd().catch(function (hideError) {
        logNativeError("Banner hide after load fail", hideError);
      });
    });

    AdMob.addListener("bannerAdLoaded", function () {
      logNative("bannerAdLoaded");
    });
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
    var AdMob = getAdMobPlugin();
    if (!AdMob || !bannerVisible) {
      return;
    }
    flashDiagMark("admob_remove_banner_start", null);
    if (typeof AdMob.removeBanner === "function") {
      try {
        await AdMob.removeBanner();
        flashDiagMark("admob_remove_banner", null);
        void flashDiagSnapshot("after_remove_banner");
      } catch (error) {
        logNative("removeBanner failed", error);
        flashDiagMark("admob_remove_banner_error", {
          message: String(error && error.message ? error.message : error),
        });
      }
    }
    bannerVisible = false;
    bannerMode = "none";
    lastBannerMargin = -1;
    setBannerLayoutClass("none");
  }

  async function renderBanner(options) {
    var AdMob = getAdMobPlugin();
    if (!AdMob) {
      return false;
    }

    flashDiagMark("admob_show_banner_start", {
      position: options && options.position,
      margin: options && options.margin,
    });

    if (bannerVisible) {
      await hideBannerAd();
    }

    try {
      await AdMob.showBanner(options);
      flashDiagMark("admob_show_banner", {
        position: options && options.position,
        margin: options && options.margin,
      });
      void flashDiagSnapshot("after_show_banner");
    } catch (error) {
      logNativeError("AdMob.showBanner failed", error);
      flashDiagMark("admob_show_banner_error", {
        message: String(error && error.message ? error.message : error),
      });
      throw error;
    }

    bannerVisible = true;
    logNative("Banner ad rendered", {
      position: options.position,
      margin: options.margin,
      testing: options.isTesting,
    });
    return true;
  }

  async function showBottomFallbackBanner() {
    // 下部固定バナーは廃止。インフィード枠が無い場合は広告を出さない。
    logNative("Bottom banner fallback disabled (in-feed only)");
    await hideBannerAd();
  }

  async function positionBannerAtAnchor(anchor) {
    if (!anchor) {
      logNative("No in-feed ad anchor; skip banner");
      await hideBannerAd();
      return;
    }

    var margin = computeBannerTopMargin(anchor, currentBannerHeight);
    var viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    if (margin > viewportHeight - 32) {
      logNative("Banner anchor off-screen; hide until visible", { margin: margin });
      await hideBannerAd();
      return;
    }

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
    try {
      await renderBanner({
        adId: ids.banner,
        adSize: "ADAPTIVE_BANNER",
        position: "TOP_CENTER",
        margin: margin,
        isTesting: testing,
      });
    } catch (error) {
      logNativeError("Inline banner render failed", error);
      await hideBannerAd();
      return;
    }
    bannerMode = "inline";
    lastBannerMargin = margin;
    setBannerLayoutClass("none");
  }

  async function repositionInlineBanner() {
    if (bannerRepositionInFlight) {
      flashDiagMark("reposition_inline_banner_skipped", { reason: "in_flight" });
      return;
    }
    bannerRepositionInFlight = true;
    flashDiagMark("reposition_inline_banner", {
      bannerVisible: bannerVisible,
      bannerMode: bannerMode,
    });
    void flashDiagSnapshot("reposition_inline_banner_start");
    try {
      var anchor = findBestAdAnchor();
      if (!anchor) {
        flashDiagMark("reposition_inline_banner_no_anchor", null);
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
      flashDiagMark("reposition_inline_banner_done", null);
      void flashDiagSnapshot("reposition_inline_banner_done");
    } catch (error) {
      logNative("Banner reposition failed", error);
      flashDiagMark("reposition_inline_banner_error", {
        message: String(error && error.message ? error.message : error),
      });
    } finally {
      bannerRepositionInFlight = false;
    }
  }

  function scheduleBannerReposition(delayMs) {
    var diag = readSpaNavDiag();
    var waitMs =
      typeof delayMs === "number" ? delayMs : BANNER_REPOSITION_DEBOUNCE_MS;
    flashDiagMark("schedule_banner_reposition_attempt", {
      delayMs: waitMs,
      bannerTrackingReady: bannerTrackingReady,
      disableBannerReposition: Boolean(diag.disableBannerReposition),
    });
    if (!bannerTrackingReady) {
      flashDiagMark("schedule_banner_reposition_skipped", {
        reason: "not_ready",
      });
      return;
    }
    if (diag.disableBannerReposition) {
      flashDiagMark("schedule_banner_reposition_skipped", {
        reason: "diag_no_banner",
      });
      return;
    }
    if (bannerRepositionTimer) {
      clearTimeout(bannerRepositionTimer);
    }
    flashDiagMark("schedule_banner_reposition", { delayMs: waitMs });
    bannerRepositionTimer = setTimeout(function () {
      flashDiagMark("schedule_banner_reposition_fire", { delayMs: waitMs });
      repositionInlineBanner().catch(function (error) {
        logNative("Deferred banner reposition failed", error);
      });
    }, waitMs);
  }

  /**
   * React SPA のクライアント遷移用。
   * 通常時は Analytics + AdMob creation trigger + banner reposition（従来どおり）。
   *
   * 切り分け（通常挙動は変えない）:
   *   ?spa_nav_diag=off          → notifySpaNavigation 全体オフ
   *   ?spa_nav_diag=no_banner    → banner reposition のみオフ
   *   ?spa_nav_diag=no_ads       → creation AdMob trigger のみオフ
   *   ?spa_nav_diag=no_analytics → Analytics のみオフ
   */
  function notifySpaNavigation(reason) {
    var diag = readSpaNavDiag();
    flashDiagMark("notify_spa_navigation", {
      reason: reason || "spa-nav",
      path: window.location.pathname,
      diag: diag,
    });
    logNative("SPA navigation", {
      reason: reason || "spa-nav",
      path: window.location.pathname,
      diag: diag,
    });

    if (diag.disableAll) {
      flashDiagMark("notify_spa_navigation_skipped", { reason: "diag_off" });
      return;
    }

    if (!diag.disableAnalytics) {
      flashDiagMark("analytics_track_page_view", {
        reason: reason || "spa-nav",
      });
      trackPageView(reason || "spa-nav").catch(function (error) {
        logNativeError("Analytics spa-nav failed", error);
      });
    } else {
      flashDiagMark("analytics_track_page_view_skipped", {
        reason: "diag_no_analytics",
      });
    }

    if (!diag.disableAds) {
      flashDiagMark("handle_page_triggers", null);
      try {
        handlePageTriggers();
      } catch (error) {
        logNativeError("SPA page triggers failed", error);
      }
    } else {
      flashDiagMark("handle_page_triggers_skipped", { reason: "diag_no_ads" });
    }

    if (!diag.disableBannerReposition && bannerTrackingReady) {
      try {
        scheduleBannerReposition();
      } catch (error) {
        logNative("SPA banner reposition failed", error);
      }
    } else if (diag.disableBannerReposition) {
      flashDiagMark("schedule_banner_reposition_skipped", {
        reason: "diag_no_banner_from_notify",
      });
    } else {
      flashDiagMark("schedule_banner_reposition_skipped", {
        reason: "banner_tracking_not_ready",
      });
    }
    void flashDiagSnapshot("after_notify_spa_navigation");
  }

  function setupInlineBannerTracking() {
    if (bannerTrackingReady) {
      return;
    }
    bannerTrackingReady = true;

    window.addEventListener("scroll", scheduleBannerReposition, { passive: true });
    window.addEventListener("resize", scheduleBannerReposition);
    window.addEventListener("orientationchange", scheduleBannerReposition);

    var AdMob = getAdMobPlugin();
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
    if (areAdsDisabled()) {
      logNative("showBannerAd skipped (DISABLE_ADS=true)");
      return;
    }
    if (!getAdMobPlugin()) {
      logNativeError("showBannerAd skipped: plugin missing");
      return;
    }

    setupInlineBannerTracking();
    var anchor = findBestAdAnchor();
    logNative("showBannerAd", {
      anchorFound: Boolean(anchor),
      anchorType: anchor ? anchor.getAttribute("data-wase-admob-anchor") : null,
    });
    if (anchor) {
      await positionBannerAtAnchor(anchor);
      return;
    }

    // インフィード枠が無い（DISABLE_ADS / Web 等）ときは下部バナーも出さない
    await hideBannerAd();
  }

  async function prepareInterstitialAd() {
    if (areAdsDisabled()) {
      return false;
    }
    var AdMob = getAdMobPlugin();
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
    if (areAdsDisabled()) {
      logNative("Interstitial skipped (DISABLE_ADS=true)", reason || "");
      return false;
    }
    if (!canShowInterstitialNow()) {
      logNative("Interstitial skipped (cooldown)", reason || "");
      return false;
    }

    var AdMob = getAdMobPlugin();
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
      logNativeError("Interstitial failed", error);
      return false;
    }
  }

  async function showAppOpenAd() {
    if (areAdsDisabled()) {
      logNative("App open ad skipped (DISABLE_ADS=true)");
      return;
    }
    if (appOpenHandled) {
      return;
    }
    appOpenHandled = true;

    if (!canShowAppOpenAdToday()) {
      logNative("App open ad skipped (already shown today)");
      return;
    }

    var AdMob = getAdMobPlugin();
    if (!AdMob) {
      logNativeError("showAppOpenAd skipped: plugin missing");
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
          markAppOpenAdShownToday();
          logNative("App open ad shown", { testing: testing });
          return;
        }
        logNative("App open ad not loaded in time; trying interstitial fallback");
      } else {
        logNative("App Open API unavailable; using interstitial fallback");
      }

      await AdMob.prepareInterstitial({
        adId: ids.interstitial,
        isTesting: testing,
      });
      await AdMob.showInterstitial();
      interstitialPrepared = false;
      markInterstitialShown();
      markAppOpenAdShownToday();
      logNative("Launch interstitial fallback shown", { testing: testing });
    } catch (error) {
      logNativeError("App open ad failed", error);
    }
  }

  /**
   * 生成完了時のみインタースティシャルを表示する。
   * タブ切替・通常ナビ・ログイン成功では表示しない。
   */
  function handlePageTriggers() {
    if (areAdsDisabled()) {
      cleanAdTriggerParams();
      return;
    }

    var params = new URLSearchParams(window.location.search);
    var triggers = [];

    CREATION_AD_PARAMS.forEach(function (key) {
      if (params.get(key) === "1") {
        triggers.push(key);
      }
    });

    if (triggers.length === 0) {
      cleanAdTriggerParams();
      return;
    }

    showInterstitialAd("creation:" + triggers.join(","))
      .catch(function (error) {
        logNative("Creation interstitial failed", error);
      })
      .finally(function () {
        cleanAdTriggerParams();
      });
  }

  async function runAdMobBootstrap() {
    if (areAdsDisabled()) {
      logNative("AdMob bootstrap skipped (DISABLE_ADS=true)");
      return;
    }

    var adsReady = await initializeAdMob();
    if (!adsReady) {
      return;
    }

    setupBannerFailureListeners();

    try {
      await showAppOpenAd();
    } catch (error) {
      logNativeError("App open bootstrap failed", error);
    }

    await waitForDomLayout();

    try {
      await showBannerAd();
    } catch (error) {
      logNativeError("Banner bootstrap failed", error);
      try {
        await hideBannerAd();
      } catch (hideError) {
        logNativeError("Banner hide after fail", hideError);
      }
    }

    prepareInterstitialAd().catch(function (error) {
      logNativeError("Initial interstitial preload failed", error);
    });
  }

  async function bootstrap() {
    if (!isNativeApp()) {
      return;
    }

    document.documentElement.classList.add("is-native-capacitor");
    try {
      document.cookie = "wase_is_app=1; path=/; Max-Age=31536000; SameSite=Lax";
    } catch (cookieError) {
      // ignore
    }
    ensureSafeAreaTopCssVar();
    bindSafeAreaTopListeners();
    setupNativeCameraInputGuard();
    logNative("bootstrap start", {
      href: window.location.href,
      hasAdMobConfig: Boolean(window.WASE_ADMOB_CONFIG),
    });

    try {
      await trackPageView("bootstrap");

      var adMobPlugin = await waitForAdMobPlugin(50);
      if (!adMobPlugin) {
        logNativeError("AdMob plugin not available", {
          hasCapacitor: Boolean(window.Capacitor),
          pluginKeys:
            window.Capacitor && window.Capacitor.Plugins
              ? Object.keys(window.Capacitor.Plugins)
              : [],
        });
      } else {
        await runAdMobBootstrap();
      }

      await initializePushNotifications();

      if (window.WASE_PUSH_TOKEN) {
        await registerTokenWithBackend(window.WASE_PUSH_TOKEN);
      }

      handlePageTriggers();
    } catch (error) {
      logNativeError("bootstrap failed", error);
    } finally {
      // スプラッシュは splash_screen.js が自動 / タップで制御する
    }
  }

  window.WaseCapacitor = {
    isNativeApp: isNativeApp,
    areAdsDisabled: areAdsDisabled,
    isProductionAds: isProductionAds,
    getActiveAdIds: getActiveAdIds,
    trackPageView: trackPageView,
    handlePageTriggers: handlePageTriggers,
    /**
     * React Router クライアント遷移時に Analytics / 広告トリガーを再評価する。
     * タブ切替時の AdMob banner 再配置は notifySpaNavigation 内で抑制・遅延。
     */
    notifySpaNavigation: notifySpaNavigation,
    /** TestFlight 切り分け: 現在の diag フラグを返す */
    getSpaNavDiag: readSpaNavDiag,
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

  window.addEventListener("pageshow", function () {
    if (!isNativeApp()) {
      return;
    }
    trackPageView("pageshow").catch(function (error) {
      logNativeError("Analytics pageshow failed", error);
    });
    if (bannerTrackingReady) {
      scheduleBannerReposition();
      return;
    }
    if (getAdMobPlugin()) {
      showBannerAd().catch(function (error) {
        logNative("pageshow banner refresh failed", error);
      });
    }
  });

  startWhenReady();
})(window);
