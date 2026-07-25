/**
 * AdMob 広告ユニット設定。
 *
 * 【審査・緊急停止用】
 * DISABLE_ADS を true にすると、バナー / インタースティシャル / 起動時広告を
 * 一切表示しません（ネイティブ Capacitor 側の広告ロジックがすべて no-op）。
 *
 * テスト時は useProductionAds: false（Google 公式テスト ID）。
 * ストア申請・本番リリース前に true に切り替えてください。
 */
(function (window) {
  "use strict";

  window.WASE_ADMOB_CONFIG = {
    // ★ App Store 審査提出時は true にして広告を完全停止できます
    DISABLE_ADS: false,

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
