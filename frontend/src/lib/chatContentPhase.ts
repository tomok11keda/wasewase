export type ChatContentPhase =
  | "skeleton"
  | "ready"
  | "empty"
  | "error"
  | "gated";

export type ChatContentPhaseInput = {
  loading: boolean;
  error: string | null;
  hasRoom: boolean;
  hydrated: boolean;
  messageCount: number;
  /** Join / pending / no send permission — never show the thread. */
  gated?: boolean;
};

/**
 * Chat first paint: unknown access stays on a skeleton.
 * A hydrated room keeps its thread during polling (loading may still be true
 * only on the initial fetch). 403/404 must clear the room before this runs.
 */
export function chatContentPhase(
  input: ChatContentPhaseInput
): ChatContentPhase {
  if (input.gated && input.hydrated) return "gated";
  if (input.hasRoom && input.hydrated) {
    return input.messageCount > 0 ? "ready" : "empty";
  }
  if (input.error && !input.loading) return "error";
  if (input.loading || !input.hydrated) return "skeleton";
  return "error";
}

export function chatRoomMatches(
  room: { id: number } | null | undefined,
  roomId: number
): boolean {
  return room != null && room.id === roomId;
}
