import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  useNavigate,
  useParams,
} from "react-router-dom";
import { useSession } from "../lib/session";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import type { TimelinePost } from "../features/timeline/api";
import type { ProductCard } from "../features/flea/api";
import {
  fetchProfile,
  fetchProfileBookmarks,
  fetchProfilePosts,
  fetchProfileProducts,
  toggleBlock,
  toggleFollow,
  type ProfilePayload,
} from "../features/profile/api";
import { startDm } from "../features/dm/api";
import { spaLoginPath } from "../features/auth/api";
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
  const { me } = useSession();
  const [profile, setProfile] = useState<ProfilePayload | null>(null);
  const [posts, setPosts] = useState<TimelinePost[]>([]);
  const [products, setProducts] = useState<ProductCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [tabLoading, setTabLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const tab = useMemo(
    () => normalizeTab(tabParam, Boolean(profile?.can_view_bookmarks)),
    [tabParam, profile?.can_view_bookmarks]
  );

  const loadProfile = useCallback(async () => {
    if (!Number.isFinite(pk)) {
      setError("invalid_id");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchProfile(pk);
      setProfile(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load_failed");
    } finally {
      setLoading(false);
    }
  }, [pk]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

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
          setError(err instanceof Error ? err.message : "tab_failed");
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

  if (loading) {
    return (
      <div className="profile-page" data-spa-page="プロフィール">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="profile-page" data-spa-page="プロフィール">
        <div className="main-inner">
          <Link className="profile-back" to="/">
            ← ホームへ戻る
          </Link>
          <p>プロフィールを表示できません（{error || "not_found"}）</p>
        </div>
      </div>
    );
  }

  const u = profile.user;

  return (
    <div className="profile-page" data-spa-page="プロフィール">
      <div className="main-inner">
        <Link className="profile-back" to="/" onClick={() => {}}>
          ← 戻る
        </Link>

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
              <h1 className="profile-name">{u.display_name}</h1>
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
          {u.department_grade ? (
            <p className="profile-meta">{u.department_grade}</p>
          ) : null}

          <div className="profile-stats">
            <div>
              <strong>{profile.stats.left_count}</strong>
              <span>{profile.stats.left_label}</span>
            </div>
            <div>
              <strong>{profile.stats.follower_count}</strong>
              <span>フォロワー</span>
            </div>
            <div>
              <strong>{profile.stats.following_count}</strong>
              <span>フォロー中</span>
            </div>
          </div>

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
              <a
                className="btn btn-secondary"
                href={`/mypage/edit/?next=${encodeURIComponent(
                  `/app/users/${u.id}/posts`
                )}`}
                title="プロフィール編集は従来ページで行います"
              >
                プロフィールを編集
              </a>
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
          {profile.can_view_bookmarks ? (
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

        {tabLoading ? <p className="profile-empty">読み込み中…</p> : null}

        {!tabLoading &&
        !profile.can_view_content &&
        (tab === "posts" || tab === "flea") ? (
          <div className="profile-empty profile-locked">
            <p className="profile-locked__title">このアカウントは非公開です</p>
            <p>フォローすると投稿や出品を見られます。</p>
          </div>
        ) : null}

        {!tabLoading && profile.can_view_content && tab === "posts" ? (
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

        {!tabLoading && tab === "bookmarks" ? (
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

        {!tabLoading && profile.can_view_content && tab === "flea" ? (
          products.length ? (
            <div className="product-grid profile-product-grid">
              {products.map((p) => (
                <Link
                  key={p.id}
                  className="product-card"
                  to={`/flea/products/${p.id}`}
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

function ProfileTimetableEmbed({ userPk }: { userPk: number }) {
  return (
    <div className="profile-timetable-embed">
      <TimetablePage overrideUserPk={userPk} embedded />
    </div>
  );
}
