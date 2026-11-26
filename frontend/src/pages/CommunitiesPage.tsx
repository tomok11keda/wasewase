import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { isBrowsePreview, useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { ThreadListSkeleton } from "../components/skeleton";
import { listContentPhase, listQueryKey } from "../lib/listContentPhase";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";
import {
  createCommunityThread,
  fetchCommunityThreads,
  participantLabel,
  type ThreadSummary,
} from "../features/community/api";
import { CommunityReportMenu } from "../features/community/CommunityReportMenu";
import {
  OfficialBadge,
  officialBoardClass,
} from "../features/community/OfficialBadge";
import { communityThreadDetailState } from "../features/community/threadNav";
import { analytics } from "../lib/analytics/events";
import { PullToRefresh } from "../lib/usePullToRefresh";

/**
 * Anonymous community boards (not a bottom-nav tab).
 * Entry from 見つける Discover. Course discovery moved to /courses tab.
 * Legacy ?hub=courses redirects to /courses.
 */
export function CommunitiesPage() {
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const tag = searchParams.get("tag") || "";
  const qParam = searchParams.get("q") || "";
  const sort = (
    searchParams.get("sort") === "latest" ? "latest" : "recommended"
  ) as "recommended" | "latest";
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [composeOpen, setComposeOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const hasDataRef = useRef(false);
  const requestIdRef = useRef(0);
  const appliedKeyRef = useRef("");
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const prevUserIdRef = useRef(sessionUserId);
  const listKey = listQueryKey([
    sessionUserId ?? "guest",
    tag,
    qParam,
    sort,
  ]);
  const composeFormRef = useRef<HTMLFormElement | null>(null);

  // Legacy hub=courses → dedicated 授業 tab (keep URL compatibility).
  useEffect(() => {
    if (searchParams.get("hub") !== "courses") return;
    const next = new URLSearchParams(searchParams);
    next.delete("hub");
    const qs = next.toString();
    navigate(`/courses${qs ? `?${qs}` : ""}`, { replace: true });
  }, [navigate, searchParams]);

  const patchParams = useCallback(
    (patch: Record<string, string>) => {
      const next = new URLSearchParams(searchParams);
      Object.entries(patch).forEach(([key, value]) => {
        if (value) next.set(key, value);
        else next.delete(key);
      });
      setSearchParams(next);
    },
    [searchParams, setSearchParams]
  );

  const load = useCallback(
    async (mode: "initial" | "soft" = "initial") => {
      const requestId = nextRequestId(requestIdRef);
      const startedUserId = userIdRef.current;
      const startedKey = listKey;
      if (browsePreview) {
        setThreads([]);
        setError(null);
        setLoading(false);
        hasDataRef.current = false;
        appliedKeyRef.current = startedKey;
        return;
      }
      const sameQuery =
        appliedKeyRef.current === startedKey && hasDataRef.current;
      if (mode === "initial" && !sameQuery) {
        setLoading(true);
      }
      if (mode !== "soft") setError(null);
      try {
        const data = await fetchCommunityThreads({
          tag: tag || undefined,
          q: qParam || undefined,
          sort,
        });
        if (!isLatestRequest(requestIdRef, requestId)) return false;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return false;
        setThreads(data.threads);
        hasDataRef.current = true;
        appliedKeyRef.current = startedKey;
        setError(null);
        return true;
      } catch (err) {
        if (!isLatestRequest(requestIdRef, requestId)) return false;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return false;
        if (mode === "soft") return false;
        setError(err instanceof Error ? err.message : "load_failed");
        return false;
      } finally {
        if (isLatestRequest(requestIdRef, requestId)) {
          setLoading(false);
        }
      }
    },
    [tag, qParam, sort, browsePreview, listKey]
  );

  useEffect(() => {
    if (prevUserIdRef.current === sessionUserId) return;
    prevUserIdRef.current = sessionUserId;
    nextRequestId(requestIdRef);
    hasDataRef.current = false;
    appliedKeyRef.current = "";
    setThreads([]);
    setError(null);
  }, [sessionUserId]);

  useEffect(() => {
    if (sessionLoading) return;
    if (searchParams.get("hub") === "courses") return;
    const soft = hasDataRef.current && appliedKeyRef.current === listKey;
    void load(soft ? "soft" : "initial");
  }, [sessionLoading, load, listKey, searchParams]);

  useEffect(() => {
    analytics.communityViewed();
  }, []);

  const normalizedPath = location.pathname.replace(/\/$/, "") || "/";
  const onCommunityList = normalizedPath === "/communities";
  const showComposeFab = !composeOpen && onCommunityList;
  const communityPhase = listContentPhase({
    browsePreview,
    loading: sessionLoading || loading,
    error,
    itemCount: threads.length,
    matchesCurrentQuery: appliedKeyRef.current === listKey,
  });

  const openCompose = () => {
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/communities"));
      return;
    }
    setComposeOpen(true);
  };

  useEffect(() => {
    if (!composeOpen) return;
    composeFormRef.current?.scrollIntoView({ block: "start" });
  }, [composeOpen]);

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/communities"));
      return;
    }
    setBusy(true);
    try {
      const thread = await createCommunityThread({
        title: title.trim(),
        body: body.trim(),
        tag: tag || undefined,
      });
      analytics.communityPostCreated();
      setThreads((prev) => [thread, ...prev]);
      setTitle("");
      setBody("");
      setComposeOpen(false);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "作成に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  if (searchParams.get("hub") === "courses") {
    return (
      <div className="communities-page" data-spa-page="コミュニティ">
        <p className="empty-message">授業タブへ移動しています…</p>
      </div>
    );
  }

  return (
    <div
      className={`communities-page ptr-shift${composeOpen ? " is-composing" : ""}`}
      data-spa-page="コミュニティ"
    >
      <PullToRefresh
        enabled={onCommunityList && !composeOpen && !browsePreview}
        onRefresh={async () => {
          const ok = await load("soft");
          if (!ok) throw new Error("refresh_failed");
        }}
      />
      <div className="communities-header">
        <div className="communities-header-top">
          <h2>コミュニティ</h2>
          {me?.authenticated ? (
            <button
              type="button"
              className="btn-new-thread btn-new-thread--desktop"
              aria-expanded={composeOpen}
              onClick={() => setComposeOpen((v) => !v)}
            >
              ＋ 新規スレッド
            </button>
          ) : (
            <Link
              className="btn-new-thread btn-new-thread--desktop"
              to={spaLoginPath("/app/communities")}
            >
              ＋ 新規スレッド
            </Link>
          )}
        </div>
        <p className="community-anon-hint community-anon-hint--compact">
          匿名ボードです。学生団体の公式ページとは別の場所です。
        </p>
        <p className="communities-hub-hint">
          <Link to="/search">見つける</Link>
          から戻る · 授業の発見は
          <Link to="/courses">授業タブ</Link>
        </p>

        <div
          className="community-sort-tabs"
          role="group"
          aria-label="コミュニティ並び順"
        >
          <button
            type="button"
            className={`community-sort-tab${sort === "recommended" ? " is-active" : ""}`}
            aria-pressed={sort === "recommended"}
            onClick={() => patchParams({ sort: "" })}
          >
            おすすめ
          </button>
          <button
            type="button"
            className={`community-sort-tab${sort === "latest" ? " is-active" : ""}`}
            aria-pressed={sort === "latest"}
            onClick={() => patchParams({ sort: "latest" })}
          >
            最新
          </button>
        </div>
      </div>

      {composeOpen ? (
        <form
          ref={composeFormRef}
          className="community-compose"
          onSubmit={onCreate}
        >
          <p className="community-anon-hint community-compose__anon">
            匿名で投稿されます
          </p>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={120}
            placeholder="スレッドタイトル"
            required
          />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={2000}
            rows={5}
            placeholder="相談内容や共有したいことを書いてください"
            required
          />
          <div className="community-compose__actions">
            <button
              type="button"
              className="community-compose__cancel"
              onClick={() => setComposeOpen(false)}
            >
              キャンセル
            </button>
            <button type="submit" disabled={busy}>
              作成する
            </button>
          </div>
        </form>
      ) : null}

      {communityPhase === "browse" ? (
        <BrowsePreviewNotice nextPath="/app/communities">
          コミュニティの投稿はログイン後に表示されます。
        </BrowsePreviewNotice>
      ) : communityPhase === "skeleton" ? (
        <ThreadListSkeleton />
      ) : communityPhase === "error" ? (
        <p className="empty-message">読み込みに失敗しました（{error}）</p>
      ) : communityPhase === "empty" ? (
        <p className="empty-message">
          {qParam
            ? "一致するスレッドはありません。"
            : "スレッドがありません。"}
        </p>
      ) : (
        <ul className="thread-list">
          {threads.map((thread) => (
            <li key={thread.id} className="thread-card-row">
              <Link
                className="thread-card"
                to={`/communities/${thread.community.slug}/threads/${thread.id}`}
                state={communityThreadDetailState(thread)}
              >
                <h3 className="thread-card__title">{thread.title}</h3>
                <p className="thread-card__meta">
                  <span>{participantLabel(thread.anonymous_label)}</span>
                  <span aria-hidden="true"> · </span>
                  <span
                    className={`thread-card__replies${
                      thread.replies_count === 0 ? " is-zero" : ""
                    }`}
                  >
                    返信 {thread.replies_count}
                  </span>
                </p>
                <p className="thread-card__preview">{thread.body_preview}</p>
                <span
                  className={officialBoardClass(
                    "thread-card__board",
                    thread.community.is_official
                  )}
                >
                  {thread.community.name}
                  <OfficialBadge official={thread.community.is_official} />
                </span>
              </Link>
              <CommunityReportMenu
                targetType="community_thread"
                targetId={thread.id}
                canReport={Boolean(thread.can_report)}
                ariaLabel="この投稿を通報"
              />
            </li>
          ))}
        </ul>
      )}

      {showComposeFab
        ? createPortal(
            <button
              type="button"
              className="compose-fab home-compose-fab community-compose-fab shell-hide-on-desktop is-visible"
              aria-label="匿名で投稿"
              onClick={openCompose}
            >
              ＋
            </button>,
            document.body
          )
        : null}
    </div>
  );
}
