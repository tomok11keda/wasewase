export type TimelineFeedPhase =
  | "skeleton"
  | "browse"
  | "unavailable"
  | "error"
  | "empty"
  | "ready";

export type TimelineFeedPhaseInput = {
  browsePreview: boolean;
  sessionLoading: boolean;
  feedLoading: boolean;
  waitingForTarget: boolean;
  postUnavailable: boolean;
  error: string | null;
  postCount: number;
};

/** Enough cards to clip at the bottom nav on iPhone-sized viewports. */
export const TIMELINE_FEED_SKELETON_COUNT = 10;

/**
 * First-paint feed state. Existing posts always win so soft refetch / keep-alive
 * never blank the timeline. Browse preview wins over skeleton so guests do not
 * see a logged-in feed placeholder.
 */
export function timelineFeedPhase(
  input: TimelineFeedPhaseInput
): TimelineFeedPhase {
  if (input.browsePreview) return "browse";
  if (input.postCount > 0) return "ready";
  if (
    !input.postUnavailable &&
    (input.sessionLoading || input.feedLoading || input.waitingForTarget)
  ) {
    return "skeleton";
  }
  if (input.postUnavailable) return "unavailable";
  if (input.error) return "error";
  return "empty";
}
