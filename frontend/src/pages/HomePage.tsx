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
import { LocalSearchBar } from "../components/LocalSearchBar";
import { getImpressedPostIds } from "../features/timeline/impressions";

export function HomePage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const activeTab = useActiveMainTab();
  const [searchParams, setSearchParams] = useSearchParams();
  const sort = (
    searchParams.get("sort") === "latest" ? "latest" : "recommended"
  ) as "recommended" | "latest";
  const faculty = searchParams.get("faculty") || "";
  const qParam = searchParams.get("q") || "";
  const ownFaculty = me?.user?.department || "";

  const patchParams = useCallback(
    (patch: Record<string, string>) => {
      const next = new URLSearchParams(searchParams);
      Object.entries(patch).forEach(([key, value]) => {
        if (value) next.set(key, value);
        else next.delete(key);
      });
      // Timeline no longer uses feed=following; drop leftover deep links.
      next.delete("feed");
      setSearchParams(next);
    },
    [searchParams, setSearchParams]
  );

  // Clear obsolete feed= query from bookmarks / old links.
  useEffect(() => {
    if (!searchParams.has("feed")) return;
    const next = new URLSearchParams(searchParams);
    next.delete("feed");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const [posts, setPosts] = useState<TimelinePost[]>([]);
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
  const [composeOpen, setComposeOpen] = useState(false);

  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const composeTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const hasDataRef = useRef(false);
  const authenticated = Boolean(me?.authenticated);
  // Keep-alive panes use transform, so fixed FAB / modal must portal to body.
  // Show only while the home timeline is the active view.
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
    // Overlay only — do not scroll the timeline.
    setComposeOpen(true);
  }, [authenticated, navigate]);

  const resetComposeDraft = useCallback(() => {
    setComposeBody("");
    setComposeImage(null);
    setQuoteId(null);
    setQuotePreview(null);
  }, []);

  const closeCompose = useCallback(() => {
    setComposeOpen(false);
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
      if (mode === "initial" && !hasDataRef.current) {
        setLoading(true);
      }
      setError(null);
      try {
        const data = await fetchTimeline({
          sort,
          faculty: faculty || undefined,
          q: qParam || undefined,
          seen: sort === "recommended" ? getImpressedPostIds() : undefined,
        });
        setPosts(data.posts);
        setHasMore(data.has_more);
        setNextOffset(data.next_offset);
        hasDataRef.current = true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        setLoading(false);
      }
    },
    [sort, faculty, qParam]
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
          sort,
          faculty: faculty || undefined,
          q: qParam || undefined,
          offset: nextOffset,
          seen: sort === "recommended" ? getImpressedPostIds() : undefined,
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
  }, [sort, faculty, qParam, hasMore, loading, loadingMore, nextOffset]);

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
      resetComposeDraft();
      setComposeOpen(false);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "投稿に失敗しました");
    } finally {
      setComposeBusy(false);
    }
  };

  const composeForm = (
    <form className="spa-compose__form" onSubmit={submitCompose}>
      <textarea
        ref={composeTextareaRef}
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
        <button type="button" onClick={requestCloseCompose}>
          閉じる
        </button>
        <button type="submit" disabled={composeBusy}>
          投稿する
        </button>
      </div>
    </form>
  );

  return (
    <div className="main-inner timeline-home" data-spa-page="タイムライン">
      <FacultyFilterTabs
        value={faculty}
        ownFaculty={ownFaculty}
        onChange={(next) => patchParams({ faculty: next })}
      />

      <LocalSearchBar
        value={qParam}
        placeholder="タイムライン投稿を検索"
        ariaLabel="タイムライン内検索"
        onSubmit={(q) => patchParams({ q })}
        onClear={() => patchParams({ q: "" })}
      />
      {qParam ? (
        <p className="local-search-hint">
          「{qParam}」のタイムライン検索結果（コミュニティ・フリマは含みません）
        </p>
      ) : null}

      <nav className="ranking-sort-tabs" aria-label="タイムライン並び順">
        <button
          type="button"
          className={`ranking-sort-tab${sort === "recommended" ? " is-active" : ""}`}
          onClick={() => patchParams({ sort: "" })}
        >
          おすすめ
        </button>
        <button
          type="button"
          className={`ranking-sort-tab${sort === "latest" ? " is-active" : ""}`}
          onClick={() => patchParams({ sort: "latest" })}
        >
          最新
        </button>
      </nav>

      {faculty ? (
        <p className="faculty-hint">🏷 {faculty}のユーザーの投稿を表示中</p>
      ) : null}

      {authenticated ? (
        <div className="spa-compose">
          <button
            type="button"
            className="spa-compose__open"
            onClick={openCompose}
          >
            いまどうしてる？
          </button>
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
        <p className="empty-message">
          {qParam
            ? "一致する投稿はありません。"
            : "まだ投稿がありません。"}
        </p>
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
