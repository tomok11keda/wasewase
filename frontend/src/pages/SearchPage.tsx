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
  type SearchOfferingResult,
  type SearchProductResult,
  type SearchResultRow,
  type SearchTab,
  type SearchThreadResult,
} from "../features/profile/api";
import {
  DiscoverPostCard,
  DiscoverThreadCard,
} from "../features/search/DiscoverCompactCards";
import { DiscoverSection } from "../features/search/DiscoverSection";
import {
  DiscoverTrendingMosaic,
  splitTrendingForMosaic,
} from "../features/search/DiscoverTrendingMosaic";
import { useSoftTabRefetch } from "../layouts/TabKeepAliveLayout";
import { analytics } from "../lib/analytics";

const TABS: { key: SearchTab; label: string }[] = [
  { key: "all", label: "おすすめ" },
  { key: "latest", label: "最新" },
  { key: "courses", label: "授業" },
  { key: "users", label: "ユーザー" },
  { key: "products", label: "商品" },
];

const DISCOVER_PREVIEW = {
  trendingPosts: 4,
  trendingProducts: 5,
  faculty: 4,
  communities: 4,
  products: 8,
} as const;

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

function SearchUserCard({ user }: { user: ProfileUser }) {
  return (
    <Link className="search-user-card" to={`/users/${user.id}/posts`}>
      {user.avatar_url ? (
        <img className="search-user-avatar" src={user.avatar_url} alt="" />
      ) : (
        <span className="search-user-avatar is-initial">{user.initial}</span>
      )}
      <span className="search-user-text">
        <strong>{user.display_name}</strong>
        <span>@{user.username || user.id}</span>
      </span>
    </Link>
  );
}

