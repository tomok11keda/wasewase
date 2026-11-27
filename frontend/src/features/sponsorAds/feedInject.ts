import type { HomeSponsorAdsPayload, SponsorAd } from "./types";

export type HomeFeedRow =
  | { kind: "post"; postId: number; index: number }
  | { kind: "sponsor"; ad: SponsorAd };

/**
 * Build home feed rows: insert the first sponsor card after N posts.
 * Only used when sponsor.enabled && items.length > 0.
 */
export function buildHomeFeedRows(
  postIds: number[],
  sponsor: HomeSponsorAdsPayload | null | undefined
): HomeFeedRow[] {
  const rows: HomeFeedRow[] = [];
  const ad =
    sponsor?.enabled && sponsor.items.length > 0 ? sponsor.items[0] : null;
  const insertAfter =
    ad && Number.isFinite(sponsor?.insert_after)
      ? Math.max(0, Number(sponsor!.insert_after))
      : -1;

  postIds.forEach((postId, index) => {
    rows.push({ kind: "post", postId, index });
    if (ad && index + 1 === insertAfter) {
      rows.push({ kind: "sponsor", ad });
    }
  });

  // Fewer than insertAfter posts: show after the last available post.
  if (
    ad &&
    postIds.length > 0 &&
    postIds.length < insertAfter &&
    !rows.some((r) => r.kind === "sponsor")
  ) {
    rows.push({ kind: "sponsor", ad });
  }

  return rows;
}
