import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { VerifiedOrganizationBadge } from "../components/VerifiedOrganizationBadge";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchOrganizationPosts,
  fetchOrganizationProfile,
  OrganizationRequestError,
  type OrganizationPostsPayload,
} from "../features/orgs/api";
import { RecruitingChatSection } from "../features/orgs/RecruitingChatSection";
import {
  organizationCategoryLabel,
  organizationExternalHref,
  organizationInitial,
  type OrganizationProfilePayload,
} from "../features/orgs/orgProfile";
import {
  parseRecruitingChat,
  type RecruitingChatEnvelope,
} from "../features/orgs/recruitingChat";
import { fetchRecruitingChat } from "../features/orgs/recruitingChatApi";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import type { TimelinePost } from "../features/timeline/api";
import { isBrowsePreview, useSession } from "../lib/session";

function statusFromError(err: unknown): string {
  if (err instanceof OrganizationRequestError) return err.code;
  return "load_failed";
}

export function OrganizationProfilePage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const [payload, setPayload] = useState<OrganizationProfilePayload | null>(
    null
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [posts, setPosts] = useState<TimelinePost[]>([]);
  const [postsMeta, setPostsMeta] = useState<OrganizationPostsPayload | null>(
    null
  );
  const [postsLoading, setPostsLoading] = useState(false);
  const [postsError, setPostsError] = useState<string | null>(null);
  const [postsLoadingMore, setPostsLoadingMore] = useState(false);
  const [recruiting, setRecruiting] = useState<RecruitingChatEnvelope | null>(
    null
  );
  const [recruitingLoading, setRecruitingLoading] = useState(false);
  const [recruitingError, setRecruitingError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!slug) {
      setError("not_found");
      setPayload(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOrganizationProfile(slug);
      setPayload(data);
    } catch (err) {
      setPayload(null);
      setRecruiting(null);
      setError(statusFromError(err));
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    if (sessionLoading) return;
    if (browsePreview) {
      setLoading(false);
      setPayload(null);
      setError(null);
      return;
    }
    void load();
  }, [sessionLoading, browsePreview, load]);

  const loadPosts = useCallback(
    async (nextOffset = 0) => {
      if (!slug) return;
      if (nextOffset > 0) setPostsLoadingMore(true);
      else setPostsLoading(true);
      setPostsError(null);
      try {
        const data = await fetchOrganizationPosts(slug, nextOffset);
        setPostsMeta(data);
        setPosts((prev) =>
          nextOffset > 0 ? [...prev, ...data.posts] : data.posts
        );
      } catch (err) {
        if (nextOffset === 0) {
          setPosts([]);
          setPostsMeta(null);
        }
        setPostsError(statusFromError(err));
      } finally {
        setPostsLoading(false);
        setPostsLoadingMore(false);
      }
    },
    [slug]
  );

  const loadRecruiting = useCallback(async () => {
    if (!slug || !payload) return;
    const summary = parseRecruitingChat(payload.recruiting_chat);
    setRecruiting({
      ok: true,
      recruiting_chat: summary,
      can_create: payload.can_manage && summary == null,
      can_manage: payload.can_manage,
    });
    setRecruitingLoading(true);
    setRecruitingError(null);
    try {
      setRecruiting(await fetchRecruitingChat(slug));
    } catch {
      setRecruiting({
        ok: true,
        recruiting_chat: summary,
        can_create: payload.can_manage && summary == null,
        can_manage: payload.can_manage,
      });
      setRecruitingError("新歓チャットの最新情報を取得できませんでした。");
    } finally {
      setRecruitingLoading(false);
    }
  }, [slug, payload]);

  useEffect(() => {
    if (sessionLoading || browsePreview || !payload || !slug) return;
    void loadPosts(0);
  }, [sessionLoading, browsePreview, payload, slug, loadPosts]);

  useEffect(() => {
    if (sessionLoading || browsePreview || !payload || !slug) return;
    void loadRecruiting();
  }, [sessionLoading, browsePreview, payload, slug, loadRecruiting]);

  if (!slug) {
    return <Navigate to="/" replace />;
  }

  const loginNext = `/app/orgs/${slug}`;

  if (browsePreview) {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <BrowsePreviewNotice nextPath={loginNext}>
            団体プロフィールはログイン後に表示されます。
          </BrowsePreviewNotice>
        </div>
      </div>
    );
  }

  if (loading || sessionLoading) {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (error === "unauthorized") {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <p>団体プロフィールを表示するにはログインが必要です。</p>
          <p>
            <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
              ログイン
            </Link>
          </p>
        </div>
      </div>
    );
  }

  if (error === "not_found") {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <p>この団体は見つからないか、表示できません。</p>
        </div>
      </div>
    );
  }

  if (error || !payload) {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <p>通信に失敗しました。時間をおいて再度お試しください。</p>
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
      </div>
    );
  }

  const org = payload.organization;
  const instagram = organizationExternalHref(org.instagram_url);
  const website = organizationExternalHref(org.website_url);

  return (
    <div className="profile-page org-profile-page" data-spa-page="団体">
      <div className="main-inner">
        <section className="profile-card">
          <div className="profile-header org-profile-header">
            {org.avatar_url ? (
              <img
                className="profile-avatar org-profile-avatar user-avatar--image"
                src={org.avatar_url}
                alt=""
              />
            ) : (
              <span className="profile-avatar org-profile-avatar user-avatar--icon">
                {organizationInitial(org.name)}
              </span>
            )}
            <div className="profile-identity">
              <p className="org-profile-kicker">学生団体</p>
              <h1 className="profile-name">{org.name}</h1>
              <p className="org-profile-category">
                {organizationCategoryLabel(org.category)}
              </p>
              <VerifiedOrganizationBadge verified={org.is_verified} />
            </div>
          </div>

          {org.description ? (
            <p className="profile-bio org-profile-description">
              {org.description}
            </p>
          ) : (
            <p className="org-profile-empty">紹介文はまだありません。</p>
          )}

          {instagram || website ? (
            <div className="org-profile-links">
              {instagram ? (
                <a
                  className="org-profile-link"
                  href={instagram}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Instagram
                </a>
              ) : null}
              {website ? (
                <a
                  className="org-profile-link"
                  href={website}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Webサイト
                </a>
              ) : null}
            </div>
          ) : null}

          {payload.can_manage ? (
            <div className="profile-actions profile-actions--own">
              <Link className="btn btn-secondary" to={`/orgs/${org.slug}/edit`}>
                プロフィールを編集
              </Link>
            </div>
          ) : null}
        </section>

        <RecruitingChatSection
          slug={org.slug}
          envelope={recruiting}
          loading={recruitingLoading}
          error={recruiting && recruitingError ? null : recruitingError}
          onReload={() => void loadRecruiting()}
          onUpdated={(chat) => {
            setRecruiting((prev) => ({
              ok: true,
              recruiting_chat: chat,
              can_create: false,
              can_manage: Boolean(prev?.can_manage || chat.can_manage),
            }));
            setRecruitingError(null);
          }}
        />

        <section className="org-profile-posts" aria-label="投稿">
          <h2 className="org-profile-posts__title">投稿</h2>
          {postsMeta?.preview ? (
            <p className="org-profile-posts__preview" role="status">
              これらの投稿は一般公開されていません。管理者プレビューです。
            </p>
          ) : null}
          {postsMeta?.unpublished && !payload.can_manage ? (
            <p className="org-profile-empty">投稿はまだ公開されていません。</p>
          ) : postsLoading ? (
            <p className="org-profile-empty">投稿を読み込み中…</p>
          ) : postsError ? (
            <p className="org-profile-empty">
              投稿を読み込めませんでした。
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void loadPosts(0)}
              >
                再試行
              </button>
            </p>
          ) : posts.length === 0 ? (
            <p className="org-profile-empty">投稿はまだありません。</p>
          ) : (
            <div className="timeline-list org-profile-posts__list">
              {posts.map((post) => (
                <TimelinePostCard
                  key={post.id}
                  post={post}
                  authenticated={Boolean(me?.authenticated)}
                  onChange={(next) =>
                    setPosts((prev) =>
                      prev.map((item) => (item.id === next.id ? next : item))
                    )
                  }
                  onRemove={(id) =>
                    setPosts((prev) => prev.filter((item) => item.id !== id))
                  }
                  onQuote={() =>
                    navigate("/", { state: { openCompose: true } })
                  }
                  onRequireLogin={() =>
                    navigate(spaLoginPath(`/app/orgs/${org.slug}`))
                  }
                />
              ))}
            </div>
          )}
          {postsMeta?.has_more ? (
            <p className="org-profile-posts__more">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={postsLoadingMore}
                onClick={() => void loadPosts(postsMeta.next_offset)}
              >
                {postsLoadingMore ? "読み込み中…" : "さらに表示"}
              </button>
            </p>
          ) : null}
        </section>
      </div>
    </div>
  );
}