function SearchOfferingCard({ offering }: { offering: SearchOfferingResult }) {
  const schedule = `${offering.day_label}${offering.period_label}`;
  const rating =
    offering.review_overall != null
      ? `⭐${offering.review_overall.toFixed(1)}`
      : "⭐—";
  const reviewCount = offering.review_count ?? 0;
  return (
    <Link
      className="search-offering-card"
      to={`/courses/${offering.id}`}
    >
      <p className="search-offering-card__meta">
        <span className="search-offering-card__badge">授業</span>
        {offering.semester_label}
        {offering.school ? ` · ${offering.school}` : ""}
      </p>
      <strong className="search-offering-card__title">{offering.title}</strong>
      <p className="search-offering-card__sub">
        {offering.instructor}
        {` · ${schedule}`}
      </p>
      <p className="search-offering-card__foot">
        {rating}
        {` · レビュー${reviewCount}件`}
        {` · 履修中${offering.enrollment_count}人`}
      </p>
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

function renderSearchResultRow(row: SearchResultRow, handlers: ResultHandlers) {
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
  if (row.kind === "user") {
    return (
      <div key={`user-${row.user.id}`} className="search-mixed-user">
        <SearchUserCard user={row.user} />
      </div>
    );
  }
  if (row.kind === "offering") {
    return (
      <SearchOfferingCard
        key={`offering-${row.offering.id}`}
        offering={row.offering}
      />
    );
  }
  return (
    <SearchProductCard
      key={`product-${row.product.id}`}
      product={row.product}
    />
  );
}

function renderDiscoverRow(row: SearchResultRow) {
  if (row.kind === "post") {
    return <DiscoverPostCard key={`d-post-${row.post.id}`} post={row.post} />;
  }
  if (row.kind === "thread") {
    return (
      <DiscoverThreadCard key={`d-thread-${row.thread.id}`} thread={row.thread} />
    );
  }
  return null;
}

function SearchDiscoverView({
  discover,
}: {
  discover: SearchDiscoverPayload;
}) {
  const [trendingExpanded, setTrendingExpanded] = useState(false);
  const [facultyExpanded, setFacultyExpanded] = useState(false);
  const [communitiesExpanded, setCommunitiesExpanded] = useState(false);
  const [productsExpanded, setProductsExpanded] = useState(false);

  useEffect(() => {
    setTrendingExpanded(false);
    setFacultyExpanded(false);
    setCommunitiesExpanded(false);
    setProductsExpanded(false);
  }, [discover]);

  const mosaic = splitTrendingForMosaic(
    discover.trending,
    discover.products
  );
  const mosaicPosts = trendingExpanded
    ? mosaic.posts
    : mosaic.posts.slice(0, DISCOVER_PREVIEW.trendingPosts);
  const mosaicProducts = trendingExpanded
    ? mosaic.products.slice(0, DISCOVER_PREVIEW.trendingProducts + 3)
    : mosaic.products.slice(0, DISCOVER_PREVIEW.trendingProducts);
  const mosaicVisibleCount = mosaicPosts.length + mosaicProducts.length;
  const mosaicTotalCount =
    mosaic.posts.length +
    Math.min(
      mosaic.products.length,
      DISCOVER_PREVIEW.trendingProducts + 3
    );
  const facultyResults = discover.faculty?.results || [];
  const facultyVisible = facultyExpanded
    ? facultyResults
    : facultyResults.slice(0, DISCOVER_PREVIEW.faculty);
  const communities = discover.communities || [];
  const communitiesVisible = communitiesExpanded
    ? communities
    : communities.slice(0, DISCOVER_PREVIEW.communities);
  const productsVisible = productsExpanded
    ? discover.products
    : discover.products.slice(0, DISCOVER_PREVIEW.products);

  const facultyParam = discover.faculty?.faculty
    ? `?tag=${encodeURIComponent(discover.faculty.faculty)}`
    : "";

  const showTrending =
    mosaic.posts.length > 0 || mosaic.products.length > 0;

  return (
    <div className="search-discover">
      {showTrending ? (
        <DiscoverSection
          title="🔥 今わせわせで話題"
          visibleCount={mosaicVisibleCount}
          totalCount={mosaicTotalCount}
          expanded={trendingExpanded}
          onExpand={() => setTrendingExpanded(true)}
        >
          <DiscoverTrendingMosaic
            posts={mosaicPosts}
            products={mosaicProducts}
          />
        </DiscoverSection>
      ) : null}

      {discover.faculty && facultyResults.length > 0 ? (
        <DiscoverSection
          title={`🏫 ${discover.faculty.title}`}
          visibleCount={facultyVisible.length}
          totalCount={facultyResults.length}
          expanded={facultyExpanded}
          onExpand={() => setFacultyExpanded(true)}
          moreTo={`/communities${facultyParam}`}
          moreLabel="コミュニティをもっと見る"
        >
          <div className="discover-compact-list">
            {facultyVisible.map((row) => renderDiscoverRow(row))}
          </div>
        </DiscoverSection>
      ) : null}

      {communities.length > 0 ? (
        <DiscoverSection
          title="💬 コミュニティで話題"
          visibleCount={communitiesVisible.length}
          totalCount={communities.length}
          expanded={communitiesExpanded}
          onExpand={() => setCommunitiesExpanded(true)}
          moreTo="/communities"
          moreLabel="コミュニティをもっと見る"
        >
          <div className="discover-compact-list">
            {communitiesVisible.map((row) => renderDiscoverRow(row))}
          </div>
        </DiscoverSection>
      ) : null}

      {discover.products.length > 0 ? (
        <DiscoverSection
          title="🛍 フリマで注目"
          visibleCount={productsVisible.length}
          totalCount={discover.products.length}
          expanded={productsExpanded}
          onExpand={() => setProductsExpanded(true)}
          moreTo="/flea"
          moreLabel="フリマをもっと見る"
        >
          <div className="search-product-rail">
            {productsVisible.map((product) => (
              <SearchProductCard
                key={product.id}
                product={product}
                compact
              />
            ))}
          </div>
        </DiscoverSection>
      ) : null}
    </div>
  );
}

export function SearchPage() {
  const { me } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const qParam = searchParams.get("q") || "";
  const tab = (searchParams.get("tab") as SearchTab) || "all";
  const activeTab: SearchTab =
    tab === "latest" ||
    tab === "courses" ||
    tab === "users" ||
    tab === "products"
      ? tab
      : "all";

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
        const resultCount =
          typeof data.result_count === "number"
            ? data.result_count
            : activeTab === "users"
              ? (data.users || []).length
              : (data.results || []).length;
        analytics.searchPerformed({
          query: qParam.trim(),
          tab: activeTab,
          result_count: resultCount,
        });
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
        : activeTab === "courses"
          ? "該当する授業が見つかりません。"
          : "一致する結果はありません。";

  const showDiscover = !qParam.trim();
  const hasDiscoverContent = Boolean(
    discover &&
      (discover.trending.length > 0 ||
        (discover.faculty && discover.faculty.results.length > 0) ||
        (discover.communities && discover.communities.length > 0) ||
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
          />
          <button type="submit">検索</button>
        </form>

        {!showDiscover ? (
          <nav className="search-tabs" aria-label="検索結果の切り替え">
            <div className="search-tabs__scroller">
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
            </div>
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
            <SearchDiscoverView discover={discover} />
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
                  <SearchUserCard user={u} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="search-empty">{emptyMessage}</p>
          )
        ) : results.length ? (
          <div className="search-mixed-feed">
            {results.map((row) => renderSearchResultRow(row, handlers))}
          </div>
        ) : (
          <p className="search-empty">{emptyMessage}</p>
        )}
      </div>
    </div>
  );
}
