import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  useNavigate,
  useParams,
} from "react-router-dom";
import { isBrowsePreview, useSession } from "../lib/session";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import type { TimelinePost } from "../features/timeline/api";
import type { ProductCard } from "../features/flea/api";
import { productDetailState } from "../features/flea/productNav";
import {
  fetchProfile,
  fetchProfileBookmarks,
  fetchProfilePosts,
  fetchProfileProducts,
  toggleBlock,
  toggleFollow,
  type ProfilePayload,
} from "../features/profile/api";
import { clearFollowListCache } from "../features/profile/followListCache";
import {
  clearOwnProfileCache,
  invalidateOwnProfileCacheAfterEdit,
  isOwnProfileCacheFresh,
  readOwnProfileCache,
  writeOwnProfileCache,
} from "../features/profile/ownProfileCache";
import { startDm } from "../features/dm/api";
import { spaLoginPath } from "../features/auth/api";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import {
  PostCardSkeleton,
  ProductGridSkeleton,
  ProfileHeaderSkeleton,
} from "../components/skeleton";
import { analytics } from "../lib/analytics/events";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";
import { MutualFriendsRow } from "../features/profile/MutualFriendsRow";
import { ProfileLinksChip } from "../features/profileLinks/ProfileLinksChip";
import { TimetablePage } from "./TimetablePage";

const TABS = [
  { key: "posts", label: "投稿" },
  { key: "timetable", label: "時間割" },
  { key: "flea", label: "フリマ" },
] as const;

type TabKey = "posts" | "timetable" | "flea" | "bookmarks";

function normalizeTab(raw: string | undefined, canBookmarks: boolean): TabKey {
  if (raw === "market") return "flea";
  if (raw === "bookmarks" && canBookmarks) return "bookmarks";
  if (raw === "timetable" || raw === "flea" || raw === "posts") return raw;
  return "posts";
}

