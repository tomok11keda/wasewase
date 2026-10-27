import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import { recruitingChatPath } from "../features/orgs/recruitingChat";
import { fetchRecruitingRoom } from "../features/orgs/recruitingChatApi";
import { useSession } from "../lib/session";
import { ChatInfoHeroSkeleton } from "../components/skeleton";

export function RecruitingChatRoomRedirectPage() {
  const { roomPk } = useParams();
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const [error, setError] = useState<string | null>(null);
  const roomId = Number(roomPk);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/dm/recruiting/${roomPk || ""}`), {
        replace: true,
      });
      return;
    }
    if (!Number.isFinite(roomId)) {
      setError("invalid_id");
      return;
    }
    const ac = new AbortController();
    void fetchRecruitingRoom(roomId, ac.signal)
      .then((data) => {
        const slug = data.room.organization_slug;
        if (slug) {
          navigate(
            recruitingChatPath(slug, data.recruiting_chat?.id),
            { replace: true }
          );
          return;
        }
        setError("not_found");
      })
      .catch((err) => {
        if ((err as Error)?.name === "AbortError") return;
        if (err instanceof OrganizationRequestError) {
          setError(err.code);
          return;
        }
        setError("load_failed");
      });
    return () => ac.abort();
  }, [me?.authenticated, sessionLoading, roomId, roomPk, navigate]);

  if (sessionLoading || !error) {
    return (
      <div className="dm-page" data-spa-page="団体チャット">
        <div className="main-inner">
          <ChatInfoHeroSkeleton rounded />
        </div>
      </div>
    );
  }

  if (error === "unauthorized") {
    return <Navigate to={spaLoginPath(`/app/dm/recruiting/${roomPk || ""}`)} replace />;
  }

  return (
    <div className="dm-page" data-spa-page="団体チャット">
      <div className="main-inner">
        <Link className="dm-back-text" to="/dm">
          ← メッセージ一覧
        </Link>
        <p>
          {error === "forbidden" || error === "not_found"
            ? "このチャットを表示する権限がありません。"
            : "団体チャットを開けませんでした。"}
        </p>
      </div>
    </div>
  );
}
