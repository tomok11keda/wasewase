/**
 * AdMob 広告ユニット設定。
 *
 * 【リリース初期・緊急停止用】
 * DISABLE_ADS を true にすると広告を完全停止します（リクエストも枠 DOM も出ません）。
 * 本番 HTML では Django の WASE_DISABLE_ADS がこの値を上書き同期します。
 *
 * 再開するとき:
 *   1) ここを false（または環境変数 WASE_DISABLE_ADS=False）
 *   2) ストア本番前に useProductionAds: true
 */
(function (window) {
  "use strict";

  window.WASE_ADMOB_CONFIG = {
    // ★ リリース初期は true（広告完全停止）。再開時は false に戻す。
    DISABLE_ADS: true,

    // Django 側 IS_APP と同期（インフィード出し分けの参考値）
    IS_APP: false,

    // 再開時も当面は false（Google 公式テスト ID）。本番課金前に true。
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