export function ProfilePage() {
  const { userId, tab: tabParam } = useParams();
  const pk = Number(userId);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const viewerId = me?.authenticated ? me.user?.id ?? null : null;
  const pkRef = useRef(pk);
  const viewerIdRef = useRef(viewerId);
  const loadGenRef = useRef(0);
  useEffect(() => {
    pkRef.current = pk;
  }, [pk]);
  useEffect(() => {
    viewerIdRef.current = viewerId;
  }, [viewerId]);
  const [profile, setProfile] = useState<ProfilePayload | null>(null);
  const [posts, setPosts] = useState<TimelinePost[]>([]);
  const [products, setProducts] = useState<ProductCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [tabLoading, setTabLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tabError, setTabError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const tab = useMemo(
    () => normalizeTab(tabParam, Boolean(profile?.can_view_bookmarks)),
    [tabParam, profile?.can_view_bookmarks]
  );

  const loadProfile = useCallback(
    async (options: { silent?: boolean; signal?: AbortSignal } = {}) => {
      if (!Number.isFinite(pk)) {
        setError("invalid_id");
        setLoading(false);
        return;
      }
      if (!options.silent) {
        setLoading(true);
        setError(null);
      }
      const startedViewerId = viewerId;
      const requestId = nextRequestId(loadGenRef);
      try {
        const data = await fetchProfile(pk);
        if (
          options.signal?.aborted ||
          !isLatestRequest(loadGenRef, requestId) ||
          pkRef.current !== pk
        ) {
          return;
        }
        if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
        if (data.user.id !== pk) return;
        setProfile(data);
        setError(null);
        if (
          viewerIdRef.current != null &&
          data.user.id === viewerIdRef.current
        ) {
          if (data.is_own) writeOwnProfileCache(viewerIdRef.current, data);
          else clearOwnProfileCache(viewerIdRef.current);
        }
      } catch (err) {
        if (
          options.signal?.aborted ||
          !isLatestRequest(loadGenRef, requestId) ||
          pkRef.current !== pk
        ) {
          return;
        }
        if (!isSameUserScope(startedViewerId, viewerIdRef.current)) return;
        const message = err instanceof Error ? err.message : "load_failed";
        if (
          viewerId != null &&
          pk === viewerId &&
          /403|401|forbidden|unauthorized/i.test(message)
        ) {
          clearOwnProfileCache(viewerId);
        }
        if (!options.silent) {
          setProfile(null);
          setError(message);
        }
      } finally {
        if (
          !options.signal?.aborted &&
          isLatestRequest(loadGenRef, requestId) &&
          pkRef.current === pk
        ) {
          setLoading(false);
        }
      }
    },
    [pk, viewerId]
  );

  useEffect(() => {
    if (sessionLoading) return;
    if (browsePreview) {
      setLoading(false);
      setProfile(null);
      setPosts([]);
      setProducts([]);
      setError(null);
      setTabError(null);
      setMenuOpen(false);
      return;
    }
    setMenuOpen(false);
    setPosts([]);
    setProducts([]);
    setTabError(null);
    const cached =
      viewerId != null && viewerId === pk ? readOwnProfileCache(viewerId) : null;
    if (cached) {
      setProfile(cached.profile);
      setLoading(false);
      setError(null);
    } else {
      setProfile(null);
      setLoading(true);
      setError(null);
    }
    const ac = new AbortController();
    if (cached && isOwnProfileCacheFresh(cached)) {
      return () => ac.abort();
    }
    void loadProfile({ silent: Boolean(cached), signal: ac.signal });
    return () => ac.abort();
  }, [sessionLoading, browsePreview, pk, viewerId, loadProfile]);

  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      if (browsePreview || sessionLoading || !Number.isFinite(pk)) return;
      if (viewerId != null && viewerId === pk) {
        invalidateOwnProfileCacheAfterEdit(viewerId);
      }
      void loadProfile({ silent: true });
    };
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, [browsePreview, sessionLoading, pk, viewerId, loadProfile]);

  useEffect(() => {
    if (!profile) return;
    const active = normalizeTab(tabParam, profile.can_view_bookmarks);
    if (!tabParam || (tabParam === "bookmarks" && !profile.can_view_bookmarks)) {
      navigate(`/users/${pk}/${active === "posts" ? "posts" : active}`, {
        replace: true,
      });
    }
  }, [profile, tabParam, pk, navigate]);

  useEffect(() => {
    if (!profile) return;
    let cancelled = false;
    const run = async () => {
      if (!profile.can_view_content && (tab === "posts" || tab === "flea")) {
        setPosts([]);
        setProducts([]);
        setTabLoading(false);
        return;
      }
      setTabLoading(true);
      setTabError(null);
      try {
        if (tab === "posts") {
          const list = await fetchProfilePosts(pk);
          if (!cancelled) setPosts(list);
        } else if (tab === "flea") {
          const list = await fetchProfileProducts(pk);
          if (!cancelled) setProducts(list);
        } else if (tab === "bookmarks" && profile.can_view_bookmarks) {
          const list = await fetchProfileBookmarks(pk);
          if (!cancelled) setPosts(list);
        }
      } catch (err) {
        if (!cancelled) {
          setTabError(err instanceof Error ? err.message : "tab_failed");
        }
      } finally {
        if (!cancelled) setTabLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [profile, tab, pk]);

  const onFollow = async () => {
    if (!profile || !me?.authenticated) {
      navigate(spaLoginPath(`/app/users/${pk}/posts`));
      return;
    }
    if (profile.follow_state === "blocked" || profile.follow_state === "self") {
      return;
    }
    setBusy(true);
    try {
      const result = await toggleFollow(pk);
      const canView =
        profile.is_own ||
        !profile.is_private ||
        result.follow_state === "following";
      setProfile({
        ...profile,
        is_following: result.is_following,
        follow_state: result.follow_state,
        can_view_content: canView,
        stats: {
          ...profile.stats,
          follower_count: result.follower_count,
        },
      });
      if (!canView) {
        setPosts([]);
        setProducts([]);
      }
      clearFollowListCache();
      void loadProfile({ silent: true });
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "フォローに失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onBlock = async () => {
    if (!profile || !me?.authenticated) return;
    const nextBlocked = !profile.is_blocked;
    const msg = nextBlocked
      ? "このユーザーをブロックしますか？"
      : "ブロックを解除しますか？";
    if (!window.confirm(msg)) return;
    setBusy(true);
    try {
      const result = await toggleBlock(pk);
      setProfile({
        ...profile,
        is_blocked: result.is_blocked,
        is_following: result.is_blocked ? false : profile.is_following,
        follow_state: result.is_blocked ? "blocked" : "none",
        can_view_content: result.is_blocked
          ? false
          : profile.is_own || !profile.is_private,
        can_send_dm: result.is_blocked ? false : profile.can_send_dm,
      });
      if (result.is_blocked) {
        setPosts([]);
        setProducts([]);
      }
      clearFollowListCache();
      void loadProfile({ silent: true });
      setMenuOpen(false);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "ブロックに失敗しました");
    } finally {
      setBusy(false);
    }
  };

  if (!Number.isFinite(pk)) {
    return <Navigate to="/" replace />;
  }

  if (browsePreview) {
    return (
      <div className="profile-page" data-spa-page="プロフィール">
        <div className="main-inner">
          <BrowsePreviewNotice nextPath={`/app/users/${pk}`}>
            プロフィールはログイン後に表示されます。
          </BrowsePreviewNotice>
        </div>
      </div>
    );
  }

  const showProfileSkeleton =
    !browsePreview && !profile && (sessionLoading || loading) && !error;

  if (showProfileSkeleton) {
    return (
      <div className="profile-page" data-spa-page="プロフィール">
        <div className="main-inner">
          <ProfileHeaderSkeleton variant="user" />
          <ProfileTabsNav
            pk={pk}
            tab={tab}
            canViewBookmarks={false}
          />
          {tab === "flea" ? (
            <ProductGridSkeleton />
          ) : tab === "timetable" ? (
            <PostCardSkeleton count={2} />
          ) : (
            <PostCardSkeleton />
          )}
        </div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="profile-page" data-spa-page="プロフィール">
        <div className="main-inner">
          <p>プロフィールを表示できません（{error || "not_found"}）</p>
        </div>
      </div>
    );
  }

  const u = profile.user;
  const followListPath = (kind: "followers" | "following"): string | null => {
    if (!profile.can_view_content) return null;
    const dest = `/users/${pk}/${kind}`;
    if (!me?.authenticated) {
      return spaLoginPath(`/app${dest}`);
    }
    return dest;
  };

  return (
    <div className="profile-page" data-spa-page="プロフィール">
      <div className="main-inner">
        <section className="profile-card">
          <div className="profile-header">
            {u.avatar_url ? (
              <img
                className="profile-avatar user-avatar--image"
                src={u.avatar_url}
                alt=""
              />
            ) : (
              <span className="profile-avatar user-avatar--icon">{u.initial}</span>
            )}
            <div className="profile-identity">
              <h1 className="profile-name">
                <AccountDisplayName
                  name={u.display_name}
                  verified={u.is_operator_verified}
                />
              </h1>
              <p className="profile-username">@{u.username || u.id}</p>
              {profile.is_private ? (
                <p className="profile-private-badge">非公開アカウント</p>
              ) : null}
            </div>
            {profile.show_safety_menu ? (
              <div className="profile-more">
                <button
                  type="button"
                  className="profile-more__trigger"
                  aria-expanded={menuOpen}
                  aria-label="その他"
                  onClick={() => setMenuOpen((v) => !v)}
                >
                  ⋯
                </button>
                {menuOpen ? (
                  <div className="profile-more__menu" role="menu">
                    <a
                      href={`/report/user/${u.id}/`}
                      role="menuitem"
                      onClick={() => setMenuOpen(false)}
                    >
                      通報
                    </a>
                    <button
                      type="button"
                      role="menuitem"
                      disabled={busy}
                      onClick={() => void onBlock()}
                    >
                      {profile.is_blocked ? "ブロック解除" : "ブロック"}
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {u.bio ? <p className="profile-bio">{u.bio}</p> : null}
          {profile.is_own || profile.can_view_content ? (
            <ProfileLinksChip links={u.links || []} />
          ) : null}
          {u.department_grade ? (
            <p className="profile-meta">{u.department_grade}</p>
          ) : null}

          <div className="profile-stats">
            <div>
              <strong>{profile.stats.left_count}</strong>
              <span>{profile.stats.left_label}</span>
            </div>
            {followListPath("followers") ? (
              <Link
                className="profile-stats__link"
                to={followListPath("followers")!}
              >
                <strong>{profile.stats.follower_count}</strong>
                <span>フォロワー</span>
              </Link>
            ) : (
              <div>
                <strong>{profile.stats.follower_count}</strong>
                <span>フォロワー</span>
              </div>
            )}
            {followListPath("following") ? (
              <Link
                className="profile-stats__link"
                to={followListPath("following")!}
              >
                <strong>{profile.stats.following_count}</strong>
                <span>フォロー中</span>
              </Link>
            ) : (
              <div>
                <strong>{profile.stats.following_count}</strong>
                <span>フォロー中</span>
              </div>
            )}
          </div>

          {!profile.is_own && profile.can_view_content && profile.mutuals ? (
            <MutualFriendsRow userId={pk} preview={profile.mutuals} />
          ) : null}

          <div
            className={`profile-actions${
              profile.is_own
                ? " profile-actions--own"
                : !me?.authenticated
                  ? " profile-actions--guest"
                  : ""
            }`}
          >
            {profile.is_own ? (
              <Link className="btn btn-secondary" to="/settings/profile">
                プロフィールを編集
              </Link>
            ) : me?.authenticated ? (
              <>
                {profile.follow_state !== "self" ? (
                  <button
                    type="button"
                    className={`btn ${
                      profile.follow_state === "none"
                        ? "btn-primary"
                        : "btn-secondary"
                    }`}
                    disabled={
                      busy ||
                      profile.follow_state === "blocked" ||
                      profile.is_blocked
                    }
                    onClick={() => void onFollow()}
                  >
                    {profile.follow_state === "following"
                      ? "フォロー中"
                      : profile.follow_state === "requested"
                        ? "リクエスト済み"
                        : "フォロー"}
                  </button>
                ) : null}
                {profile.can_send_dm ? (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busy || profile.is_blocked}
                    onClick={() => {
                      void (async () => {
                        if (profile.dm_room_id) {
                          navigate(`/dm/${profile.dm_room_id}`);
                          return;
                        }
                        setBusy(true);
                        try {
                          const roomId = await startDm(u.id);
                          analytics.dmStarted({ created_new: true });
                          navigate(`/dm/${roomId}`);
                        } catch (err) {
                          window.alert(
                            err instanceof Error
                              ? err.message
                              : "DMを開始できませんでした"
                          );
                        } finally {
                          setBusy(false);
                        }
                      })();
                    }}
                  >
                    メッセージ
                  </button>
                ) : (
                  <span className="btn btn-secondary" style={{ opacity: 0.5 }}>
                    メッセージ不可
                  </span>
                )}
              </>
            ) : (
              <Link
                className="btn btn-primary"
                to={spaLoginPath(`/app/users/${pk}/posts`)}
              >
                ログインしてフォロー
              </Link>
            )}
          </div>
        </section>

        <ProfileTabsNav
          pk={pk}
          tab={tab}
          canViewBookmarks={profile.can_view_bookmarks}
        />

        {tabError ? (
          <p className="profile-empty">読み込みに失敗しました（{tabError}）</p>
        ) : null}

        {tabLoading &&
        (tab === "posts" || tab === "bookmarks") &&
        posts.length === 0 &&
        !tabError ? (
          <PostCardSkeleton />
        ) : null}

        {tabLoading && tab === "flea" && products.length === 0 && !tabError ? (
          <ProductGridSkeleton />
        ) : null}

        {!tabLoading &&
        !profile.can_view_content &&
        (tab === "posts" || tab === "flea") ? (
          <div className="profile-empty profile-locked">
            <p className="profile-locked__title">このアカウントは非公開です</p>
            <p>フォローすると投稿や出品を見られます。</p>
          </div>
        ) : null}

        {profile.can_view_content &&
        tab === "posts" &&
        (posts.length > 0 || !tabLoading) &&
        !tabError ? (
          posts.length ? (
            <div className="timeline-feed">
              {posts.map((post) => (
                <TimelinePostCard
                  key={post.id}
                  post={post}
                  authenticated={Boolean(me?.authenticated)}
                  onChange={(next) =>
                    setPosts((prev) =>
                      prev.map((p) => (p.id === next.id ? next : p))
                    )
                  }
                  onRemove={(id) =>
                    setPosts((prev) => prev.filter((p) => p.id !== id))
                  }
                  onQuote={() => {
                    navigate("/");
                  }}
                  onRequireLogin={() => {
                    navigate(spaLoginPath(`/app/users/${pk}/posts`));
                  }}
                />
              ))}
            </div>
          ) : (
            <p className="profile-empty">投稿はまだありません。</p>
          )
        ) : null}

        {tab === "bookmarks" &&
        (posts.length > 0 || !tabLoading) &&
        !tabError ? (
          posts.length ? (
            <div className="timeline-feed">
              {posts.map((post) => (
                <TimelinePostCard
                  key={post.id}
                  post={post}
                  authenticated={Boolean(me?.authenticated)}
                  onChange={(next) =>
                    setPosts((prev) =>
                      prev.map((p) => (p.id === next.id ? next : p))
                    )
                  }
                  onRemove={(id) =>
                    setPosts((prev) => prev.filter((p) => p.id !== id))
                  }
                  onQuote={() => navigate("/")}
                  onRequireLogin={() => {
                    navigate(spaLoginPath(`/app/users/${pk}/bookmarks`));
                  }}
                />
              ))}
            </div>
          ) : (
            <p className="profile-empty">ブックマークはまだありません。</p>
          )
        ) : null}

        {profile.can_view_content &&
        tab === "flea" &&
        (products.length > 0 || !tabLoading) &&
        !tabError ? (
          products.length ? (
            <div className="product-grid profile-product-grid">
              {products.map((p) => (
                <Link
                  key={p.id}
                  className="product-card"
                  to={`/flea/products/${p.id}`}
                  state={productDetailState(p)}
                >
                  <div className="product-card-media">
                    {p.image_url ? (
                      <img src={p.image_url} alt={p.name} loading="lazy" />
                    ) : (
                      <span className="product-card-placeholder">No Image</span>
                    )}
                    <p className="product-price-badge">¥{p.price}</p>
                  </div>
                  <p className="product-card-title">{p.name}</p>
                </Link>
              ))}
            </div>
          ) : (
            <p className="profile-empty">出品中の商品はありません。</p>
          )
        ) : null}

        {tab === "timetable" ? (
          profile.can_view_timetable ? (
            <ProfileTimetableEmbed userPk={pk} />
          ) : (
            <p className="profile-empty">このユーザーの時間割は非公開です。</p>
          )
        ) : null}
      </div>
    </div>
  );
}

function ProfileTabsNav({
  pk,
  tab,
  canViewBookmarks,
}: {
  pk: number;
  tab: TabKey;
  canViewBookmarks: boolean;
}) {
  return (
    <nav className="profile-tabs" aria-label="プロフィールタブ">
      {TABS.map((t) => (
        <NavLink
          key={t.key}
          to={`/users/${pk}/${t.key}`}
          className={({ isActive }) =>
            `profile-tab${isActive || (t.key === "posts" && tab === "posts") ? " is-active" : ""}`
          }
        >
          {t.label}
        </NavLink>
      ))}
      {canViewBookmarks ? (
        <NavLink
          to={`/users/${pk}/bookmarks`}
          className={({ isActive }) =>
            `profile-tab${isActive ? " is-active" : ""}`
          }
        >
          ブックマーク
        </NavLink>
      ) : null}
    </nav>
  );
}

function ProfileTimetableEmbed({ userPk }: { userPk: number }) {
  return (
    <div className="profile-timetable-embed">
      <TimetablePage key={userPk} overrideUserPk={userPk} embedded />
    </div>
  );
}
