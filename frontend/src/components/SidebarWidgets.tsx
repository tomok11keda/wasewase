import { Link } from "react-router-dom";

export function SidebarWidgets() {
  return (
    <div className="sidebar-right-inner">
      <section className="widget-card">
        <h2 className="widget-card__title">わせわせ</h2>
        <p className="widget-card__lead">
          早稲田大学生向けキャンパスSNSです。
        </p>
      </section>
      <section className="widget-card">
        <h2 className="widget-card__title">ホーム</h2>
        <p className="widget-card__lead">
          <Link to="/" style={{ color: "var(--accent)", fontWeight: 700 }}>
            タイムライン
          </Link>
          から投稿やコミュニティ、フリマを利用できます。
        </p>
      </section>
    </div>
  );
}
