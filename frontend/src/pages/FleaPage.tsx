import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import {
  fetchFleaList,
  type FilterTab,
  type ProductCard,
} from "../features/flea/api";
import { spaLoginPath } from "../features/auth/api";

function ProductGridCard({ product }: { product: ProductCard }) {
  const sellerName = product.seller?.display_name || "出品者";
  return (
    <Link className="product-card" to={`/flea/products/${product.id}`}>
      <div className="product-card-media">
        {product.image_url ? (
          <img src={product.image_url} alt={product.name} loading="lazy" />
        ) : (
          <span className="product-card-placeholder">No Image</span>
        )}
        {(product.is_sold || product.is_pending) && (
          <span className="product-card-mask" aria-hidden="true" />
        )}
        {product.is_sold ? (
          <p className="product-status-label">SOLD OUT</p>
        ) : product.is_pending ? (
          <p className="product-status-label">取引中</p>
        ) : (
          <p className="product-price-badge">¥{product.price}</p>
        )}
      </div>
      <p className="product-card-title">{product.name}</p>
      <p className="product-card-meta">
        {sellerName} · {product.created_at_label}
        {product.handover_campus_label
          ? ` · ${product.handover_campus_label}`
          : ""}
      </p>
    </Link>
  );
}

export function FleaPage() {
  const { me } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const feed = searchParams.get("feed") || "all";
  const qParam = searchParams.get("q") || "";
  const faculty = searchParams.get("faculty") || "";
  const campus = searchParams.get("campus") || "";
  const order = searchParams.get("order") || "";

  const [products, setProducts] = useState<ProductCard[]>([]);
  const [facultyTabs, setFacultyTabs] = useState<FilterTab[]>([]);
  const [campusTabs, setCampusTabs] = useState<FilterTab[]>([]);
  const [orderOptions, setOrderOptions] = useState<FilterTab[]>([]);
  const [userFaculty, setUserFaculty] = useState("");
  const [campusLabel, setCampusLabel] = useState("");
  const [followingUnauth, setFollowingUnauth] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [qInput, setQInput] = useState(qParam);
  const exhibitSuccess = searchParams.get("exhibit_success") === "1";

  const patchParams = useCallback(
    (patch: Record<string, string>) => {
      const next = new URLSearchParams(searchParams);
      Object.entries(patch).forEach(([key, value]) => {
        if (value) next.set(key, value);
        else next.delete(key);
      });
      setSearchParams(next);
    },
    [searchParams, setSearchParams]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFleaList({
        feed: feed || undefined,
        q: qParam || undefined,
        faculty: faculty || undefined,
        campus: campus || undefined,
        order: order || undefined,
      });
      setProducts(data.products);
      setFacultyTabs(data.faculty_tabs);
      setCampusTabs(data.campus_tabs);
      setOrderOptions(data.order_options);
      setUserFaculty(data.user_faculty);
      setCampusLabel(data.campus_label);
      setFollowingUnauth(data.feed_following_unauthenticated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load_failed");
    } finally {
      setLoading(false);
    }
  }, [feed, qParam, faculty, campus, order]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setQInput(qParam);
  }, [qParam]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    patchParams({ q: qInput.trim() });
  };

  return (
    <div className="flea-page" data-spa-page="フリマ">
      {exhibitSuccess ? (
        <ul className="messages">
          <li className="success">商品を出品しました。</li>
        </ul>
      ) : null}

      <section className="faculty-filter-section" aria-label="学部フィルター">
        <div className="faculty-tabs">
          {facultyTabs.map((tab) => (
            <button
              key={tab.value || "all"}
              type="button"
              className={`faculty-tab${faculty === tab.value ? " is-active" : ""}`}
              onClick={() => patchParams({ faculty: tab.value })}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      <section className="campus-filter-section" aria-label="キャンパスフィルター">
        <p className="campus-filter-label">受け渡しキャンパス</p>
        <div className="faculty-tabs">
          {campusTabs.map((tab) => (
            <button
              key={tab.value || "all-campus"}
              type="button"
              className={`faculty-tab${campus === tab.value ? " is-active" : ""}`}
              onClick={() => patchParams({ campus: tab.value })}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      <main className="main-inner">
        <nav className="feed-scope-tabs" aria-label="フリマ表示範囲">
          <button
            type="button"
            className={`feed-scope-tab${feed !== "following" ? " is-active" : ""}`}
            onClick={() => patchParams({ feed: "all" })}
          >
            全体
          </button>
          <button
            type="button"
            className={`feed-scope-tab${feed === "following" ? " is-active" : ""}`}
            onClick={() => patchParams({ feed: "following" })}
          >
            フォロー中
          </button>
        </nav>

        {followingUnauth ? (
          <p className="feed-scope-hint">
            フォロー中の出品を見るには
            <Link to={spaLoginPath("/app/flea?feed=following")}>
              ログイン
            </Link>
            してください。
          </p>
        ) : userFaculty &&
          !qParam &&
          feed !== "following" &&
          !faculty &&
          !campus &&
          !order ? (
          <p className="faculty-hint">
            📍 {userFaculty}の出品を優先表示しています
          </p>
        ) : faculty || campus ? (
          <p className="faculty-hint">
            🏷 {faculty}
            {faculty && campus ? " · " : ""}
            {campus ? campusLabel : ""}で絞り込み中
          </p>
        ) : null}

        <div className="flea-toolbar">
          <form className="flea-search-form" onSubmit={onSearch}>
            <input
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="商品名・教科書名で検索"
              aria-label="商品検索"
            />
            <button type="submit">検索</button>
          </form>
          {me?.authenticated ? (
            <Link className="btn-exhibit" to="/flea/exhibit">
              出品
            </Link>
          ) : (
            <Link className="btn-exhibit" to={spaLoginPath("/app/flea/exhibit")}>
              出品
            </Link>
          )}
        </div>

        <div className="flea-sort-bar" aria-label="並び替え">
          <span className="flea-sort-bar__label">並び替え</span>
          <div className="flea-sort-options">
            {orderOptions.map((opt) => (
              <button
                key={opt.value || "recommend"}
                type="button"
                className={`flea-sort-option${order === opt.value ? " is-active" : ""}`}
                onClick={() => patchParams({ order: opt.value })}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <h2 className="section-title">
          {qParam ? `「${qParam}」の検索結果` : "おすすめ商品"}
        </h2>

        {loading ? (
          <p className="empty-message">読み込み中…</p>
        ) : error ? (
          <p className="empty-message">読み込みに失敗しました（{error}）</p>
        ) : products.length ? (
          <div className="product-grid">
            {products.map((p) => (
              <ProductGridCard key={p.id} product={p} />
            ))}
          </div>
        ) : (
          <p className="empty-message">
            {qParam
              ? "該当する商品はありません。"
              : feed === "following"
                ? "フォロー中のユーザーの出品はまだありません。"
                : "出品されている商品はまだありません。"}
          </p>
        )}
      </main>
    </div>
  );
}
