/**
 * AdMob 広告ユニット設定。
 *
 * 【審査・緊急停止用】
 * DISABLE_ADS を true にすると広告を完全停止します。
 * 本番 HTML では Django の WASE_DISABLE_ADS がこの値を上書き同期します。
 * （テンプレート側も DOM を一切レンダリングしません）
 *
 * テスト時は useProductionAds: false（Google 公式テスト ID）。
 * ストア申請・本番リリース前に true に切り替えてください。
 */
(function (window) {
  "use strict";

  window.WASE_ADMOB_CONFIG = {
    // ★ App Store 審査提出時は true（または Django の WASE_DISABLE_ADS=True）
    DISABLE_ADS: false,

    // Django 側 IS_APP と同期（インフィード出し分けの参考値）
    IS_APP: false,

    useProductionAds: false,
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
})(window);
