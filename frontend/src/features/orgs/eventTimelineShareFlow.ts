export type TimelineShareUiState = {
  composerOpen: boolean;
  submitting: boolean;
  body: string;
  error: string | null;
};

export type TimelineShareUiAction =
  | { type: "tap_open" }
  | { type: "edit"; body: string }
  | { type: "tap_submit" }
  | { type: "success" }
  | { type: "failure"; message: string }
  | { type: "close" };

export function initialTimelineShareUi(): TimelineShareUiState {
  return {
    composerOpen: false,
    submitting: false,
    body: "",
    error: null,
  };
}

export function reduceTimelineShareUi(
  state: TimelineShareUiState,
  action: TimelineShareUiAction
): TimelineShareUiState {
  switch (action.type) {
    case "tap_open":
      if (state.submitting) return state;
      return {
        ...state,
        composerOpen: true,
        error: null,
      };
    case "edit":
      if (!state.composerOpen || state.submitting) return state;
      return { ...state, body: action.body };
    case "tap_submit":
      if (!state.composerOpen || state.submitting) return state;
      return { ...state, submitting: true, error: null };
    case "success":
      return initialTimelineShareUi();
    case "failure":
      return {
        ...state,
        submitting: false,
        composerOpen: true,
        error: action.message,
      };
    case "close":
      if (state.submitting) return state;
      return { ...state, composerOpen: false, error: null };
  }
}

export function timelineShareTapSendsRequest(
  action: TimelineShareUiAction
): boolean {
  return action.type === "tap_submit";
}
