import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import { TimelinePostCard } from "../features/timeline/TimelinePostCard";
import type { TimelinePost } from "../features/timeline/api";
import {
  fetchSearchPage,
  type ProfileUser,
  type SearchDiscoverPayload,
  type SearchProductResult,
  type SearchResultRow,
  type SearchTab,
  type SearchThreadResult,
} from "../features/profile/api";
import { useSoftTabRefetch } from "../layouts/TabKeepAliveLayout";

const TABS: { key: SearchTab; label: string }[] = [
  { key: "all", label: "おすすめ" },
  { key: "latest", label: "最新" },
  { key: "users", label: "ユーザー" },
  { key: "products", label: "商品" },
];

function tabLabel(tab: SearchTab): string {
  return TABS.find((t) => t.key === tab)?.label || "おすすめ";
}

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

function SearchProductCard({
  product,
  compact = false,
}: {
  product: SearchProductResult;
  compact?: boolean;
}) {
  const sellerName = product.seller?.display_name || "出品者";
  return (
    <Link
      className={`search-product-card${compact ? " search-product-card--rail" : ""}`}
      to={`/flea/products/${product.id}`}
    >
      <div className="search-product-card__media">
        {product.image_url ? (
          <img src={product.image_url} alt="" loading="lazy" />
        ) : (
          <span className="search-product-card__placeholder">No Image</span>
        )}
        {product.is_sold || product.is_pending ? (
          <span className="search-product-card__mask" aria-hidden="true" />
        ) : null}
      </div>
      <div className="search-product-card__body">
        <p className="search-product-card__meta">
          {!compact ? (
            <span className="search-product-card__badge">フリマ</span>
          ) : null}
          {product.is_sold
            ? "売り切れ"
            : product.is_pending
              ? "取引中"
              : `¥${product.price.toLocaleString()}`}
        </p>
        <strong className="search-product-card__title">{product.name}</strong>
        {!compact ? (
          <p className="search-product-card__foot">
            {sellerName}
            {product.created_at_label ? ` · ${product.created_at_label}` : ""}
            {product.handover_campus_label
              ? ` · ${product.handover_campus_label}`
              : ""}
          </p>
        ) : null}
      </div>
    </Link>
  );
}

type ResultHandlers = {
  authenticated: boolean;
  qParam: string;
  activeTab: SearchTab;
  onChangePost: (post: TimelinePost) => void;
  onRemovePost: (id: number) => void;
  onQuote: () => void;
  onRequireLogin: () => void;
};

function renderResultRow(row: SearchResultRow, handlers: ResultHandlers) {
  if (row.kind === "post") {
    return (
      <TimelinePostCard
        key={`post-${row.post.id}`}
        post={row.post}
        authenticated={handlers.authenticated}
        onChange={handlers.onChangePost}
        onRemove={handlers.onRemovePost}
        onQuote={handlers.onQuote}
        onRequireLogin={handlers.onRequireLogin}
      />
    );
  }
  if (row.kind === "thread") {
    return (
      <SearchThreadCard key={`thread-${row.thread.id}`} thread={row.thread} />
    );
  }
  return (
    <SearchProductCard
      key={`product-${row.product.id}`}
      product={row.product}
    />
  );
}

