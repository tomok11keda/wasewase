import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  createTimelinePost,
  fetchQuotable,
  fetchTimeline,
  type TimelineFeedResponse,
  type TimelinePost,
} from "../features/timeline/api";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import { restoreScrollPosition } from "../features/profile/api";
import {
  useActiveMainTab,
  useSoftTabRefetch,
} from "../layouts/TabKeepAliveLayout";
import { ImagePickField } from "../components/ImagePickField";
import { FacultyFilterTabs } from "../components/FacultyFilterTabs";

export function HomePage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const activeTab = useActiveMainTab();
  const [searchParams, setSearchParams] = useSearchParams();
  const feed = (searchParams.get("feed") === "following" ? "following" : "all") as
    | "all"
    | "following";
  const faculty = searchParams.get("faculty") || "";
  const ownFaculty = me?.user?.department || "";

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

  const [posts, setPosts] = useState<TimelinePost[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [followingUnauth, setFollowingUnauth] = useState(false);

  const [composeBody, setComposeBody] = useState("");
  const [composeImage, setComposeImage] = useState<File | null>(null);
  const [quoteId, setQuoteId] = useState<number | null>(null);
  const [quotePreview, setQuotePreview] = useState<TimelinePost | null>(null);
  const [composeBusy, setComposeBusy] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);

  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const composeSectionRef = useRef<HTMLDivElement | null>(null);
  const hasDataRef = useRef(false);
  const authenticated = Boolean(me?.authenticated);
  // Keep-alive panes use transform, so fixed FAB must portal to body.
  // Show only while the home timeline is the active view.
  const normalizedPath = location.pathname.replace(/\/$/, "") || "/";
  const showComposeFab =
    activeTab === "home" ||
    (activeTab === null && normalizedPath === "/");

  const openCompose = useCallback(() => {
    if (!authenticated) {
      navigate(spaLoginPath("/app/?compose=1"));
      return;
    }
    setComposeOpen(true);
    window.requestAnimationFrame(() => {
      composeSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }, [authenticated, navigate]);

  // Open compose from Search / Sidebar without full reload
  useEffect(() => {
    const state = location.state as { openCompose?: boolean } | null;
    const wantCompose =
      Boolean(state?.openCompose) || searchParams.get("compose") === "1";
    if (!wantCompose) return;
    if (authenticated) {
      setComposeOpen(true);
    }
    if (state?.openCompose) {
      navigate(".", { replace: true, state: {} });
    }
    if (searchParams.get("compose") === "1") {
      const next = new URLSearchParams(searchParams);
      next.delete("compose");
      setSearchParams(next, { replace: true });
    }
  }, [authenticated, location.state, navigate, searchParams, setSearchParams]);

  const loadInitial = useCallback(
    async (mode: "initial" | "soft" = "initial") => {
      if (mode === "initial" && !hasDataRef.current) {
        setLoading(true);
      }
      setError(null);
      try {
        const data = await fetchTimeline({
          feed,
          faculty: faculty || undefined,
        });
        setPosts(data.posts);
        setHasMore(data.has_more);
        setNextOffset(data.next_offset);
        setFollowingUnauth(Boolean(data.feed_following_unauthenticated));
        hasDataRef.current = true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        setLoading(false);
      }
    },
    [feed, faculty]
  );

  useEffect(() => {
    void loadInitial(hasDataRef.current ? "soft" : "initial");
  }, [loadInitial]);

  useSoftTabRefetch("home", () => loadInitial("soft"));

  useEffect(() => {
    if (loading) return;
    restoreScrollPosition("/");
  }, [loading, posts.length]);

  useEffect(() => {
    if (!hasMore || loading || loadingMore) return;
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        setLoadingMore(true);
        void fetchTimeline({
          feed,
          faculty: faculty || undefined,
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
  }, [feed, faculty, hasMore, loading, loadingMore, nextOffset]);

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
      setComposeOpen(true);
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
    setComposeBusy(true);
    try {
      const post = await createTimelinePost({
        body: body || (quoteId ? "リポスト" : ""),
        image: composeImage,
        quoted_post_id: quoteId,
      });
      setPosts((prev) => [post, ...prev]);
      setComposeBody("");
      setComposeImage(null);
      setQuoteId(null);
      setQuotePreview(null);
      setComposeOpen(false);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "投稿に失敗しました");
    } finally {
      setComposeBusy(false);
    }
  };

  return (
    <div className="main-inner timeline-home" data-spa-page="タイムライン">
      <FacultyFilterTabs
        value={faculty}
        ownFaculty={ownFaculty}
        onChange={(next) => patchParams({ faculty: next })}
      />

      <nav className="feed-scope-tabs" aria-label="タイムライン表示範囲">
        <button
          type="button"
          className={`feed-scope-tab${feed === "all" ? " is-active" : ""}`}
          onClick={() => patchParams({ feed: "" })}
        >
          全体
        </button>
        <button
          type="button"
          className={`feed-scope-tab${feed === "following" ? " is-active" : ""}`}
          onClick={() => patchParams({ feed: "following" })}
        >
          フォロー中
        </button>
      </nav>

      {faculty ? (
        <p className="faculty-hint">🏷 {faculty}のユーザーの投稿を表示中</p>
      ) : null}

      {followingUnauth ? (
        <p className="feed-scope-hint">
          フォロー中の投稿を見るには
          <Link to={spaLoginPath("/app/?feed=following")}>
            ログイン
          </Link>
          してください。
        </p>
      ) : null}

      {authenticated ? (
        <div className="spa-compose" ref={composeSectionRef}>
          {!composeOpen ? (
            <button
              type="button"
              className="spa-compose__open"
              onClick={openCompose}
            >
              いまどうしてる？
            </button>
          ) : (
            <form className="spa-compose__form" onSubmit={submitCompose}>
              <textarea
                value={composeBody}
                onChange={(e) => setComposeBody(e.target.value)}
                maxLength={280}
                rows={3}
                placeholder="いま思ったこと、質問、情報共有など（280字まで）"
              />
              {quotePreview ? (
                <div className="quoted-post-card spa-compose__quote">
                  <strong>
                    {quotePreview.author?.display_name || "投稿"} をリポスト
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
                <button type="button" onClick={() => setComposeOpen(false)}>
                  閉じる
                </button>
                <button type="submit" disabled={composeBusy}>
                  投稿する
                </button>
              </div>
            </form>
          )}
        </div>
      ) : (
        <p className="feed-scope-hint">
          投稿するには
          <Link to={spaLoginPath("/app/")}>ログイン</Link>
          してください。
        </p>
      )}

      {sessionLoading || (loading && posts.length === 0) ? (
        <p className="empty-message">読み込み中…</p>
      ) : error && posts.length === 0 ? (
        <p className="empty-message">読み込みに失敗しました（{error}）</p>
      ) : posts.length === 0 ? (
        <p className="empty-message">まだ投稿がありません。</p>
      ) : (
        <div className="timeline-list" id="timeline-list">
          {posts.map((post) => (
            <TimelinePostCard
              key={post.id}
              post={post}
              authenticated={authenticated}
              onChange={(next: TimelinePost) =>
                setPosts((prev) =>
                  prev.map((p) => (p.id === next.id ? next : p))
                )
              }
              onRemove={(id: number) =>
                setPosts((prev) => prev.filter((p) => p.id !== id))
              }
              onQuote={onQuote}
              onRequireLogin={requireLogin}
            />
          ))}
        </div>
      )}

      <div ref={sentinelRef} className="timeline-scroll-sentinel" aria-hidden="true" />
      {loadingMore ? <p className="empty-message">読み込み中…</p> : null}
      {!hasMore && posts.length > 0 ? (
        <p className="empty-message">すべて表示しました</p>
      ) : null}

      {showComposeFab
        ? createPortal(
            <button
              type="button"
              className="compose-fab shell-hide-on-desktop"
              aria-label="投稿する"
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
