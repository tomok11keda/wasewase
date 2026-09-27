import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchTimelinePost,
  type TimelinePost,
} from "../features/timeline/api";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import type { TimelinePostDetailNavState } from "../features/timeline/postAnchor";
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

  const [post, setPost] = useState<TimelinePost | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const goBack = useCallback(() => {
    if (navState?.fromWaseWase) {
      navigate(-1);
      return;
    }
    navigate("/", { replace: true });
  }, [navState?.fromWaseWase, navigate]);

  const load = useCallback(async () => {
    if (!Number.isFinite(postId) || postId <= 0) {
      setPost(null);
      setError("この投稿は表示できません");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const next = await fetchTimelinePost(postId);
      setPost(next);
    } catch (err) {
      setPost(null);
      setError(
        err instanceof Error ? err.message : "この投稿は表示できません"
      );
    } finally {
      setLoading(false);
    }
  }, [postId]);

  useEffect(() => {
    if (sessionLoading) return;
    if (browsePreview) {
      setPost(null);
      setError(null);
      setLoading(false);
      return;
    }
    void load();
  }, [sessionLoading, browsePreview, load]);

  const authenticated = Boolean(me?.authenticated);

  return (
    <div className="post-detail-page" data-spa-page="投稿">
      <header className="post-detail-header">
        <button
          type="button"
          className="post-detail-back"
          aria-label="戻る"
          onClick={goBack}
        >
          ←
        </button>
        <h1 className="post-detail-title">投稿</h1>
      </header>

      {browsePreview ? (
        <BrowsePreviewNotice nextPath={`/app/posts/${postId}`}>
          投稿の詳細はログイン後に表示されます。
        </BrowsePreviewNotice>
      ) : loading || sessionLoading ? (
        <p className="empty-message">読み込み中…</p>
      ) : error || !post ? (
        <p className="empty-message">{error || "この投稿は表示できません"}</p>
      ) : (
        <div className="post-detail-body">
          <TimelinePostCard
            post={post}
            authenticated={authenticated}
            variant="detail"
            focusComposer={focusComposerOnce}
            onChange={setPost}
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
      )}
    </div>
  );
}
