import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useAccount } from "../lib/accountContext";
import { isBrowsePreview, useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { PostCardSkeleton } from "../components/skeleton";
import {
  HOME_TIMELINE_SORT,
  createTimelinePost,
  fetchQuotable,
  fetchTimeline,
  fetchTimelinePost,
  type TimelineFeedResponse,
  type TimelinePost,
} from "../features/timeline/api";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";
import { VerifiedOrganizationBadge } from "../components/VerifiedOrganizationBadge";
import { organizationPostDisplay } from "../features/timeline/organizationActor";
import { ComposeIdentity } from "../features/timeline/ComposeIdentity";
import { ComposeVisibility } from "../features/timeline/ComposeVisibility";
import {
  composeActorFromNavOrganization,
  composeActorKey,
  composeActorLabel,
  organizationIdForCompose,
  snapshotComposeActor,
  type ComposeActorSnapshot,
} from "../features/timeline/composeActor";
import {
  composeNoticeForOrganizationPost,
  DEFAULT_ORGANIZATION_COMPOSE_VISIBILITY,
  isUnpublishedOrganizationPost,
  type OrganizationPostVisibility,
} from "../features/timeline/organizationPostVisibility";
import { restoreScrollPosition } from "../features/profile/api";
import {
  TIMELINE_FEED_SKELETON_COUNT,
  timelineFeedPhase,
} from "../features/timeline/timelineFeedPhase";
import {
  useActiveMainTab,
  useSoftTabRefetch,
} from "../layouts/TabKeepAliveLayout";
import { ImagePickField } from "../components/ImagePickField";
import {
  parseTimelinePostHash,
  scrollToTimelinePost,
} from "../features/timeline/postAnchor";
import { analytics } from "../lib/analytics/events";
import { PullToRefresh } from "../lib/usePullToRefresh";
import {
  HOME_POST_SEARCH_HREF,
  HOME_POST_SEARCH_PLACEHOLDER,
} from "../features/search/homeSearchEntry";

export function HomePage() {
  const { me, loading: sessionLoading } = useSession();
  const { actor, selectOrganization } = useAccount();
  const browsePreview = isBrowsePreview(me);
  const liveComposeActor = snapshotComposeActor(actor);
  const liveComposeKey = composeActorKey(liveComposeActor);
  const navigate = useNavigate();
  const location = useLocation();
  const activeTab = useActiveMainTab();
  const [searchParams, setSearchParams] = useSearchParams();
  const faculty = searchParams.get("faculty") || "";
  const qParam = searchParams.get("q") || "";

  // Clear obsolete feed=/sort= query from bookmarks / old links.
  useEffect(() => {
    if (!searchParams.has("feed") && !searchParams.has("sort")) return;
    const next = new URLSearchParams(searchParams);
    next.delete("feed");
    next.delete("sort");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    analytics.timelineViewed();
  }, []);

  const [posts, setPosts] = useState<TimelinePost[]>([]);
  const [pinnedPost, setPinnedPost] = useState<TimelinePost | null>(null);
  const [postUnavailable, setPostUnavailable] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [composeBody, setComposeBody] = useState("");
  const [composeImage, setComposeImage] = useState<File | null>(null);
  const [quoteId, setQuoteId] = useState<number | null>(null);
  const [quotePreview, setQuotePreview] = useState<TimelinePost | null>(null);
  const [composeBusy, setComposeBusy] = useState(false);
  const [composeVisibility, setComposeVisibility] =
    useState<OrganizationPostVisibility>(
      DEFAULT_ORGANIZATION_COMPOSE_VISIBILITY
    );
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeActor, setComposeActor] = useState<ComposeActorSnapshot | null>(
    null
  );
  const [actorMismatch, setActorMismatch] = useState(false);
  const [composeNotice, setComposeNotice] = useState<string | null>(null);
  const [composeNoticeSlug, setComposeNoticeSlug] = useState<string | null>(
    null
  );
  const quoteOrgDisplay = organizationPostDisplay(quotePreview);
  const sendActor = composeActor || liveComposeActor;

  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const composeTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const composeBusyRef = useRef(false);
  const hasDataRef = useRef(false);
  const ensurePostReqRef = useRef(0);
  const authenticated = Boolean(me?.authenticated);
  // Keep-alive panes use transform, so fixed FAB / modal must portal to body.
  // Show only while the home timeline is the active view. Scroll position
  // must not hide it — the inline 「いまどうしてる？」 cue can coexist.
  const normalizedPath = location.pathname.replace(/\/$/, "") || "/";
  const showComposeFab =
    !composeOpen &&
    (activeTab === "home" ||
      (activeTab === null && normalizedPath === "/"));

  const hasComposeDraft = Boolean(
    composeBody.trim() || composeImage || quoteId
  );

  const openCompose = useCallback(() => {
    if (!authenticated) {
      navigate(spaLoginPath("/app/?compose=1"));
      return;
    }
    setComposeActor((prev) => prev ?? snapshotComposeActor(actor));
    setActorMismatch(false);
    setComposeOpen(true);
  }, [authenticated, navigate, actor]);

  const resetComposeDraft = useCallback(() => {
    setComposeBody("");
    setComposeImage(null);
    setQuoteId(null);
    setQuotePreview(null);
    setComposeVisibility(DEFAULT_ORGANIZATION_COMPOSE_VISIBILITY);
  }, []);

  const closeCompose = useCallback(() => {
    setComposeOpen(false);
    setComposeActor(null);
    setActorMismatch(false);
    resetComposeDraft();
  }, [resetComposeDraft]);

  const requestCloseCompose = useCallback(() => {
    if (composeBusy) return;
    if (
      hasComposeDraft &&
      !window.confirm("入力中の内容は破棄されます。閉じますか？")
    ) {
      return;
    }
    closeCompose();
  }, [closeCompose, composeBusy, hasComposeDraft]);

  // Open compose from Search / Sidebar without full reload
  useEffect(() => {
    const state = location.state as {
      openCompose?: boolean;
      composeOrganization?: unknown;
    } | null;
    const wantCompose =
      Boolean(state?.openCompose) || searchParams.get("compose") === "1";
    if (!wantCompose) return;
    if (authenticated) {
      const fromHub = composeActorFromNavOrganization(state?.composeOrganization);
      if (fromHub?.type === "organization") {
        selectOrganization(fromHub.organization.id);
        setComposeActor(fromHub);
        setActorMismatch(false);
        setComposeOpen(true);
      } else {
        openCompose();
      }
    }
    if (state?.openCompose) {
      navigate(".", { replace: true, state: {} });
    }
    if (searchParams.get("compose") === "1") {
      const next = new URLSearchParams(searchParams);
      next.delete("compose");
      setSearchParams(next, { replace: true });
    }
  }, [
    authenticated,
    location.state,
    navigate,
    openCompose,
    searchParams,
    selectOrganization,
    setSearchParams,
  ]);

  useEffect(() => {
    if (!composeOpen || !composeActor) {
      setActorMismatch(false);
      return;
    }
    setActorMismatch(composeActorKey(composeActor) !== liveComposeKey);
  }, [composeOpen, composeActor, liveComposeKey]);

  // Lock page scroll while compose overlay is open (keeps timeline scrollY).
  useEffect(() => {
    if (!composeOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [composeOpen]);

  // Focus textarea after open; Escape closes.
  useEffect(() => {
    if (!composeOpen) return;
    const focusTimer = window.setTimeout(() => {
      composeTextareaRef.current?.focus();
    }, 50);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        requestCloseCompose();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [composeOpen, requestCloseCompose]);

  // Keep modal above the iOS keyboard using visualViewport.
  useEffect(() => {
    if (!composeOpen) return;
    const vv = window.visualViewport;
    if (!vv) return;
    const sync = () => {
      document.documentElement.style.setProperty(
        "--compose-vv-offset",
        `${vv.offsetTop}px`
      );
      document.documentElement.style.setProperty(
        "--compose-vv-height",
        `${vv.height}px`
      );
    };
    sync();
    vv.addEventListener("resize", sync);
    vv.addEventListener("scroll", sync);
    return () => {
      vv.removeEventListener("resize", sync);
      vv.removeEventListener("scroll", sync);
      document.documentElement.style.removeProperty("--compose-vv-offset");
      document.documentElement.style.removeProperty("--compose-vv-height");
    };
  }, [composeOpen]);
  const loadInitial = useCallback(
    async (mode: "initial" | "soft" = "initial") => {
      if (browsePreview) {
        setPosts([]);
        setHasMore(false);
        setNextOffset(0);
        setError(null);
        setLoading(false);
        return;
      }
      if (mode === "initial" && !hasDataRef.current) {
        setLoading(true);
      }
      if (mode !== "soft") setError(null);
      try {
        const data = await fetchTimeline({
          sort: HOME_TIMELINE_SORT,
          faculty: faculty || undefined,
          q: qParam || undefined,
        });
        setPosts(data.posts);
        setHasMore(data.has_more);
        setNextOffset(data.next_offset);
        hasDataRef.current = true;
        setError(null);
        return true;
      } catch (err) {
        if (mode === "soft") return false;
        setError(err instanceof Error ? err.message : "load_failed");
        return false;
      } finally {
        if (mode !== "soft") setLoading(false);
      }
    },
    [faculty, qParam, browsePreview]
  );

  useEffect(() => {
    if (sessionLoading) return;
    void loadInitial(hasDataRef.current ? "soft" : "initial");
  }, [sessionLoading, loadInitial]);

  useSoftTabRefetch("home", () => {
    void loadInitial("soft");
  });

  const onVisibleHome =
    activeTab === "home" ||
    (activeTab === null && normalizedPath === "/");

  const stateHash = (location.state as { hash?: string } | null)?.hash;
  const targetPostId = onVisibleHome
    ? parseTimelinePostHash(location.hash) ?? parseTimelinePostHash(stateHash)
    : null;

  const visiblePosts = useMemo(() => {
    if (!pinnedPost) return posts;
    if (posts.some((p) => p.id === pinnedPost.id)) return posts;
    return [pinnedPost, ...posts];
  }, [posts, pinnedPost]);

  const waitingForTarget =
    Boolean(targetPostId) &&
    !browsePreview &&
    !postUnavailable &&
    !visiblePosts.some((p) => p.id === targetPostId);

  const feedPhase = timelineFeedPhase({
    browsePreview,
    sessionLoading,
    feedLoading: loading,
    waitingForTarget,
    postUnavailable,
    error,
    postCount: visiblePosts.length,
  });

  useEffect(() => {
    if (!onVisibleHome || browsePreview) return;
    if (!targetPostId) {
      ensurePostReqRef.current += 1;
      setPinnedPost(null);
      setPostUnavailable(false);
      return;
    }
    if (posts.some((p) => p.id === targetPostId)) {
      ensurePostReqRef.current += 1;
      setPinnedPost(null);
      setPostUnavailable(false);
      return;
    }
    if (pinnedPost?.id === targetPostId) {
      setPostUnavailable(false);
      return;
    }
    if (loading) return;

    const req = ++ensurePostReqRef.current;
    setPostUnavailable(false);
    void fetchTimelinePost(targetPostId)
      .then((post) => {
        if (req !== ensurePostReqRef.current) return;
        setPinnedPost(post);
        setPostUnavailable(false);
      })
      .catch(() => {
        if (req !== ensurePostReqRef.current) return;
        setPinnedPost(null);
        setPostUnavailable(true);
      });
  }, [
    onVisibleHome,
    browsePreview,
    targetPostId,
    loading,
    posts,
    pinnedPost?.id,
  ]);

  const visiblePostIdsKey = visiblePosts.map((p) => p.id).join(",");

  useEffect(() => {
    if (!onVisibleHome || loading || !targetPostId || postUnavailable) return;
    if (!visiblePosts.some((p) => p.id === targetPostId)) return;

    let cancelled = false;
    const tryScroll = () => {
      if (cancelled) return;
      scrollToTimelinePost(targetPostId);
    };
    tryScroll();
    const frame = window.requestAnimationFrame(tryScroll);
    const timer = window.setTimeout(tryScroll, 120);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [
    onVisibleHome,
    loading,
    targetPostId,
    postUnavailable,
    visiblePostIdsKey,
    location.key,
  ]);

  useEffect(() => {
    if (loading) return;
    if (targetPostId) return;
    if (activeTab !== "home") return;
    restoreScrollPosition("/");
  }, [loading, posts.length, targetPostId, activeTab]);

  useEffect(() => {
    if (browsePreview || !hasMore || loading || loadingMore) return;
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        setLoadingMore(true);
        void fetchTimeline({
          sort: HOME_TIMELINE_SORT,
          faculty: faculty || undefined,
          q: qParam || undefined,
          offset: nextOffset,
        })
          .then((data: TimelineFeedResponse) => {
            setPosts((prev) => {
              const seen = new Set(prev.map((p) => p.id));
              const appended = data.posts.filter((p) => !seen.has(p.id));
              return [...prev, ...appended];
            });
            setHasMore(data.has_more);
            setNextOffset(data.next_offset);
          })
          .catch(() => {
            /* ignore */
          })
          .finally(() => setLoadingMore(false));
      },
      { rootMargin: "200px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [browsePreview, faculty, qParam, hasMore, loading, loadingMore, nextOffset]);

  const requireLogin = () => {
    navigate(spaLoginPath("/app/"));
  };

  const onQuote = async (post: TimelinePost) => {
    if (!authenticated) {
      requireLogin();
      return;
    }
    try {
      const quoted = await fetchQuotable(post.id);
      setQuoteId(quoted.id);
      setQuotePreview(quoted);
      openCompose();
    } catch {
      window.alert("この投稿はリポストできません。");
    }
  };

  const submitCompose = async (e: FormEvent) => {
    e.preventDefault();
    if (!authenticated) {
      requireLogin();
      return;
    }
    const body = composeBody.trim();
    if (!body && !composeImage && !quoteId) return;
    if (actorMismatch) return;
    if (composeBusyRef.current) return;
    composeBusyRef.current = true;
    setComposeBusy(true);
    try {
      const organizationId = organizationIdForCompose(sendActor);
      const post = await createTimelinePost({
        body: body || (quoteId ? "リポスト" : ""),
        image: composeImage,
        quoted_post_id: quoteId,
        organization_id: organizationId,
        visibility:
          sendActor.type === "organization" ? composeVisibility : null,
      });
      analytics.timelinePostCreated({
        has_image: Boolean(composeImage),
        is_quote: Boolean(quoteId),
      });
      const unpublished = isUnpublishedOrganizationPost(post);
      if (post.actor_type === "organization") {
        setComposeNotice(
          composeNoticeForOrganizationPost({
            unpublished,
            organizationName: composeActorLabel(sendActor),
          })
        );
        setComposeNoticeSlug(
          sendActor.type === "organization" ? sendActor.organization.slug : null
        );
        if (!unpublished) {
          setPosts((prev) => [post, ...prev]);
        }
      } else {
        setPosts((prev) => [post, ...prev]);
        setComposeNotice(null);
        setComposeNoticeSlug(null);
      }
      resetComposeDraft();
      setComposeOpen(false);
      setComposeActor(null);
      setActorMismatch(false);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "投稿に失敗しました");
    } finally {
      composeBusyRef.current = false;
      setComposeBusy(false);
    }
  };

  const composeForm = (
    <form className="spa-compose__form" onSubmit={submitCompose}>
      <ComposeIdentity
        actor={sendActor}
        personalName={me?.user?.display_name || "自分"}
        personalAvatarUrl={me?.user?.avatar_url}
        personalInitial={me?.user?.initial}
        personalVerified={me?.user?.is_operator_verified}
      />
      {actorMismatch ? (
        <div className="spa-compose__mismatch" role="status">
          <p>
            投稿の途中でアカウントが切り替わりました。この下書きは「
            {composeActorLabel(sendActor)}」名義のままです。送信名義を選んでください。
          </p>
          <div className="spa-compose__mismatch-actions">
            <button
              type="button"
              onClick={() => setActorMismatch(false)}
            >
              この名義のまま続ける
            </button>
            <button
              type="button"
              onClick={() => {
                setComposeActor(snapshotComposeActor(actor));
                setActorMismatch(false);
              }}
            >
              切り替えた「{composeActorLabel(liveComposeActor)}」名義に変更
            </button>
          </div>
        </div>
      ) : null}
      <textarea
        ref={composeTextareaRef}
        value={composeBody}
        onChange={(e) => setComposeBody(e.target.value)}
        maxLength={280}
        rows={3}
        placeholder="いま思ったこと、質問、情報共有など（280字まで）"
        disabled={composeBusy}
      />
      {sendActor.type === "organization" ? (
        <ComposeVisibility
          value={composeVisibility}
          onChange={setComposeVisibility}
          disabled={composeBusy}
        />
      ) : null}
      {quotePreview ? (
        <div className="quoted-post-card spa-compose__quote">
          <strong>
            {quoteOrgDisplay ? (
              <>
                <span className="account-verified-name">
                  <span className="account-verified-name__text">
                    {quoteOrgDisplay.name}
                  </span>
                  <VerifiedOrganizationBadge
                    verified={quoteOrgDisplay.isVerified}
                    compact
                  />
                </span>
                {quoteOrgDisplay.kindLabel ? (
                  <span className="tweet-org-kind">
                    {" "}
                    {quoteOrgDisplay.kindLabel}
                  </span>
                ) : null}{" "}
              </>
            ) : (
              <AccountDisplayName
                name={quotePreview.author?.display_name || "投稿"}
                verified={quotePreview.author?.is_operator_verified}
              />
            )}
            をリポスト
          </strong>
          <p>{quotePreview.body.slice(0, 120)}</p>
          <button
            type="button"
            onClick={() => {
              setQuoteId(null);
              setQuotePreview(null);
            }}
          >
            解除
          </button>
        </div>
      ) : null}
      <div className="spa-compose__actions">
        <div className="spa-compose__image">
          <ImagePickField
            id="compose-image"
            value={composeImage}
            onChange={setComposeImage}
            disabled={composeBusy}
            hint="JPEG / PNG / GIF / WebP（任意）"
          />
        </div>
        <button type="button" onClick={requestCloseCompose}>
          閉じる
        </button>
        <button type="submit" disabled={composeBusy || actorMismatch}>
          {composeBusy
            ? "保存中…"
            : sendActor.type === "organization" &&
                composeVisibility === "draft"
              ? "下書き保存"
              : sendActor.type === "organization"
                ? "公開する"
                : "投稿する"}
        </button>
      </div>
    </form>
  );

  return (
    <div className="main-inner timeline-home" data-spa-page="タイムライン">
      <PullToRefresh
        enabled={onVisibleHome && !composeOpen && !browsePreview}
        onRefresh={async () => {
          if (!(await loadInitial("soft"))) {
            throw new Error("refresh_failed");
          }
        }}
      />
      {sessionLoading ? null : authenticated ? (
        <div className="home-compose">
          <button
            type="button"
            className="home-compose__open"
            onClick={openCompose}
          >
            {liveComposeActor.type === "organization" &&
            liveComposeActor.organization.avatar_url ? (
              <img
                className="home-compose__avatar"
                src={liveComposeActor.organization.avatar_url}
                alt=""
              />
            ) : liveComposeActor.type === "organization" ? (
              <span
                className="home-compose__avatar home-compose__avatar--initial"
                aria-hidden="true"
              >
                {liveComposeActor.organization.name.slice(0, 1) || "?"}
              </span>
            ) : me?.user?.avatar_url ? (
              <img
                className="home-compose__avatar"
                src={me.user.avatar_url}
                alt=""
              />
            ) : (
              <span
                className="home-compose__avatar home-compose__avatar--initial"
                aria-hidden="true"
              >
                {me?.user?.initial || "?"}
              </span>
            )}
            <span className="home-compose__prompt">
              {liveComposeActor.type === "organization"
                ? `${liveComposeActor.organization.name}として投稿`
                : "いまどうしてる？"}
            </span>
          </button>
        </div>
      ) : (
        <p className="feed-scope-hint">
          投稿するには
          <Link to={spaLoginPath("/app/")}>ログイン</Link>
          してください。
        </p>
      )}
      <div className="home-search">
        <Link
          to={HOME_POST_SEARCH_HREF}
          className="home-search-bar"
          aria-label={HOME_POST_SEARCH_PLACEHOLDER}
        >
          <svg
            className="home-search-bar__icon"
            viewBox="0 0 24 24"
            width={18}
            height={18}
            aria-hidden="true"
            focusable="false"
          >
            <path
              fill="currentColor"
              d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"
            />
          </svg>
          <span className="home-search-bar__placeholder">
            {HOME_POST_SEARCH_PLACEHOLDER}
          </span>
        </Link>
      </div>
      {composeNotice ? (
        <p className="org-compose-notice" role="status">
          {composeNotice}
          {composeNoticeSlug ? (
            <>
              {" "}
              <Link to={`/orgs/${composeNoticeSlug}`}>団体プロフィールを開く</Link>
            </>
          ) : null}
          <button
            type="button"
            className="org-compose-notice__close"
            onClick={() => {
              setComposeNotice(null);
              setComposeNoticeSlug(null);
            }}
          >
            閉じる
          </button>
        </p>
      ) : null}
      {feedPhase === "skeleton" ? (
        <div className="timeline-list home-feed home-feed--skeleton">
          <PostCardSkeleton count={TIMELINE_FEED_SKELETON_COUNT} />
        </div>
      ) : feedPhase === "browse" ? (
        <BrowsePreviewNotice
          nextPath={
            targetPostId ? `/app/posts/${targetPostId}` : "/app/"
          }
        >
          タイムラインはログイン後に表示されます。
        </BrowsePreviewNotice>
      ) : feedPhase === "unavailable" ? (
        <p className="empty-message">この投稿は表示できません</p>
      ) : feedPhase === "error" ? (
        <p className="empty-message">読み込みに失敗しました（{error}）</p>
      ) : feedPhase === "empty" ? (
        <p className="empty-message">
          {qParam
            ? "一致する投稿はありません。"
            : "まだ投稿がありません。"}
        </p>
      ) : (
        <div className="timeline-list home-feed" id="timeline-list">
          {postUnavailable ? (
            <p className="empty-message">この投稿は表示できません</p>
          ) : null}
          {visiblePosts.map((post) => (
            <TimelinePostCard
              key={post.id}
              post={post}
              authenticated={authenticated}
              onChange={(next: TimelinePost) => {
                setPosts((prev) =>
                  prev.map((p) => (p.id === next.id ? next : p))
                );
                setPinnedPost((prev) =>
                  prev && prev.id === next.id ? next : prev
                );
              }}
              onRemove={(id: number) => {
                setPosts((prev) => prev.filter((p) => p.id !== id));
                setPinnedPost((prev) =>
                  prev && prev.id === id ? null : prev
                );
              }}
              onQuote={onQuote}
              onRequireLogin={requireLogin}
            />
          ))}
        </div>
      )}

      <div ref={sentinelRef} className="timeline-scroll-sentinel" aria-hidden="true" />
      {loadingMore ? <p className="empty-message">読み込み中…</p> : null}
      {!hasMore && visiblePosts.length > 0 ? (
        <p className="empty-message">すべて表示しました</p>
      ) : null}

      {showComposeFab
        ? createPortal(
            <button
              type="button"
              className="compose-fab home-compose-fab shell-hide-on-desktop is-visible"
              aria-label="投稿する"
              onClick={openCompose}
            >
              ＋
            </button>,
            document.body
          )
        : null}

      {composeOpen && authenticated
        ? createPortal(
            <div
              className="compose-modal spa-compose-modal"
              aria-hidden="false"
            >
              <div
                className="compose-modal__backdrop"
                onClick={requestCloseCompose}
              />
              <div
                className="compose-modal__panel"
                role="dialog"
                aria-modal="true"
                aria-labelledby="spa-compose-modal-title"
              >
                <header className="compose-modal__header">
                  <h2 id="spa-compose-modal-title">投稿する</h2>
                  <button
                    type="button"
                    className="compose-modal__close"
                    aria-label="閉じる"
                    onClick={requestCloseCompose}
                  >
                    ×
                  </button>
                </header>
                {composeForm}
              </div>
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
