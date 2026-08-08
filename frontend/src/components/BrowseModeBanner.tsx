import { Link } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";

export function BrowseModeBanner() {
  const { me } = useSession();
  if (!me || me.authenticated || !me.is_browse_mode) {
    return null;
  }

  return (
    <div className="browse-mode-banner" role="status">
      <span>閲覧モードです。投稿やいいねにはログインが必要です。</span>
      <Link to={spaLoginPath("/app/")}>ログイン</Link>
    </div>
  );
}
