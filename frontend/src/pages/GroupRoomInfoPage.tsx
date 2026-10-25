import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";
import { ChatInfoHeroSkeleton, PeopleListSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { readGroupHeaderPreview } from "../features/chat/inboxRoomPreview";
import { fetchGroupRoom, type GroupRoomDetail } from "../features/dm/api";
import { detailContentPhase } from "../lib/detailContentPhase";
import { useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function GroupRoomInfoPage() {
  const { roomPk } = useParams();
  const roomId = Number(roomPk);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [room, setRoom] = useState<GroupRoomDetail | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setRoom(null);
    setHydrated(false);
    setLoading(true);
    setError(null);
  }, [roomId, sessionUserId]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!Number.isFinite(roomId)) {
        setError("invalid_id");
        setLoading(false);
        setHydrated(true);
        return;
      }
      const gen = nextRequestId(fetchGen);
      const startedUserId = userIdRef.current;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchGroupRoom(roomId, signal);
        if (signal?.aborted) return;
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setRoom(data.room);
        setError(null);
        setHydrated(true);
      } catch (err) {
        if (signal?.aborted || (err as Error)?.name === "AbortError") return;
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setError(err instanceof Error ? err.message : "load_failed");
        setRoom(null);
        setHydrated(true);
      } finally {
        if (isLatestRequest(fetchGen, gen)) setLoading(false);
      }
    },
    [roomId]
  );

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/dm/groups/${roomPk || ""}/info`), {
        replace: true,
      });
      return;
    }
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [me?.authenticated, sessionLoading, roomId, roomPk, navigate, load, sessionUserId]);

  const liveRoom = room && room.id === roomId ? room : null;
  const preview = readGroupHeaderPreview(sessionUserId, roomId);
  const phase = detailContentPhase({
    browsePreview: false,
    loading: sessionLoading || loading,
    error,
    hasItem: Boolean(liveRoom),
    hydrated: Boolean(liveRoom) && hydrated,
  });

  return (
    <div className="dm-page chat-info-page" data-spa-page="グループ情報">
      <div className="main-inner">
        {phase === "error" || (hydrated && !liveRoom) ? (
          <>
            <p>グループを表示できません（{error || "not_found"}）</p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void load()}
            >
              再試行
            </button>
            <p>
              <Link to="/dm">メッセージ一覧へ戻る</Link>
            </p>
          </>
        ) : phase === "skeleton" || !liveRoom ? (
          <>
            {preview ? (
              <section className="chat-info-hero">
                <span className="chat-info-hero__avatar" aria-hidden="true">
                  {preview.avatarInitial || (preview.title || "G").slice(0, 1)}
                </span>
                <h1>{preview.title}</h1>
                {preview.subtitle ? <p>{preview.subtitle}</p> : null}
              </section>
            ) : (
              <ChatInfoHeroSkeleton />
            )}
            <h2 className="chat-info-heading">メンバー</h2>
            <PeopleListSkeleton rows={5} />
          </>
        ) : (
          <>
            <section className="chat-info-hero">
              <span className="chat-info-hero__avatar" aria-hidden="true">
                {(liveRoom.name || "G").slice(0, 1)}
              </span>
              <h1>{liveRoom.name}</h1>
              <p>メンバー {liveRoom.member_count}人</p>
              {liveRoom.pending_invites?.length ? (
                <p>招待中 {liveRoom.pending_invites.length}人</p>
              ) : null}
            </section>

            <h2 className="chat-info-heading">メンバー</h2>
            {liveRoom.members.length === 0 ? (
              <p className="org-profile-empty">メンバー情報はありません。</p>
            ) : (
              <ul className="chat-info-members">
                {liveRoom.members.map((member, index) => {
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
          </>
        )}
      </div>
    </div>
  );
}
