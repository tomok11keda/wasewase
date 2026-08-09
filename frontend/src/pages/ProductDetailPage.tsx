import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../lib/session";
import {
  deleteProduct,
  fetchProductDetail,
  postProductComment,
  purchaseErrorMessage,
  purchaseProduct,
  shareProductToTimeline,
  startProductChat,
  submitProductReview,
  toggleProductLike,
  type ProductDetail,
} from "../features/flea/api";
import { spaLoginPath } from "../features/auth/api";

export function ProductDetailPage() {
  const { pk } = useParams();
  const productId = Number(pk);
  const navigate = useNavigate();
  const { me } = useSession();
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ type: string; text: string } | null>(
    null
  );
  const [commentBody, setCommentBody] = useState("");
  const [rating, setRating] = useState(3);
  const [reviewComment, setReviewComment] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(productId)) {
      setError("invalid_id");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchProductDetail(productId);
      setProduct(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load_failed");
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    void load();
  }, [load]);

  const requireLogin = (next: string) => {
    navigate(spaLoginPath(next));
  };

  const onLike = async () => {
    if (!product) return;
    if (!me?.authenticated) {
      requireLogin(`/app/flea/products/${product.id}`);
      return;
    }
    try {
      const result = await toggleProductLike(product.id);
      setProduct({
        ...product,
        user_liked: result.liked,
        like_count: result.like_count,
      });
    } catch (err) {
      setFlash({
        type: "error",
        text: err instanceof Error ? err.message : "いいねに失敗しました",
      });
    }
  };

  const onPurchase = async () => {
    if (!product) return;
    if (!me?.authenticated) {
      requireLogin(`/app/flea/products/${product.id}`);
      return;
    }
    if (!window.confirm("この商品を即決購入しますか？")) return;
    setBusy(true);
    setFlash(null);
    try {
      const roomId = await purchaseProduct(product.id);
      const refreshed = await fetchProductDetail(product.id);
      setProduct(refreshed);
      setFlash({
        type: "success",
        text: "即決購入が成立しました。受け渡し場所と時間を相談してください。",
      });
      navigate(`/flea/chats/${roomId}`);
    } catch (err) {
      const code = err instanceof Error ? err.message : "purchase_failed";
      setFlash({ type: "warning", text: purchaseErrorMessage(code) });
      void load();
    } finally {
      setBusy(false);
    }
  };

  const onStartChat = async () => {
    if (!product) return;
    if (!me?.authenticated) {
      requireLogin(`/app/flea/products/${product.id}`);
      return;
    }
    setBusy(true);
    try {
      const roomId = await startProductChat(product.id);
      navigate(`/flea/chats/${roomId}`);
    } catch (err) {
      setFlash({
        type: "error",
        text: err instanceof Error ? err.message : "チャットを開始できません",
      });
      void load();
    } finally {
      setBusy(false);
    }
  };

  const onComment = async (e: FormEvent) => {
    e.preventDefault();
    if (!product || !commentBody.trim()) return;
    setBusy(true);
    try {
      const comment = await postProductComment(product.id, commentBody.trim());
      setProduct({
        ...product,
        comments: [...product.comments, comment],
      });
      setCommentBody("");
    } catch (err) {
      setFlash({
        type: "error",
        text: err instanceof Error ? err.message : "コメントに失敗しました",
      });
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async () => {
    if (!product) return;
    if (!window.confirm("この商品を削除しますか？")) return;
    setBusy(true);
    try {
      await deleteProduct(product.id);
      navigate("/flea");
    } catch (err) {
      setFlash({
        type: "error",
        text: err instanceof Error ? err.message : "削除に失敗しました",
      });
      setBusy(false);
    }
  };

  const onShare = async () => {
    if (!product) return;
    setBusy(true);
    try {
      await shareProductToTimeline(product.id);
      setFlash({ type: "success", text: "スレッドにシェアしました！" });
    } catch (err) {
      setFlash({
        type: "error",
        text: err instanceof Error ? err.message : "シェアに失敗しました",
      });
    } finally {
      setBusy(false);
    }
  };

  const onReview = async (e: FormEvent) => {
    e.preventDefault();
    if (!product) return;
    setBusy(true);
    try {
      await submitProductReview(product.id, rating, reviewComment);
      setFlash({ type: "success", text: "評価を投稿しました。" });
      await load();
    } catch (err) {
      setFlash({
        type: "error",
        text: err instanceof Error ? err.message : "評価に失敗しました",
      });
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="product-detail-page" data-spa-page="フリマ">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="product-detail-page" data-spa-page="フリマ">
        <div className="main-inner">
          <Link className="back-link" to="/flea">
            ← フリマへ戻る
          </Link>
          <p>商品を表示できません（{error || "not_found"}）</p>
        </div>
      </div>
    );
  }

  return (
    <div className="product-detail-page" data-spa-page="フリマ">
      <div className="main-inner">
        <Link className="back-link" to="/flea">
          ← フリマへ戻る
        </Link>

        {flash ? <div className={`flash ${flash.type}`}>{flash.text}</div> : null}

        <article
          className={`product-hero${product.is_sold ? " is-sold" : ""}`}
        >
          <div className="product-hero-image">
            {product.image_url ? (
              <img src={product.image_url} alt={product.name} />
            ) : (
              "No Image"
            )}
            {product.is_sold ? (
              <span className="sold-out-badge">SOLD OUT</span>
            ) : product.is_pending ? (
              <span className="sold-out-badge trading-badge">取引中</span>
            ) : null}
          </div>
          <div className="product-info">
            <h1 className="product-name">{product.name}</h1>
            <p className="product-seller">
              出品者{" "}
              <strong>{product.seller?.display_name || "不明"}</strong>
              <span className="product-posted-at">
                {product.created_at_label}
              </span>
            </p>
            <p className="product-price">
              <span className="yen">¥</span>
              {product.price}
            </p>
            {product.handover_campus_label ? (
              <p className="meta-row">
                受け渡し: {product.handover_campus_label}
              </p>
            ) : null}
            {product.faculty ? (
              <p className="meta-row">対象学部: {product.faculty}</p>
            ) : null}
            {(product.course_name || product.professor_name) && (
              <p className="meta-row">
                {[product.course_name, product.professor_name]
                  .filter(Boolean)
                  .join(" / ")}
              </p>
            )}
            <p
              className={`product-description${
                product.description ? "" : " product-description-empty"
              }`}
            >
              {product.description || "説明文はありません。"}
            </p>

            {product.can_purchase ? (
              <p className="purchase-hint">
                即決購入すると取引チャットが始まり、商品は「取引中」になります。
              </p>
            ) : null}

            <div className="action-bar">
              <div className="action-row">
                <button
                  type="button"
                  className={`btn btn-like${product.user_liked ? " is-liked" : ""}`}
                  onClick={() => void onLike()}
                  disabled={busy}
                >
                  {product.user_liked ? "♥" : "♡"} {product.like_count}
                </button>
                {product.can_purchase ? (
                  <button
                    type="button"
                    className="btn btn-purchase"
                    onClick={() => void onPurchase()}
                    disabled={busy}
                  >
                    即決購入
                  </button>
                ) : null}
              </div>

              {product.can_share_to_timeline ? (
                <button
                  type="button"
                  className="btn-share-timeline"
                  onClick={() => void onShare()}
                  disabled={busy}
                >
                  スレッドにシェア
                </button>
              ) : null}

              {product.user_chat_room ? (
                <Link
                  className="btn-chat-open"
                  to={`/flea/chats/${product.user_chat_room.id}`}
                >
                  取引チャットを開く
                </Link>
              ) : product.can_contact_seller && product.can_negotiate ? (
                <button
                  type="button"
                  className="btn-chat-contact"
                  onClick={() => void onStartChat()}
                  disabled={busy}
                >
                  値下げ交渉する
                </button>
              ) : null}

              {product.seller_chat_rooms.length > 0 ? (
                <div className="seller-chat-list">
                  <h3>問い合わせ・取引チャット</h3>
                  {product.seller_chat_rooms.map((room) => (
                    <div className="seller-chat-item" key={room.id}>
                      <p className="seller-chat-meta">
                        {room.buyer?.display_name || "購入希望者"}（
                        {room.deal_status}）
                      </p>
                      <Link to={`/flea/chats/${room.id}`}>開く</Link>
                    </div>
                  ))}
                </div>
              ) : null}

              {product.can_delete ? (
                <div className="owner-actions">
                  <button
                    type="button"
                    className="btn btn-delete"
                    onClick={() => void onDelete()}
                    disabled={busy}
                  >
                    出品を削除
                  </button>
                </div>
              ) : null}

              {me?.authenticated &&
              product.seller &&
              me.user?.id !== product.seller.id ? (
                <a
                  className="meta-row"
                  href={`/report/product/${product.id}/`}
                  style={{ color: "var(--accent)" }}
                >
                  この商品を通報
                </a>
              ) : null}
            </div>
          </div>
        </article>

        {product.can_review ? (
          <section className="comments-section">
            <h2>取引相手を評価</h2>
            <form className="review-form" onSubmit={onReview}>
              <select
                value={rating}
                onChange={(e) => setRating(Number(e.target.value))}
              >
                <option value={3}>良い ★3</option>
                <option value={2}>普通 ★2</option>
                <option value={1}>悪い ★1</option>
              </select>
              <textarea
                value={reviewComment}
                onChange={(e) => setReviewComment(e.target.value)}
                maxLength={200}
                rows={2}
                placeholder="短いコメント..."
              />
              <button type="submit" className="btn btn-purchase" disabled={busy}>
                評価を送信
              </button>
            </form>
          </section>
        ) : null}

        <section className="comments-section">
          <h2>コメント（{product.comments.length}）</h2>
          {product.comments.map((c) => (
            <div className="comment-item" key={c.id}>
              <p className="comment-meta">
                {c.author?.display_name || "匿名"} · {c.created_at_label}
              </p>
              <p className="comment-body">{c.body}</p>
            </div>
          ))}
          <form className="comment-form" onSubmit={onComment}>
            <textarea
              value={commentBody}
              onChange={(e) => setCommentBody(e.target.value)}
              rows={3}
              placeholder="コメントを入力..."
              required
            />
            <button type="submit" disabled={busy}>
              投稿
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
