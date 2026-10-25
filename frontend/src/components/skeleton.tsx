type BoneProps = {
  className?: string;
  width?: string | number;
  height?: string | number;
};

export function SkeletonBone({ className = "", width, height }: BoneProps) {
  const style = {
    ...(width != null ? { width } : {}),
    ...(height != null ? { height } : {}),
  };
  return (
    <span
      className={`sk-bone${className ? ` ${className}` : ""}`}
      style={Object.keys(style).length ? style : undefined}
      aria-hidden="true"
    />
  );
}

export function SkeletonCircle({
  size = 48,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={`sk-bone sk-bone--circle${className ? ` ${className}` : ""}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  );
}

/** Circle, rectangle, or text-line placeholder. No dummy copy. */
export function SkeletonPrimitive({
  variant = "rect",
  className = "",
  width,
  height,
  size = 48,
}: BoneProps & { variant?: "rect" | "circle" | "line"; size?: number }) {
  if (variant === "circle") {
    return <SkeletonCircle size={size} className={className} />;
  }
  return (
    <SkeletonBone
      className={`${variant === "line" ? "sk-bone--line" : ""}${className ? ` ${className}` : ""}`.trim()}
      width={width}
      height={height}
    />
  );
}

export function ListRowSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <ul className="sk-list" aria-busy="true" aria-label="読み込み中">
      {Array.from({ length: rows }, (_, index) => (
        <li key={index} className="sk-list-row">
          <SkeletonBone className="sk-list-row__title" />
          <SkeletonBone className="sk-list-row__meta" />
        </li>
      ))}
    </ul>
  );
}

export function ProfileHeaderSkeleton({
  variant = "user",
}: {
  variant?: "user" | "org";
}) {
  const isOrg = variant === "org";
  return (
    <section className="profile-card" aria-busy="true" aria-label="読み込み中">
      <div className={`profile-header${isOrg ? " org-profile-header" : ""}`}>
        <SkeletonCircle size={72} className="profile-avatar" />
        <div className="profile-identity">
          {isOrg ? <SkeletonBone className="sk-bone--kicker" /> : null}
          <SkeletonBone className="sk-bone--name" />
          <SkeletonBone className="sk-bone--handle" />
        </div>
      </div>
      <SkeletonBone className="sk-bone--bio" />
      <SkeletonBone className="sk-bone--bio is-short" />
      {!isOrg ? (
        <div className="profile-stats sk-stats" aria-hidden="true">
          <SkeletonBone className="sk-bone--stat" />
          <SkeletonBone className="sk-bone--stat" />
          <SkeletonBone className="sk-bone--stat" />
        </div>
      ) : null}
      {!isOrg ? (
        <div className="profile-actions profile-actions--own" aria-hidden="true">
          <SkeletonBone className="sk-bone--btn" />
        </div>
      ) : null}
    </section>
  );
}

export function PostCardSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="sk-feed" aria-busy="true" aria-label="読み込み中">
      {Array.from({ length: count }, (_, index) => (
        <article key={index} className="sk-post">
          <SkeletonCircle size={40} />
          <div className="sk-post__body">
            <SkeletonBone className="sk-bone--name" />
            <SkeletonBone className="sk-list-row__title" />
            <SkeletonBone className="sk-list-row__title is-mid" />
          </div>
        </article>
      ))}
    </div>
  );
}

export function ProductGridSkeleton({
  count = 4,
  className = "product-grid profile-product-grid",
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div className={className} aria-busy="true" aria-label="読み込み中">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="sk-product">
          <SkeletonBone className="sk-product__media" />
          <SkeletonBone className="sk-product__title" />
        </div>
      ))}
    </div>
  );
}

export function PostDetailSkeleton() {
  return (
    <div className="post-detail-body" aria-busy="true" aria-label="読み込み中">
      <PostCardSkeleton count={1} />
      <ListRowSkeleton rows={3} />
    </div>
  );
}

export function ProductDetailSkeleton() {
  return (
    <article className="product-hero" aria-busy="true" aria-label="読み込み中">
      <div className="product-hero-image" aria-hidden="true">
        <SkeletonBone className="sk-product-hero" />
      </div>
      <div className="product-info" aria-hidden="true">
        <SkeletonPrimitive className="sk-bone--name" />
        <SkeletonPrimitive variant="line" className="sk-thread-meta" />
        <SkeletonPrimitive className="sk-product-price" />
        <SkeletonPrimitive className="sk-bone--bio" />
        <SkeletonPrimitive className="sk-bone--bio is-short" />
        <SkeletonPrimitive className="sk-bone--btn" />
      </div>
    </article>
  );
}

export function ThreadDetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="読み込み中">
      <article className="thread-detail forum-op" aria-hidden="true">
        <SkeletonPrimitive className="sk-thread-board" />
        <SkeletonPrimitive className="sk-bone--name" />
        <SkeletonPrimitive className="sk-list-row__title" />
        <SkeletonPrimitive className="sk-list-row__title is-mid" />
        <SkeletonPrimitive className="sk-bone--bio" />
      </article>
      <ListRowSkeleton rows={4} />
    </div>
  );
}

export function ThreadListSkeleton({ count = 6 }: { count?: number }) {
  return (
    <ul className="thread-list" aria-busy="true" aria-label="読み込み中">
      {Array.from({ length: count }, (_, index) => (
        <li key={index} className="thread-card-row" aria-hidden="true">
          <div className="thread-card">
            <SkeletonPrimitive className="sk-bone--name" />
            <SkeletonPrimitive variant="line" className="sk-thread-meta" />
            <SkeletonPrimitive className="sk-list-row__title" />
            <SkeletonPrimitive className="sk-list-row__title is-mid" />
            <SkeletonPrimitive className="sk-thread-board" />
          </div>
        </li>
      ))}
    </ul>
  );
}
