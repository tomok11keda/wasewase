import { Link } from "react-router-dom";
import { AccountMenuContent } from "../components/AccountMenuContent";

/** Kept for deep links (/more) and settings back-navigation; not a bottom tab. */
export function MorePage() {
  return (
    <div className="more-page" data-spa-page="メニュー">
      <main className="main-inner">
        <h1 className="page-title">メニュー</h1>
        <p className="more-page-lead">
          左上のプロフィールアイコンからも同じメニューを開けます。
        </p>
        <AccountMenuContent />
        <p className="more-page-foot">
          <Link to="/">タイムラインへ戻る</Link>
        </p>
      </main>
    </div>
  );
}
