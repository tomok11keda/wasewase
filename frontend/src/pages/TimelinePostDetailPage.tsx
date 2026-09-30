import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
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
import { isBrowsePreview, useSession } from "../lib/session";

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

  useEffect(() => {
    const next = readInitialTimelinePost(location.state, postId);
    mutatedRef.current = false;
    fetchGen.current += 1;
    setPost(next);
    setLoading(!next);
    setHydrated(!next);
    setError(null);
  }, [postId, location.key]);

  const load = useCallback(async () => {
    if (!Number.isFinite(postId) || postId <= 0) {
      setPost(null);
      setError("この投稿は表示できません");
      setLoading(false);
      setHydrated(true);
      return;
    }
    const gen = ++fetchGen.current;
    const hadPreview = Boolean(readInitialTimelinePost(location.state, postId));
    if (!hadPreview) {
      setLoading(true);
      setError(null);
    }
    try {
      const next = await fetchTimelinePost(postId);
      if (gen !== fetchGen.current) return;
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
      if (gen !== fetchGen.current) return;
      const message =
        err instanceof Error ? err.message : "この投稿は表示できません";
      if (hadPreview && message !== "この投稿は表示できません") {
        setHydrated(true);
        return;
      }
      setPost(null);
      setError(message);
      setHydrated(true);
    } finally {
      if (gen === fetchGen.current) setLoading(false);
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
  }, [sessionLoading, browsePreview, load]);

  const authenticated = Boolean(me?.authenticated);

  return (
    <div className="post-detail-page" data-spa-page="投稿">
      {browsePreview ? (
        <BrowsePreviewNotice nextPath={`/app/posts/${postId}`}>
          投稿の詳細はログイン後に表示されます。
        </BrowsePreviewNotice>
      ) : post ? (
        <div className="post-detail-body">
          <TimelinePostCard
            post={post}
            authenticated={authenticated}
            variant="detail"
            focusComposer={focusComposerOnce}
            commentsPending={!hydrated}
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
      ) : loading || sessionLoading ? (
        <p className="empty-message">読み込み中…</p>
      ) : (
        <p className="empty-message">{error || "この投稿は表示できません"}</p>
      )}
    </div>
  );
}
