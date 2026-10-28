const listeners = new Set<() => void>();

export function invalidateTimelineFeed(): void {
  for (const listener of listeners) listener();
}

export function subscribeTimelineFeedInvalidation(
  listener: () => void
): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
