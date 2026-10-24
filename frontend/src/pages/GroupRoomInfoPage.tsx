import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";
import { spaLoginPath } from "../features/auth/api";
import { fetchGroupRoom, type GroupRoomDetail } from "../features/dm/api";
import { useSession } from "../lib/session";

export function GroupRoomInfoPage() {
  const { roomPk } = useParams();
  const roomId = Number(roomPk);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const [room, setRoom] = useState<GroupRoomDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/dm/groups/${roomPk || ""}/info`), {
        replace: true,
      });
      return;
    }
    if (!Number.isFinite(roomId)) {
      setError("invalid_id");
      setLoading(false);
      return;
    }
    const ac = new AbortController();
    setLoading(true);
    void fetchGroupRoom(roomId, ac.signal)
      .then((data) => {
        if (ac.signal.aborted) return;
        setRoom(data.room);
        setError(null);
      })
      .catch((err) => {
        if (ac.signal.aborted || (err as Error)?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "load_failed");
        setRoom(null);
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [me?.authenticated, sessionLoading, roomId, roomPk, navigate]);

  if (loading || sessionLoading) {
    return (
      <div className="dm-page chat-info-page" data-spa-page="グループ情報">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (error || !room) {
    return (
      <div className="dm-page chat-info-page" data-spa-page="グループ情報">
        <div className="main-inner">
          <p>グループを表示できません（{error || "not_found"}）</p>
          <Link to="/dm">メッセージ一覧へ戻る</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="dm-page chat-info-page" data-spa-page="グループ情報">
      <div className="main-inner">
        <section className="chat-info-hero">
          <span className="chat-info-hero__avatar" aria-hidden="true">
            {(room.name || "G").slice(0, 1)}
          </span>
          <h1>{room.name}</h1>
          <p>メンバー {room.member_count}人</p>
          {room.pending_invites?.length ? (
            <p>招待中 {room.pending_invites.length}人</p>
          ) : null}
        </section>

        <h2 className="chat-info-heading">メンバー</h2>
        {room.members.length === 0 ? (
          <p className="org-profile-empty">メンバー情報はありません。</p>
        ) : (
          <ul className="chat-info-members">
            {room.members.map((member, index) => {
              const name = member.display_name || member.username || "ユーザー";
              const body = (
                <>
                  {member.avatar_url ? (
                    <img src={member.avatar_url} alt="" />
                  ) : (
                    <span className="chat-info-members__initial">
                      {member.initial || name.slice(0, 1)}
                    </span>
                  )}
                  <AccountDisplayName
                    name={name}
                    verified={member.is_operator_verified}
                  />
                </>
              );
              return (
                <li key={member.id ?? `${member.username}-${index}`}>
                  {member.id ? (
                    <Link to={`/users/${member.id}/posts`}>{body}</Link>
                  ) : (
                    <span className="chat-info-members__row">{body}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