export function SearchPage() {
  const { me } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const qParam = searchParams.get("q") || "";
  const tab = (searchParams.get("tab") as SearchTab) || "all";
  const activeTab: SearchTab =
    tab === "latest" || tab === "users" || tab === "products" ? tab : "all";

  const [qInput, setQInput] = useState(qParam);
  const [results, setResults] = useState<SearchResultRow[]>([]);
  const [users, setUsers] = useState<ProfileUser[]>([]);
  const [discover, setDiscover] = useState<SearchDiscoverPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSearchPage({
        q: qParam || undefined,
        tab: qParam ? activeTab : undefined,
      });
      if (!qParam.trim()) {
        setResults([]);
        setUsers([]);
        setDiscover(data.discover || null);
      } else {
        setDiscover(null);
        setResults(data.results || []);
        setUsers((data.users || []) as ProfileUser[]);
      }
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
    next.set("tab", activeTab === "all" ? "all" : activeTab);
    setSearchParams(next);
  };

  const setTab = (nextTab: SearchTab) => {
    const next = new URLSearchParams();
    if (qParam) next.set("q", qParam);
    next.set("tab", nextTab);
    setSearchParams(next);
  };

  const updatePostInResults = (nextPost: TimelinePost) => {
    const patch = (rows: SearchResultRow[]) =>
      rows.map((row) =>
        row.kind === "post" && row.post.id === nextPost.id
          ? { ...row, post: nextPost }
          : row
      );
    setResults((prev) => patch(prev));
    setDiscover((prev) =>
      prev
        ? {
            ...prev,
            trending: patch(prev.trending),
            faculty: prev.faculty
              ? { ...prev.faculty, results: patch(prev.faculty.results) }
              : null,
          }
        : prev
    );
  };

  const removePostFromResults = (id: number) => {
    const drop = (rows: SearchResultRow[]) =>
      rows.filter((row) => !(row.kind === "post" && row.post.id === id));
    setResults((prev) => drop(prev));
    setDiscover((prev) =>
      prev
        ? {
            ...prev,
            trending: drop(prev.trending),
            faculty: prev.faculty
              ? { ...prev.faculty, results: drop(prev.faculty.results) }
              : null,
          }
        : prev
    );
  };

  const handlers: ResultHandlers = {
    authenticated: Boolean(me?.authenticated),
    qParam,
    activeTab,
    onChangePost: updatePostInResults,
    onRemovePost: removePostFromResults,
    onQuote: () => navigate("/", { state: { openCompose: true } }),
    onRequireLogin: () =>
      navigate(
        spaLoginPath(
          qParam
            ? `/app/search?q=${encodeURIComponent(qParam)}&tab=${activeTab}`
            : "/app/search"
        )
      ),
  };

  const emptyMessage =
    activeTab === "users"
      ? "一致するユーザーはいません。"
      : activeTab === "products"
        ? "一致する商品はありません。"
        : "一致する結果はありません。";

  const showDiscover = !qParam.trim();
  const hasDiscoverContent = Boolean(
    discover &&
      (discover.trending.length > 0 ||
        (discover.faculty && discover.faculty.results.length > 0) ||
        discover.products.length > 0)
  );

  return (
    <div className="search-page" data-spa-page="検索">
      <div className="main-inner">
        <h1 className="search-title">検索</h1>
        <p className="search-lead">
          わせわせ全体から探したり、話題の投稿や商品を見つけられます。
        </p>
        <form className="search-form" onSubmit={onSearch} role="search">
          <input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder="ゼミ、教科書、先生などを検索"
            aria-label="わせわせ全体検索"
            autoFocus
          />
          <button type="submit">検索</button>
        </form>

        {!showDiscover ? (
          <nav className="search-tabs" aria-label="検索結果の切り替え">
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
        ) : null}

        {qParam ? (
          <p className="search-query-label">
            「{qParam}」の検索結果 · {tabLabel(activeTab)}
          </p>
        ) : null}

        {loading ? (
          <p className="search-empty">
            {showDiscover ? "読み込み中…" : "検索中…"}
          </p>
        ) : error ? (
          <p className="search-empty">
            {showDiscover
              ? `読み込みに失敗しました（${error}）`
              : `検索に失敗しました（${error}）`}
          </p>
        ) : showDiscover ? (
          hasDiscoverContent && discover ? (
            <div className="search-discover">
              {discover.trending.length > 0 ? (
                <section className="search-discover__section">
                  <h2 className="search-discover__title">🔥 今わせわせで話題</h2>
                  <div className="search-mixed-feed">
                    {discover.trending.map((row) =>
                      renderResultRow(row, handlers)
                    )}
                  </div>
                </section>
              ) : null}

              {discover.faculty && discover.faculty.results.length > 0 ? (
                <section className="search-discover__section">
                  <h2 className="search-discover__title">
                    🏫 {discover.faculty.title}
                  </h2>
                  <div className="search-mixed-feed">
                    {discover.faculty.results.map((row) =>
                      renderResultRow(row, handlers)
                    )}
                  </div>
                </section>
              ) : null}

              {discover.products.length > 0 ? (
                <section className="search-discover__section">
                  <h2 className="search-discover__title">🛍 フリマで注目</h2>
                  <div className="search-product-rail">
                    {discover.products.map((product) => (
                      <SearchProductCard
                        key={product.id}
                        product={product}
                        compact
                      />
                    ))}
                  </div>
                </section>
              ) : null}
            </div>
          ) : (
            <p className="search-empty">
              キーワードを入力すると、わせわせ全体を横断検索できます。
            </p>
          )
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
            <p className="search-empty">{emptyMessage}</p>
          )
        ) : results.length ? (
          <div className="search-mixed-feed">
            {results.map((row) => renderResultRow(row, handlers))}
          </div>
        ) : (
          <p className="search-empty">{emptyMessage}</p>
        )}
      </div>
    </div>
  );
}
