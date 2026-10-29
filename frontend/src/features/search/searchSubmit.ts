import { stripHomeTimelineLeftoverParams } from "../timeline/homeFeed.ts";

export type GlobalSearchTab =
  | "all"
  | "latest"
  | "courses"
  | "users"
  | "products";

export const SEARCH_NO_RESULTS_MESSAGE = "検索結果がありません";
export const SEARCH_FAILED_MESSAGE =
  "検索に失敗しました。通信環境を確認して、もう一度お試しください。";
export const SEARCH_DISCOVER_FAILED_MESSAGE =
  "話題の読み込みに失敗しました。通信環境を確認して、もう一度お試しください。";

export function buildSearchSubmitParams(
  qInput: string,
  activeTab: GlobalSearchTab
): URLSearchParams {
  const next = new URLSearchParams();
  const q = (qInput || "").trim();
  if (q) next.set("q", q);
  next.set("tab", activeTab === "all" ? "all" : activeTab);
  return next;
}

export function searchFetchQuery(
  qParam: string,
  activeTab: GlobalSearchTab
): { q?: string; tab?: GlobalSearchTab } {
  const q = (qParam || "").trim();
  return {
    q: q || undefined,
    tab: q ? activeTab : undefined,
  };
}

export function globalSearchEmptyMessage(hasQuery: boolean): string {
  if (!hasQuery) {
    return "キーワードを入力すると、わせわせ全体を横断検索できます。";
  }
  return SEARCH_NO_RESULTS_MESSAGE;
}

export function globalSearchErrorMessage(
  error: unknown,
  hasQuery = true
): string {
  const raw = error instanceof Error ? error.message : String(error || "");
  if (raw && /[ぁ-んァ-ン一-龥]/.test(raw) && !/search_failed/.test(raw)) {
    return raw;
  }
  return hasQuery ? SEARCH_FAILED_MESSAGE : SEARCH_DISCOVER_FAILED_MESSAGE;
}

/** Same handler for the on-screen 検索 button and the iPhone keyboard 検索 key. */
export function submitSearchForm(input: {
  pathname: string;
  qInput: string;
  activeTab: GlobalSearchTab;
}): {
  params: URLSearchParams;
  q: string;
  tab: GlobalSearchTab;
  fetch: { q?: string; tab?: GlobalSearchTab };
} {
  const submitted = buildSearchSubmitParams(input.qInput, input.activeTab);
  const visible =
    stripHomeTimelineLeftoverParams(input.pathname, submitted) ?? submitted;
  const q = visible.get("q") || "";
  const tab = (visible.get("tab") as GlobalSearchTab) || input.activeTab;
  return {
    params: visible,
    q,
    tab,
    fetch: searchFetchQuery(q, tab),
  };
}

export type SearchSubmitView = {
  qInput: string;
  qParam: string;
  tab: GlobalSearchTab;
  loading: boolean;
  error: string | null;
  results: string[];
  fetches: Array<{ id: number; q?: string; tab?: GlobalSearchTab }>;
};

/**
 * Component-level harness: typing, tapping 検索, and keyboard submit share
 * one path. Keep-alive HomePage may try to rewrite the URL after submit.
 */
export function createSearchTabHarness() {
  let pathname = "/search";
  let qInput = "";
  let tab: GlobalSearchTab = "all";
  let qParam = "";
  let loading = false;
  let error: string | null = null;
  let results: string[] = [];
  let requestId = 0;
  const fetches: SearchSubmitView["fetches"] = [];

  const snapshot = (): SearchSubmitView => ({
    qInput,
    qParam,
    tab,
    loading,
    error,
    results: [...results],
    fetches: [...fetches],
  });

  const submit = () => {
    const next = submitSearchForm({ pathname, qInput, activeTab: tab });
    qParam = next.q;
    tab = next.tab;
    requestId += 1;
    const id = requestId;
    loading = true;
    error = null;
    fetches.push({ id, ...next.fetch });
    return id;
  };

  const commit = (
    id: number,
    outcome:
      | { ok: true; results: string[] }
      | { ok: false; error?: unknown }
  ) => {
    if (id !== requestId) return snapshot();
    loading = false;
    if (outcome.ok) {
      results = outcome.results;
      error = null;
    } else {
      error = globalSearchErrorMessage(outcome.error, Boolean(qParam.trim()));
    }
    return snapshot();
  };

  return {
    snapshot,
    type(value: string) {
      qInput = value;
      return snapshot();
    },
    setTab(next: GlobalSearchTab) {
      tab = next;
      return snapshot();
    },
    /** On-screen 検索 button (type=submit → form onSubmit). */
    clickSearchButton() {
      return submit();
    },
    /** iPhone keyboard 検索 / Enter on type=search input. */
    submitWithKeyboard() {
      return submit();
    },
    async finish(
      id: number,
      outcome:
        | { ok: true; results: string[] }
        | { ok: false; error?: unknown }
    ) {
      return commit(id, outcome);
    },
  };
}
