import type { SearchProductResult, SearchResultRow } from "../profile/api";
import {
  DiscoverPostCard,
  DiscoverProductCard,
  DiscoverThreadCard,
} from "./DiscoverCompactCards";

export type TrendingMosaicSplit = {
  posts: SearchResultRow[];
  products: SearchProductResult[];
};

/** Split mixed trending rows into text column + product column (layout only). */
export function splitTrendingForMosaic(
  trending: SearchResultRow[],
  railProducts: SearchProductResult[]
): TrendingMosaicSplit {
  const posts: SearchResultRow[] = [];
  const fromTrending: SearchProductResult[] = [];
  const seen = new Set<number>();

  for (const row of trending) {
    if (row.kind === "post" || row.kind === "thread") {
      posts.push(row);
      continue;
    }
    if (row.kind === "product" && !seen.has(row.product.id)) {
      seen.add(row.product.id);
      fromTrending.push(row.product);
    }
  }

  const extras = railProducts.filter((p) => !seen.has(p.id));
  return { posts, products: [...fromTrending, ...extras] };
}

function renderPostRow(row: SearchResultRow) {
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

type Props = {
  posts: SearchResultRow[];
  products: SearchProductResult[];
};

/**
 * Asymmetric discovery layout: posts/threads on the left (~2/3),
 * portrait flea cards stacked on the right (~1/3).
 */
export function DiscoverTrendingMosaic({ posts, products }: Props) {
  const hasPosts = posts.length > 0;
  const hasProducts = products.length > 0;

  if (!hasPosts && !hasProducts) return null;

  if (!hasProducts) {
    return (
      <div className="discover-compact-list">{posts.map(renderPostRow)}</div>
    );
  }

  if (!hasPosts) {
    return (
      <div className="discover-trending-mosaic__products is-alone">
        {products.map((product) => (
          <DiscoverProductCard
            key={`d-product-${product.id}`}
            product={product}
            layout="stack"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="discover-trending-mosaic">
      <div className="discover-trending-mosaic__posts">
        {posts.map(renderPostRow)}
      </div>
      <div className="discover-trending-mosaic__products">
        {products.map((product) => (
          <DiscoverProductCard
            key={`d-product-${product.id}`}
            product={product}
            layout="stack"
          />
        ))}
      </div>
    </div>
  );
}
