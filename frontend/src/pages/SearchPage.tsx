import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import type { TimelinePost } from "../features/timeline/api";
import {
  fetchSearchPage,
  type ProfileUser,
  type SearchResultRow,
  type SearchTab,
  type SearchThreadResult,
} from "../features/profile/api";
import { useSoftTabRefetch } from "../layouts/TabKeepAliveLayout";

const TABS: { key: SearchTab; label: string }[] = [
  { key: "all", label: "おすすめ" },
  { key: "latest", label: "最新" },
  { key: "users", label: "ユーザー" },
];

function SearchThreadCard({ thread }: { thread: SearchThreadResult }) {
  const authorName = thread.author?.display_name || "ユーザー";
  const handle = thread.author?.username ? `@${thread.author.username}` : "";
  return (
    <Link
      className="search-thread-card"
      to={`/communities/${thread.community.slug}/threads/${thread.id}`}
    >
      <p className="search-thread-card__meta">
        <span className="search-thread-card__badge">コミュニティ</span>
        {thread.community.name}
        {thread.community.faculty ? ` · ${thread.community.faculty}` : ""}
      </p>
      <strong className="search-thread-card__title">{thread.title}</strong>
      <p className="search-thread-card__preview">
        {thread.body_preview || thread.body}
      </p>
      <p className="search-thread-card__foot">
        {authorName}
        {handle ? ` ${handle}` : ""}
        {` · 返信 ${thread.replies_count}`}
      </p>
    </Link>
  );
}

export function SearchPage() {
  const { me } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const qParam = searchParams.get("q") || "";
  const tab = (searchParams.get("tab") as SearchTab) || "all";
  const activeTab: SearchTab =
    tab === "latest" || tab === "users" ? tab : "all";

  const [qInput, setQInput] = useState(qParam);
  const [results, setResults] = useState<SearchResultRow[]>([]);
  const [users, setUsers] = useState<ProfileUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!qParam.trim()) {
      setResults([]);
      setUsers([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSearchPage({
        q: qParam,
        tab: activeTab,
      });
      setResults(data.results || []);
      setUsers((data.users || []) as ProfileUser[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "search_failed");
    } finally {
      setLoading(false);
    }
  }, [qParam, activeTab]);

  useEffect(() => {
    void load();
  }, [load]);

  useSoftTabRefetch("search", () => load());

  useEffect(() => {
    setQInput(qParam);
  }, [qParam]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (qInput.trim()) next.set("q", qInput.trim());
    next.set("tab", activeTab);
    setSearchParams(next);
  };

  const setTab = (nextTab: SearchTab) => {
    const next = new URLSearchParams();
    if (qParam) next.set("q", qParam);
    next.set("tab", nextTab);
    setSearchParams(next);
  };

  const updatePostInResults = (nextPost: TimelinePost) => {
    setResults((prev) =>
      prev.map((row) =>
        row.kind === "post" && row.post.id === nextPost.id
          ? { ...row, post: nextPost }
          : row
      )
    );
  };

  const removePostFromResults = (id: number) => {
    setResults((prev) =>
      prev.filter((row) => !(row.kind === "post" && row.post.id === id))
    );
  };

  return (
    <div className="search-page" data-spa-page="検索">
      <div className="main-inner">
        <h1 className="search-title">検索</h1>
        <p className="search-lead">
          わせわせ全体から、タイムライン・コミュニティ・ユーザーを横断検索します。
        </p>
        <form className="search-form" onSubmit={onSearch} role="search">
          <input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder="例: ゼミ、履修、サークル"
            aria-label="全体検索"
            autoFocus
          />
          <button type="submit">検索</button>
        </form>

        <nav className="search-tabs" aria-label="検索タブ">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              className={`search-tab${activeTab === t.key ? " is-active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {qParam ? (
          <p className="search-query-label">
            「{qParam}」の検索結果
            {activeTab === "all"
              ? " · おすすめ"
              : activeTab === "latest"
                ? " · 最新"
                : " · ユーザー"}
          </p>
        ) : null}

        {!qParam ? (
          <p className="search-empty">
            キーワードを入力すると、タイムラインとコミュニティを横断検索できます。ユーザーは
            「ユーザー」タブから探せます。
          </p>
        ) : loading ? (
          <p className="search-empty">検索中…</p>
        ) : error ? (
          <p className="search-empty">検索に失敗しました（{error}）</p>
        ) : activeTab === "users" ? (
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
            <p className="search-empty">一致するユーザーはいません。</p>
          )
        ) : results.length ? (
          <div className="search-mixed-feed">
            {results.map((row) =>
              row.kind === "post" ? (
                <TimelinePostCard
                  key={`post-${row.post.id}`}
                  post={row.post}
                  authenticated={Boolean(me?.authenticated)}
                  onChange={updatePostInResults}
                  onRemove={removePostFromResults}
                  onQuote={() => {
                    navigate("/", { state: { openCompose: true } });
                  }}
                  onRequireLogin={() => {
                    navigate(
                      spaLoginPath(
                        `/app/search?q=${encodeURIComponent(qParam)}&tab=${activeTab}`
                      )
                    );
                  }}
                />
              ) : (
                <SearchThreadCard
                  key={`thread-${row.thread.id}`}
                  thread={row.thread}
                />
              )
            )}
          </div>
        ) : (
          <p className="search-empty">一致する投稿はありません。</p>
        )}
      </div>
    </div>
  );
}
