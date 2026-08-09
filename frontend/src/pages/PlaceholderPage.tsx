import { Link } from "react-router-dom";

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
          <Link to="/" style={{ color: "var(--accent)", fontWeight: 700 }}>
            ホーム
          </Link>
          に戻る
        </p>
      </section>
    </div>
  );
}
