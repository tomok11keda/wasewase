import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { PostCardSkeleton, ProfileHeaderSkeleton } from "../components/skeleton";
import { VerifiedOrganizationBadge } from "../components/VerifiedOrganizationBadge";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchOrganizationPosts,
  fetchOrganizationProfile,
  OrganizationRequestError,
  type OrganizationPostsPayload,
} from "../features/orgs/api";
import { OrganizationEventSection } from "../features/orgs/OrganizationEventSection";
import { OrganizationManageHub } from "../features/orgs/OrganizationManageHub";
import { RecruitingChatSection } from "../features/orgs/RecruitingChatSection";
import {
  fetchOrganizationEvents,
} from "../features/orgs/orgEventsApi";
import type { OrganizationEvent } from "../features/orgs/orgEvents";
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
import { useAccount } from "../lib/accountContext";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

function statusFromError(err: unknown): string {
  if (err instanceof OrganizationRequestError) {
    if (err.status === 403 || err.code === "forbidden") return "not_found";
    return err.code;
  }
  return "load_failed";
}

export function OrganizationProfilePage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const { selectOrganization } = useAccount();
  const browsePreview = isBrowsePreview(me);
  const viewerId = me?.authenticated ? me.user?.id ?? null : null;
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
  const [postsScope, setPostsScope] = useState<"public" | "unpublished">(
    "public"
  );
  const [recruiting, setRecruiting] = useState<RecruitingChatEnvelope | null>(
    null
  );
  const [recruitingLoading, setRecruitingLoading] = useState(false);
  const [recruitingError, setRecruitingError] = useState<string | null>(null);
  const [events, setEvents] = useState<OrganizationEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const slugRef = useRef(slug);
  const viewerIdRef = useRef(viewerId);
  const loadGenRef = useRef(0);
  const postsGenRef = useRef(0);
  const recruitingGenRef = useRef(0);
  const eventsGenRef = useRef(0);
  useEffect(() => {
    slugRef.current = slug;
  }, [slug]);
  useEffect(() => {
    viewerIdRef.current = viewerId;
  }, [viewerId]);
  useEffect(() => {
    setPostsScope("public");
  }, [slug]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!slug) {
        setError("not_found");
        setPayload(null);
        setLoading(false);
        return;
      }
      const requestedSlug = slug;
      const startedViewerId = viewerId;
      const requestId = nextRequestId(loadGenRef);
      setLoading(true);
      setError(null);
      setPayload(null);
      setPosts([]);
      setPostsMeta(null);
      setPostsError(null);
      setRecruiting(null);
      setRecruitingError(null);
      setEvents([]);
      setEventsError(null);
      try {
        const data = await fetchOrganizationProfile(requestedSlug);
        if (
          signal?.aborted ||
          !isLatestRequest(loadGenRef, requestId) ||
          slugRef.current !== requestedSlug
        ) {
          return;
        }
        if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
        setPayload(data);
      } catch (err) {
        if (
          signal?.aborted ||
          !isLatestRequest(loadGenRef, requestId) ||
          slugRef.current !== requestedSlug
        ) {
          return;
        }
        if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
        setPayload(null);
        setRecruiting(null);
        setEvents([]);
        setError(statusFromError(err));
      } finally {
        if (
          !signal?.aborted &&
          isLatestRequest(loadGenRef, requestId) &&
          slugRef.current === requestedSlug &&
          isSameUserScope(startedViewerId, viewerIdRef.current)
        ) {
          setLoading(false);
        }
      }
    },
    [slug, viewerId]
  );

  useEffect(() => {
    if (sessionLoading) return;
    if (browsePreview) {
      setLoading(false);
      setPayload(null);
      setPosts([]);
      setPostsMeta(null);
      setRecruiting(null);
      setEvents([]);
      setError(null);
      return;
    }
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [sessionLoading, browsePreview, load]);

  const loadPosts = useCallback(
    async (nextOffset = 0) => {
      if (!slug) return;
      const requestedSlug = slug;
      const startedViewerId = viewerId;
      const requestId =
        nextOffset > 0 ? postsGenRef.current : nextRequestId(postsGenRef);
      if (nextOffset > 0) setPostsLoadingMore(true);
      else setPostsLoading(true);
      setPostsError(null);
      try {
        const data = await fetchOrganizationPosts(
          requestedSlug,
          nextOffset,
          postsScope
        );
        if (
          !isLatestRequest(postsGenRef, requestId) ||
          slugRef.current !== requestedSlug
        ) {
          return;
        }
        if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
        setPostsMeta(data);
        setPosts((prev) =>
          nextOffset > 0 ? [...prev, ...data.posts] : data.posts
        );
      } catch (err) {
        if (
          !isLatestRequest(postsGenRef, requestId) ||
          slugRef.current !== requestedSlug
        ) {
          return;
        }
        if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
        if (nextOffset === 0) {
          setPosts([]);
          setPostsMeta(null);
        }
        setPostsError(statusFromError(err));
      } finally {
        if (
          isLatestRequest(postsGenRef, requestId) &&
          slugRef.current === requestedSlug &&
          isSameUserScope(startedViewerId, viewerIdRef.current)
        ) {
          setPostsLoading(false);
          setPostsLoadingMore(false);
        }
      }
    },
    [slug, viewerId, postsScope]
  );

  const loadRecruiting = useCallback(async () => {
    if (!slug || !payload) return;
    const requestedSlug = slug;
    const startedViewerId = viewerId;
    const requestId = nextRequestId(recruitingGenRef);
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
      const next = await fetchRecruitingChat(requestedSlug);
      if (
        !isLatestRequest(recruitingGenRef, requestId) ||
        slugRef.current !== requestedSlug
      ) {
        return;
      }
      if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
      setRecruiting(next);
    } catch {
      if (
        !isLatestRequest(recruitingGenRef, requestId) ||
        slugRef.current !== requestedSlug
      ) {
        return;
      }
      if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
      setRecruiting({
        ok: true,
        recruiting_chat: summary,
        can_create: payload.can_manage && summary == null,
        can_manage: payload.can_manage,
      });
      setRecruitingError("団体チャットの最新情報を取得できませんでした。");
    } finally {
      if (
        isLatestRequest(recruitingGenRef, requestId) &&
        slugRef.current === requestedSlug &&
        isSameUserScope(startedViewerId, viewerIdRef.current)
      ) {
        setRecruitingLoading(false);
      }
    }
  }, [slug, payload, viewerId]);

  useEffect(() => {
    if (sessionLoading || browsePreview || !payload || !slug) return;
    void loadPosts(0);
  }, [sessionLoading, browsePreview, payload, slug, loadPosts]);

  useEffect(() => {
    if (sessionLoading || browsePreview || !payload || !slug) return;
    void loadRecruiting();
  }, [sessionLoading, browsePreview, payload, slug, loadRecruiting]);

  const loadEvents = useCallback(async () => {
    if (!slug || !payload) return;
    const requestedSlug = slug;
    const startedViewerId = viewerId;
    const requestId = nextRequestId(eventsGenRef);
    setEventsLoading(true);
    setEventsError(null);
    try {
      const next = await fetchOrganizationEvents(requestedSlug);
      if (
        !isLatestRequest(eventsGenRef, requestId) ||
        slugRef.current !== requestedSlug
      ) {
        return;
      }
      if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
      setEvents(next.events);
    } catch {
      if (
        !isLatestRequest(eventsGenRef, requestId) ||
        slugRef.current !== requestedSlug
      ) {
        return;
      }
      if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
      setEvents([]);
      setEventsError("イベントを読み込めませんでした。");
    } finally {
      if (
        isLatestRequest(eventsGenRef, requestId) &&
        slugRef.current === requestedSlug &&
        isSameUserScope(startedViewerId, viewerIdRef.current)
      ) {
        setEventsLoading(false);
      }
    }
  }, [slug, payload, viewerId]);

  useEffect(() => {
    if (sessionLoading || browsePreview || !payload || !slug) return;
    void loadEvents();
  }, [sessionLoading, browsePreview, payload, slug, loadEvents]);

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

  if ((loading || sessionLoading) && !payload && !error) {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <ProfileHeaderSkeleton variant="org" />
          <section className="org-profile-posts" aria-label="投稿">
            <h2 className="org-profile-posts__title">投稿</h2>
            <PostCardSkeleton />
          </section>
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

        </section>

        <OrganizationManageHub
          slug={org.slug}
          canManage={payload.can_manage}
          recruiting={recruiting}
          onComposeAsOrg={() => {
            selectOrganization(org.id);
            navigate("/", {
              state: {
                openCompose: true,
                composeOrganization: {
                  id: org.id,
                  name: org.name,
                  slug: org.slug,
                  avatar_url: org.avatar_url,
                  is_verified: org.is_verified,
                },
              },
            });
          }}
        />

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

        <OrganizationEventSection
          slug={org.slug}
          events={events}
          loading={eventsLoading}
          error={eventsError}
          canManage={payload.can_manage}
          hydrated={!eventsLoading}
          onRetry={() => void loadEvents()}
        />

        <section className="org-profile-posts" aria-label="投稿">
          <h2 className="org-profile-posts__title">投稿</h2>
          {payload.can_manage ? (
            <div className="org-profile-posts__tabs" role="tablist" aria-label="投稿の公開状態">
              <button
                type="button"
                role="tab"
                aria-selected={postsScope === "public"}
                className={`org-profile-posts__tab${
                  postsScope === "public" ? " is-active" : ""
                }`}
                onClick={() => setPostsScope("public")}
              >
                公開
                {typeof postsMeta?.public_count === "number"
                  ? `（${postsMeta.public_count}）`
                  : ""}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={postsScope === "unpublished"}
                className={`org-profile-posts__tab${
                  postsScope === "unpublished" ? " is-active" : ""
                }`}
                onClick={() => setPostsScope("unpublished")}
              >
                下書き・非公開
                {typeof postsMeta?.unpublished_count === "number"
                  ? `（${postsMeta.unpublished_count}）`
                  : ""}
              </button>
            </div>
          ) : null}
          {postsMeta?.preview ? (
            <p className="org-profile-posts__preview" role="status">
              下書きと、公開前のまま残っている投稿です。一般のタイムラインと検索には表示されません。「公開する」で1件ずつ公開できます。
            </p>
          ) : null}
          {postsMeta?.unpublished && !payload.can_manage ? (
            <p className="org-profile-empty">投稿はまだ公開されていません。</p>
          ) : postsLoading && posts.length === 0 && !postsError ? (
            <PostCardSkeleton />
          ) : postsError && posts.length === 0 ? (
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
            <p className="org-profile-empty">
              {payload.can_manage && postsScope === "unpublished"
                ? "下書きと過去の非公開投稿はありません。"
                : payload.can_manage
                  ? "公開中の投稿はまだありません。下書きタブから公開できます。"
                  : "投稿はまだありません。"}
            </p>
          ) : (
            <div className="timeline-list org-profile-posts__list">
              {posts.map((post) => (
                <TimelinePostCard
                  key={post.id}
                  post={post}
                  authenticated={Boolean(me?.authenticated)}
                  onChange={(next) => {
                    const movedOffList =
                      (postsScope === "unpublished" &&
                        next.visibility === "public") ||
                      (postsScope === "public" &&
                        next.visibility !== "public");
                    if (movedOffList) {
                      setPosts((prev) =>
                        prev.filter((item) => item.id !== next.id)
                      );
                      setPostsMeta((prev) =>
                        prev
                          ? {
                              ...prev,
                              public_count:
                                next.visibility === "public"
                                  ? (prev.public_count ?? 0) + 1
                                  : Math.max(0, (prev.public_count ?? 1) - 1),
                              unpublished_count:
                                next.visibility === "public"
                                  ? Math.max(
                                      0,
                                      (prev.unpublished_count ?? 1) - 1
                                    )
                                  : (prev.unpublished_count ?? 0) + 1,
                            }
                          : prev
                      );
                      return;
                    }
                    setPosts((prev) =>
                      prev.map((item) => (item.id === next.id ? next : item))
                    );
                  }}
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
