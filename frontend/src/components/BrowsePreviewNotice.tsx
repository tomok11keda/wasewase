import { Link } from "react-router-dom";
import { spaLoginPath } from "../features/auth/api";

type Props = {
  nextPath: string;
  children?: string;
};

export function BrowsePreviewNotice({ nextPath, children }: Props) {
  return (
    <div className="browse-preview">
      {children ? <p className="empty-message">{children}</p> : null}
      <p className="feed-scope-hint">
        早稲田メールでログインすると利用できます。{" "}
        <Link to={spaLoginPath(nextPath)}>ログイン</Link>
      </p>
    </div>
  );
}
