import assert from "node:assert/strict";
import test from "node:test";
import { buildHomeFeedRows } from "./feedInject.ts";
import { parseDiscoverSponsorAds, parseHomeSponsorAds } from "./types.ts";

const sampleAd = {
  id: 9,
  kind: "sponsored",
  badge_label: "スポンサー",
  sponsor_name: "架空カフェ合同会社",
  title: "キャンパス近くの勉強カフェ",
  description: "テスト用の架空広告です",
  image_url: null,
  cta_url: "https://example.com/fictional-cafe",
  cta_label: "詳しく見る",
  placement: "home_feed",
};

test("home feed inserts sponsor after two posts", () => {
  const rows = buildHomeFeedRows([1, 2, 3, 4], {
    enabled: true,
    insert_after: 2,
    items: [sampleAd],
  });
  assert.deepEqual(
    rows.map((r) => (r.kind === "post" ? `p${r.postId}` : "ad")),
    ["p1", "p2", "ad", "p3", "p4"]
  );
});

test("disabled or empty sponsor leaves posts alone", () => {
  assert.equal(
    buildHomeFeedRows([1, 2], { enabled: false, insert_after: 2, items: [sampleAd] })
      .length,
    2
  );
  assert.equal(
    buildHomeFeedRows([1, 2], { enabled: true, insert_after: 2, items: [] }).length,
    2
  );
});

test("http CTA is rejected by parser", () => {
  const parsed = parseHomeSponsorAds({
    enabled: true,
    insert_after: 2,
    items: [{ ...sampleAd, cta_url: "http://insecure.example/" }],
  });
  assert.equal(parsed.enabled, false);
  assert.equal(parsed.items.length, 0);
});

test("discover list parser keeps https ads only", () => {
  const ads = parseDiscoverSponsorAds([
    sampleAd,
    { ...sampleAd, id: 10, cta_url: "http://bad.example/" },
  ]);
  assert.equal(ads.length, 1);
  assert.equal(ads[0].id, 9);
});
