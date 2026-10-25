import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { PostDetailSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchTimelinePost,
  type TimelinePost,
} from "../features/timeline/api";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import {
  readInitialTimelinePost,
  type TimelinePostDetailNavState,
} from "../features/timeline/postAnchor";
import {
  DETAIL_NETWORK_ERROR,
  detailContentPhase,
  detailItemMatches,
  shouldKeepDetailPreview,
} from "../lib/detailContentPhase";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function TimelinePostDetailPage() {
  const { postId: rawPostId } = useParams();
  const postId = Number(rawPostId);
  const navigate = useNavigate();
  const location = useLocation();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const navState = (location.state || null) as TimelinePostDetailNavState | null;
  const focusComposerOnce = useRef(Boolean(navState?.focusComposer)).current;

  const [post, setPost] = useState<TimelinePost | null>(() =>
    readInitialTimelinePost(location.state, postId)
  );
  const [loading, setLoading] = useState(() => !post);
  const [hydrated, setHydrated] = useState(() => !post);
  const [error, setError] = useState<string | null>(null);
  const mutatedRef = useRef(false);
  const fetchGen = useRef(0);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const prevUserIdRef = useRef(sessionUserId);

  const goBack = useCallback(() => {
    if (navState?.fromWaseWase) {
      navigate(-1);
      return;
    }
    navigate("/", { replace: true });
  }, [navState?.fromWaseWase, navigate]);

  const applyLocalPost = useCallback((next: TimelinePost) => {
    mutatedRef.current = true;
    setPost(next);
  }, []);

  useLayoutEffect(() => {
    const next = readInitialTimelinePost(location.state, postId);
    mutatedRef.current = false;
    nextRequestId(fetchGen);
    setPost(next);
    setLoading(!next);
    setHydrated(!next);
    setError(null);
    // location.key identifies this navigation; state is read for the matching snapshot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postId, location.key]);

  useLayoutEffect(() => {
    if (prevUserIdRef.current === sessionUserId) return;
    prevUserIdRef.current = sessionUserId;
    nextRequestId(fetchGen);
    mutatedRef.current = false;
    setPost(null);
    setLoading(true);
    setHydrated(false);
    setError(null);
  }, [sessionUserId]);

  const load = useCallback(async () => {
    if (!Number.isFinite(postId) || postId <= 0) {
      setPost(null);
      setError("この投稿は表示できません");
      setLoading(false);
      setHydrated(true);
      return;
    }
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    const hadPreview = Boolean(readInitialTimelinePost(location.state, postId));
    setError(null);
    if (!hadPreview) {
      setLoading(true);
    }
    try {
      const next = await fetchTimelinePost(postId);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      if (mutatedRef.current) {
        setPost((prev) =>
          prev
            ? {
                ...prev,
                comments: next.comments,
                comment_count: next.comment_count,
                view_count: next.view_count,
              }
            : next
        );
      } else {
        setPost(next);
      }
      setError(null);
      setHydrated(true);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      if (shouldKeepDetailPreview(hadPreview, err)) {
        setError(DETAIL_NETWORK_ERROR);
        setHydrated(false);
        return;
      }
      setPost(null);
      setError(
        err instanceof Error ? err.message : "この投稿は表示できません"
      );
      setHydrated(true);
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [postId, location.state]);

  useEffect(() => {
    if (sessionLoading) return;
    if (browsePreview) {
      setPost(null);
      setError(null);
      setLoading(false);
      setHydrated(true);
      return;
    }
    void load();
  }, [sessionLoading, browsePreview, load, sessionUserId]);

  const authenticated = Boolean(me?.authenticated);
  const postMatches = detailItemMatches(post, postId);
  const phase = detailContentPhase({
    browsePreview,
    loading: sessionLoading || loading || Boolean(post && !postMatches),
    error: postMatches ? error : post ? null : error,
    hasItem: postMatches,
    hydrated: postMatches && hydrated,
  });

  return (
    <div className="post-detail-page" data-spa-page="投稿">
      {phase === "browse" ? (
        <BrowsePreviewNotice nextPath={`/app/posts/${postId}`}>
          投稿の詳細はログイン後に表示されます。
        </BrowsePreviewNotice>
      ) : phase === "skeleton" ? (
        <PostDetailSkeleton />
      ) : post && (phase === "preview" || phase === "ready") ? (
        <div className="post-detail-body">
          {error === DETAIL_NETWORK_ERROR ? (
            <p className="feed-scope-hint">
              通信に失敗しました。
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void load()}
              >
                再試行
              </button>
            </p>
          ) : null}
          <TimelinePostCard
            post={post}
            authenticated={authenticated}
            variant="detail"
            focusComposer={focusComposerOnce && phase === "ready"}
            commentsPending={!hydrated}
            hydrated={hydrated}
            composerUser={me?.user ?? null}
            onChange={applyLocalPost}
            onRemove={() => {
              goBack();
            }}
            onQuote={() => {
              navigate("/", { state: { openCompose: true } });
            }}
            onRequireLogin={() => {
              navigate(spaLoginPath(`/app/posts/${postId}`));
            }}
          />
        </div>
      ) : (
        <div className="empty-message">
          <p>{error || "この投稿は表示できません"}</p>
          <p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void load()}
            >
              再試行
            </button>
          </p>
        </div>
      )}
    </div>
  );
}
