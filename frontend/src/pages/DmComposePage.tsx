import { Link, Navigate } from "react-router-dom";
import { spaLoginPath } from "../features/auth/api";
import { isBrowsePreview, useSession } from "../lib/session";

export function DmComposePage() {
  const { me, loading } = useSession();
  const browsePreview = isBrowsePreview(me);

  if (!loading && (browsePreview || !me?.authenticated)) {
    return <Navigate to={spaLoginPath("/app/dm/new")} replace />;
  }

  return (
    <div className="dm-page" data-spa-page="新しいチャット">
      <main className="main-inner" aria-label="新しいチャット">
        <p className="dm-compose-lead">
          作成するチャットの種類を選んでください。
        </p>
        <ul className="dm-compose-list">
          <li>
            <Link className="dm-compose-choice" to="/dm/new/direct">
              <strong>個人チャット</strong>
              <span>フォロー中の学生や検索した相手と1対1で話す</span>
            </Link>
          </li>
          <li>
            <Link className="dm-compose-choice" to="/dm/groups/new">
              <strong>グループチャット</strong>
              <span>複数人を招待してグループを作る</span>
            </Link>
          </li>
          <li>
            <Link className="dm-compose-choice" to="/dm/new/org-chat">
              <strong>団体チャット</strong>
              <span>管理している団体のチャットを開くか作成する</span>
            </Link>
          </li>
        </ul>
      </main>
    </div>
  );
}
