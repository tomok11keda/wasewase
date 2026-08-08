type Props = {
  title: string;
  body: string;
};

export function PlaceholderPage({ title, body }: Props) {
  return (
    <div className="main-inner">
      <section className="spa-placeholder" data-spa-page={title}>
        <h2>{title}</h2>
        <p>{body}</p>
        <p className="spa-placeholder__note">
          Phase 1–2 プレースホルダ（機能は Phase 3 以降）。クラシック版は{" "}
          <a href="/" style={{ color: "var(--accent)", fontWeight: 700 }}>
            既存トップ
          </a>{" "}
          を利用してください。
        </p>
      </section>
    </div>
  );
}
