import { Link, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useSession } from "../lib/session";
import { logoutRequest, spaLoginPath } from "../features/auth/api";
import type { MeResponse } from "../lib/api";
import { SpaDiagSection } from "../components/SpaDiagSection";
import { SpaNativeProbe } from "../components/SpaNativeProbe";

function ClassicLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a className="more-link" href={href}>
      {children}
      <small className="more-link-note">（従来ページ）</small>
    </a>
  );
}

export function MorePage() {
  const { me, setMeFromAuth, refresh } = useSession();
  const navigate = useNavigate();
  const user = me?.user;

  const onLogout = async () => {
    try {
      await logoutRequest();
    } catch {
      /* ignore */
    }
    setMeFromAuth({
      authenticated: false,
      is_browse_mode: false,
      react_spa_enabled: true,
      user: null,
      unread_notifications: 0,
      dm_unread_total: 0,
    } as MeResponse);
    await refresh();
    navigate("/login", { replace: true });
  };

  const spaProfile = user
    ? `/app/users/${user.id}/posts`
    : "/app/";

  return (
    <div className="more-page" data-spa-page="その他">
      <main className="main-inner">
        <h1 className="page-title">その他</h1>

        <p className="more-section-title">アカウント</p>
        <ul className="more-list">
          {me?.authenticated && user ? (
            <>
              <li>
                <Link className="more-link" to={`/users/${user.id}/posts`}>
                  プロフィール
                </Link>
              </li>
              <li>
                <Link className="more-link" to={`/users/${user.id}/flea`}>
                  公開プロフィール（フリマ）
                </Link>
              </li>
              <li>
                <ClassicLink
                  href={`/mypage/edit/?next=${encodeURIComponent(spaProfile)}`}
                >
                  プロフィール設定
                </ClassicLink>
              </li>
              <li>
                <ClassicLink href="/mypage/settings/">
                  アカウント設定（退会）
                </ClassicLink>
              </li>
              <li>
                <ClassicLink href="/mypage/settings/blocked/">
                  ブロック一覧
                </ClassicLink>
              </li>
              <li>
                <Link className="more-link" to="/flea/exhibit">
                  商品を出品
                </Link>
              </li>
              <li>
                <Link className="more-link" to={`/users/${user.id}/bookmarks`}>
                  ブックマーク
                </Link>
              </li>
              <li>
                <button
                  type="button"
                  className="more-link more-link-button"
                  onClick={() => void onLogout()}
                >
                  ログアウト
                </button>
              </li>
            </>
          ) : (
            <>
              <li>
                <Link className="more-link" to={spaLoginPath("/app/more")}>
                  ログイン
                </Link>
              </li>
              <li>
                <Link className="more-link" to="/signup">
                  新規登録
                </Link>
              </li>
              <li>
                <Link
                  className="more-link"
                  to={spaLoginPath("/app/flea/exhibit")}
                >
                  商品を出品
                </Link>
              </li>
            </>
          )}
        </ul>

        <p className="more-section-title">サービス</p>
        <ul className="more-list">
          <li>
            <Link className="more-link" to="/">
              タイムライン（ホーム）
            </Link>
          </li>
          <li>
            <Link className="more-link" to="/communities">
              コミュニティ
            </Link>
          </li>
          <li>
            <Link className="more-link" to="/flea">
              フリマ
            </Link>
          </li>
          <li>
            <Link className="more-link" to="/timetable">
              時間割
            </Link>
          </li>
          <li>
            <Link className="more-link" to="/search">
              検索
            </Link>
          </li>
          <li>
            <Link className="more-link" to="/notifications">
              通知
            </Link>
          </li>
          <li>
            <Link className="more-link" to="/dm">
              メッセージ
            </Link>
          </li>
        </ul>

        <SpaNativeProbe />
        <SpaDiagSection />
      </main>
    </div>
  );
}
