export type SponsorAdKind = "internal_promotion" | "sponsored";

export type SponsorAdPlacement =
  | "home_feed"
  | "discover_featured"
  | "flea_banner"
  | "courses_feed"
  | "timetable";

export type SponsorAd = {
  id: number;
  kind: SponsorAdKind | string;
  badge_label: string;
  sponsor_name: string;
  title: string;
  description: string;
  image_url: string | null;
  cta_url: string;
  cta_label: string;
  placement: SponsorAdPlacement | string;
};

export type HomeSponsorAdsPayload = {
  enabled: boolean;
  insert_after: number;
  items: SponsorAd[];
};

export function parseSponsorAd(raw: unknown): SponsorAd | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  const cta = String(row.cta_url || "").trim();
  if (!cta.startsWith("https://")) return null;
  return {
    id,
    kind: String(row.kind || "sponsored"),
    badge_label: String(row.badge_label || "スポンサー"),
    sponsor_name: String(row.sponsor_name || ""),
    title: String(row.title || ""),
    description: String(row.description || ""),
    image_url:
      typeof row.image_url === "string" && row.image_url
        ? row.image_url
        : null,
    cta_url: cta,
    cta_label: String(row.cta_label || "詳しく見る"),
    placement: String(row.placement || ""),
  };
}

export function parseHomeSponsorAds(raw: unknown): HomeSponsorAdsPayload {
  const empty: HomeSponsorAdsPayload = {
    enabled: false,
    insert_after: 2,
    items: [],
  };
  if (!raw || typeof raw !== "object") return empty;
  const row = raw as Record<string, unknown>;
  const items = Array.isArray(row.items)
    ? row.items
        .map(parseSponsorAd)
        .filter((ad): ad is SponsorAd => ad != null)
    : [];
  const insertAfter = Number(row.insert_after);
  return {
    enabled: Boolean(row.enabled) && items.length > 0,
    insert_after: Number.isFinite(insertAfter) ? insertAfter : 2,
    items,
  };
}

export function parseDiscoverSponsorAds(raw: unknown): SponsorAd[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map(parseSponsorAd)
    .filter((ad): ad is SponsorAd => ad != null);
}
