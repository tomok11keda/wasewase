import { Link } from "react-router-dom";
import type { SharedProduct } from "./api";

function yen(price: number): string {
  return `¥${Number(price || 0).toLocaleString("ja-JP")}`;
}

export function TimelineFleaShareCard({
  product,
}: {
  product: SharedProduct;
}) {
  const statusLabel = product.is_sold
    ? "SOLD OUT"
    : product.is_pending
      ? "取引中"
      : null;
  return (
    <Link
      className="share-card share-card--flea timeline-flea-share"
      to={`/flea/products/${product.id}`}
      aria-label={`フリマ商品 ${product.name}`}
    >
      <p className="share-card__brand">フリマ</p>
      {product.image_url ? (
        <img
          className="share-card__media"
          src={product.image_url}
          alt=""
        />
      ) : (
        <div className="share-card__media timeline-flea-share__empty">
          No Image
        </div>
      )}
      <p className="share-card__title">{product.name}</p>
      <p className="share-card__price">
        {statusLabel || yen(product.price)}
      </p>
    </Link>
  );
}
