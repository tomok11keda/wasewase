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
import {
  fetchCourseDiscover,
  type CourseDiscoverCard,
} from "../features/courses/api";
import { CourseDiscoveryPanel } from "../features/courses/CourseDiscoveryPanel";
import {
  useActiveMainTab,
  useSoftTabRefetch,
} from "../layouts/TabKeepAliveLayout";
import { analytics } from "../lib/analytics/events";
import { PullToRefresh } from "../lib/usePullToRefresh";

type Hub = "community" | "courses";

export function CommunitiesPage() {
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const navigate = useNavigate();
  const location = useLocation();
  const activeTab = useActiveMainTab();
  const [searchParams, setSearchParams] = useSearchParams();
  const hub: Hub =
    searchParams.get("hub") === "courses" ? "courses" : "community";
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

  const [enrolled, setEnrolled] = useState<CourseDiscoverCard[]>([]);
  const [active, setActive] = useState<CourseDiscoverCard[]>([]);
  const [popular, setPopular] = useState<CourseDiscoverCard[]>([]);
  const [courseLoading, setCourseLoading] = useState(false);
  const [courseError, setCourseError] = useState<string | null>(null);
  const hasCourseDataRef = useRef(false);
  const courseRequestIdRef = useRef(0);

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

  const setHub = (next: Hub) => {
    patchParams({ hub: next === "courses" ? "courses" : "" });
    if (next === "courses") {
      analytics.communityCourseTabOpened();
    }
  };

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

  const loadCourses = useCallback(
    async (mode: "initial" | "soft" = "initial") => {
      const requestId = nextRequestId(courseRequestIdRef);
      const startedUserId = userIdRef.current;
      if (browsePreview) {
        setEnrolled([]);
        setActive([]);
        setPopular([]);
        setCourseError(null);
        setCourseLoading(false);
        return;
      }
      if (mode === "initial" && !hasCourseDataRef.current) {
        setCourseLoading(true);
      }
      if (mode !== "soft") setCourseError(null);
      try {
        const data = await fetchCourseDiscover();
        if (!isLatestRequest(courseRequestIdRef, requestId)) return false;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return false;
        setEnrolled(data.enrolled);
        setActive(data.active);
        setPopular(data.popular);
        hasCourseDataRef.current = true;
        setCourseError(null);
        return true;
      } catch (err) {
        if (!isLatestRequest(courseRequestIdRef, requestId)) return false;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return false;
        if (mode === "soft") return false;
        setCourseError(err instanceof Error ? err.message : "load_failed");
        return false;
      } finally {
        if (isLatestRequest(courseRequestIdRef, requestId)) {
          setCourseLoading(false);
        }
      }
    },
    [browsePreview]
  );

  useEffect(() => {
    if (prevUserIdRef.current === sessionUserId) return;
    prevUserIdRef.current = sessionUserId;
    nextRequestId(requestIdRef);
    nextRequestId(courseRequestIdRef);
    hasDataRef.current = false;
    hasCourseDataRef.current = false;
    appliedKeyRef.current = "";
    setThreads([]);
    setEnrolled([]);
    setActive([]);
    setPopular([]);
    setError(null);
    setCourseError(null);
  }, [sessionUserId]);

  useEffect(() => {
    if (sessionLoading) return;
    if (hub === "community") {
      const soft = hasDataRef.current && appliedKeyRef.current === listKey;
      void load(soft ? "soft" : "initial");
    }
  }, [sessionLoading, hub, load, listKey]);

  useEffect(() => {
    if (sessionLoading) return;
    if (hub === "courses") {
      void loadCourses(hasCourseDataRef.current ? "soft" : "initial");
    }
  }, [sessionLoading, hub, loadCourses]);

  useEffect(() => {
    analytics.communityViewed();
  }, []);

  useSoftTabRefetch("communities", () => {
    if (hub === "courses") {
      void loadCourses("soft");
      return;
    }
    void load("soft");
  });

  useEffect(() => {
    if (hub === "community") return;
    setComposeOpen(false);
  }, [hub]);

  const normalizedPath = location.pathname.replace(/\/$/, "") || "/";
  const onCommunityList =
    activeTab === "communities" ||
    (activeTab === null && normalizedPath === "/communities");
  const showComposeFab =
    hub === "community" && !composeOpen && onCommunityList;
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

  return (
    <div
      className={`communities-page ptr-shift${composeOpen ? " is-composing" : ""}`}
      data-spa-page="コミュニティ"
    >
      <PullToRefresh
        enabled={onCommunityList && !composeOpen && !browsePreview}
        onRefresh={async () => {
          const ok =
            hub === "courses" ? await loadCourses("soft") : await load("soft");
          if (!ok) throw new Error("refresh_failed");
        }}
      />
      <div className="communities-header">
        <div className="communities-header-top">
          <h2>コミュニティ</h2>
          {hub === "community" ? (
            me?.authenticated ? (
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
            )
          ) : null}
        </div>
        {hub === "community" ? (
          <p className="community-anon-hint community-anon-hint--compact">
            Communityでは匿名で投稿できます
          </p>
        ) : null}

        <nav className="community-hub-tabs" aria-label="コミュニティと授業">
          <button
            type="button"
            className={`community-hub-tab${hub === "community" ? " is-active" : ""}`}
            aria-pressed={hub === "community"}
            onClick={() => setHub("community")}
          >
            コミュニティ
          </button>
          <button
            type="button"
            className={`community-hub-tab${hub === "courses" ? " is-active" : ""}`}
            aria-pressed={hub === "courses"}
            onClick={() => setHub("courses")}
          >
            授業
          </button>
        </nav>

        {hub === "community" ? (
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
        ) : (
          <p className="communities-hub-hint">
            履修中・活発・人気の授業を見つけられます
          </p>
        )}
      </div>

      {hub === "courses" ? (
        browsePreview ? (
          <BrowsePreviewNotice nextPath="/app/communities?hub=courses">
            授業の発見はログイン後に利用できます。
          </BrowsePreviewNotice>
        ) : (
        <CourseDiscoveryPanel
          enrolled={enrolled}
          active={active}
          popular={popular}
          loading={courseLoading && !hasCourseDataRef.current}
          error={courseError}
          authenticated={Boolean(me?.authenticated)}
        />
        )
      ) : (
        <>
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
                    <p className="thread-card__preview">
                      {thread.body_preview}
                    </p>
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
        </>
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
