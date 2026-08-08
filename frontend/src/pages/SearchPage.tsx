import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import type { TimelinePost } from "../features/timeline/api";
import {
  fetchSearchPage,
  type ProfileUser,
  type SearchTab,
} from "../features/profile/api";

const TABS: { key: SearchTab; label: string }[] = [
  { key: "all", label: "すべて" },
  { key: "latest", label: "最新" },
  { key: "users", label: "ユーザー" },
];

export function SearchPage() {
  const { me } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const qParam = searchParams.get("q") || "";
  const tab = (searchParams.get("tab") as SearchTab) || "all";

  const [qInput, setQInput] = useState(qParam);
  const [posts, setPosts] = useState<TimelinePost[]>([]);
  const [users, setUsers] = useState<ProfileUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!qParam.trim()) {
      setPosts([]);
      setUsers([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSearchPage({
        q: qParam,
        tab: tab === "latest" || tab === "users" ? tab : "all",
      });
      setPosts(data.posts || []);
      setUsers((data.users || []) as ProfileUser[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "search_failed");
    } finally {
      setLoading(false);
    }
  }, [qParam, tab]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setQInput(qParam);
  }, [qParam]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (qInput.trim()) next.set("q", qInput.trim());
    next.set("tab", tab === "latest" || tab === "users" ? tab : "all");
    setSearchParams(next);
  };

  const setTab = (nextTab: SearchTab) => {
    const next = new URLSearchParams();
    if (qParam) next.set("q", qParam);
    next.set("tab", nextTab);
    setSearchParams(next);
  };

  return (
    <div className="search-page" data-spa-page="検索">
      <div className="main-inner">
        <h1 className="search-title">検索</h1>
        <form className="search-form" onSubmit={onSearch}>
          <input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder="投稿・ユーザーを検索"
            aria-label="検索"
          />
          <button type="submit">検索</button>
        </form>

        <nav className="search-tabs" aria-label="検索タブ">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              className={`search-tab${tab === t.key ? " is-active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {!qParam ? (
          <p className="search-empty">キーワードを入力して検索してください。</p>
        ) : loading ? (
          <p className="search-empty">検索中…</p>
        ) : error ? (
          <p className="search-empty">検索に失敗しました（{error}）</p>
        ) : tab === "users" ? (
          users.length ? (
            <ul className="search-user-list">
              {users.map((u) => (
                <li key={u.id}>
                  <Link className="search-user-card" to={`/users/${u.id}/posts`}>
                    {u.avatar_url ? (
                      <img
                        className="search-user-avatar"
                        src={u.avatar_url}
                        alt=""
                      />
                    ) : (
                      <span className="search-user-avatar is-initial">
                        {u.initial}
                      </span>
                    )}
                    <span className="search-user-text">
                      <strong>{u.display_name}</strong>
                      <span>@{u.username || u.id}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="search-empty">該当するユーザーはいません。</p>
          )
        ) : posts.length ? (
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
                  navigate("/", { state: { openCompose: true } });
                }}
                onRequireLogin={() => {
                  navigate(
                    spaLoginPath(
                      `/app/search?q=${encodeURIComponent(qParam)}&tab=${tab}`
                    )
                  );
                }}
              />
            ))}
          </div>
        ) : (
          <p className="search-empty">該当する投稿はありません。</p>
        )}
      </div>
    </div>
  );
}
