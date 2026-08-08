export function SidebarWidgets() {
  return (
    <div className="sidebar-right-inner">
      <section className="widget-card">
        <h2 className="widget-card__title">わせわせ</h2>
        <p className="widget-card__lead">
          早稲田大学生向けキャンパスSNS。React版シェル（Phase 1–2）です。
        </p>
      </section>
      <section className="widget-card">
        <h2 className="widget-card__title">クラシック版</h2>
        <p className="widget-card__lead">
          既存のフル機能はこれまでどおり{" "}
          <a href="/" style={{ color: "var(--accent)", fontWeight: 700 }}>
            トップ
          </a>{" "}
          から利用できます。
        </p>
      </section>
    </div>
  );
}
