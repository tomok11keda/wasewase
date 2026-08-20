import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import { fetchDmInbox, type InboxItem } from "../features/dm/api";

const TABS = [
  { key: "all", label: "すべて" },
  { key: "dm", label: "通常" },
  { key: "course", label: "授業" },
  { key: "trade", label: "取引" },
] as const;

function statusClass(label: string): string {
  if (label === "取引中") return " is-trading";
  if (label === "売り切れ") return " is-sold";
  if (label === "交渉終了") return " is-closed";
  if (label === "履修中") return " is-enrolled";
  if (label === "履修済み") return " is-past";
  return "";
}

function avatarContent(item: InboxItem) {
  if (item.kind === "trade") {
    if (item.thumbnail_url) {
      return <img src={item.thumbnail_url} alt="" />;
    }
    return "🛒";
  }
  if (item.kind === "course") return "📚";
  if (item.kind === "group" || item.kind === "group_invite") return "👥";
  if (item.is_blocked) return "?";
  const name = item.partner?.display_name || item.display_name || "?";
  return name.slice(0, 1);
}

function emptyCopy(tab: string) {
  if (tab === "trade") {
    return {
      title: "取引チャットはまだありません",
      body: "フリマで即決購入や値下げ交渉をすると、ここに取引チャットが表示されます。",
    };
  }
  if (tab === "dm") {
    return {
      title: "通常のDMはまだありません",
      body: "プロフィールやタイムラインの「DM」ボタンから会話を始めるか、右下の＋からグループを作成できます。",
    };
  }
  if (tab === "course") {
    return {
      title: "参加中の授業トークはありません",
      body: "授業詳細の「授業トーク」を開くと、ここに表示されます。履修前の質問もOKです。",
    };
  }
  return {
    title: "まだ会話がありません",
    body: "通常のDM・グループ、授業トーク、またはフリマの取引チャットがここに表示されます。",
  };
}

export function DmInboxPage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") || "all";
  const [items, setItems] = useState<InboxItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [requestCount, setRequestCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!me?.authenticated) return;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchDmInbox(tab, signal);
        if (signal?.aborted) return;
        setItems(data.conversations || []);
        setCounts(data.tab_counts || {});
        setRequestCount(Number(data.message_request_count || 0));
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [me?.authenticated, tab]
  );

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/dm"), { replace: true });
      return;
    }
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [sessionLoading, me?.authenticated, load]);

  if (sessionLoading || !me?.authenticated) {
    return (
      <div className="dm-page" data-spa-page="メッセージ">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  const empty = emptyCopy(tab);

  return (
    <div className="dm-page" data-spa-page="メッセージ">
      <main className="main-inner" data-dm-inbox>
        <header className="dm-inbox-header">
          <h1>メッセージ</h1>
          <p>DM・授業トーク・取引チャットをまとめて確認できます。</p>
          <nav className="dm-inbox-tabs" aria-label="メッセージの種類">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                className={`dm-inbox-tab${tab === t.key ? " is-active" : ""}`}
                aria-current={tab === t.key ? "page" : undefined}
                onClick={() =>
                  setSearchParams(t.key === "all" ? {} : { tab: t.key })
                }
              >
                {t.label}
                <span className="dm-inbox-tab-count">
                  {typeof counts[t.key] === "number" ? counts[t.key] : 0}
                </span>
              </button>
            ))}
          </nav>
        </header>

        {!loading && requestCount > 0 ? (
          <Link className="dm-request-entry" to="/dm/requests">
            <span className="dm-request-entry__label">
              💬 メッセージリクエスト
            </span>
            <span className="dm-request-entry__count" aria-label={`${requestCount}件`}>
              {requestCount}
            </span>
          </Link>
        ) : null}

        {loading ? (
          <p className="dm-inbox-empty">読み込み中…</p>
        ) : error ? (
          <p className="dm-inbox-empty">読み込みに失敗しました（{error}）</p>
        ) : items.length === 0 ? (
          <div className="dm-inbox-empty">
            <strong>{empty.title}</strong>
            {empty.body}
          </div>
        ) : (
          <ul className="dm-inbox-list">
            {items.map((item) => (
              <li key={`${item.kind}-${item.room_id}`}>
                <Link
                  className={`dm-inbox-item${
                    item.unread_count > 0 ? " has-unread" : ""
                  }${item.kind === "group_invite" ? " is-invite" : ""}`}
                  to={item.spa_path}
                >
                  <span
                    className={`dm-inbox-avatar${
                      item.kind === "group" || item.kind === "group_invite"
                        ? " is-group"
                        : item.kind === "trade"
                          ? " is-trade"
                          : item.kind === "course"
                            ? " is-course"
                            : ""
                    }`}
                    aria-hidden="true"
                  >
                    {avatarContent(item)}
                  </span>
                  <span className="dm-inbox-body">
                    <span className="dm-inbox-top">
                      <span className="dm-inbox-name">{item.display_name}</span>
                    </span>
                    {item.kind === "trade" ? (
                      <>
                        {item.status_label ? (
                          <span
                            className={`dm-inbox-status${statusClass(
                              item.status_label
                            )}`}
                          >
                            {item.status_label}
                          </span>
                        ) : null}
                        {item.partner ? (
                          <span className="dm-inbox-handle">
                            相手: {item.partner.display_name}
                          </span>
                        ) : null}
                      </>
                    ) : item.kind === "course" ? (
                      <>
                        {item.status_label ? (
                          <span
                            className={`dm-inbox-status${statusClass(
                              item.status_label
                            )}`}
                          >
                            {item.status_label}
                          </span>
                        ) : null}
                        <span className="dm-inbox-handle">{item.subtitle}</span>
                      </>
                    ) : item.kind === "group_invite" ? (
                      <>
                        <span className="dm-inbox-status is-invite">
                          {item.status_label || "招待あり"}
                        </span>
                        <span className="dm-inbox-handle">{item.subtitle}</span>
                      </>
                    ) : (
                      <span className="dm-inbox-handle">{item.subtitle}</span>
                    )}
                    {item.kind === "group_invite" ? (
                      <p className="dm-inbox-preview">
                        タップして参加するか辞退してください
                      </p>
                    ) : item.latest_body ? (
                      <p className="dm-inbox-preview">
                        {item.latest_sender_name ? (
                          <span className="dm-inbox-preview-prefix">
                            {item.latest_sender_name}:{" "}
                          </span>
                        ) : null}
                        {item.latest_body}
                      </p>
                    ) : (
                      <p className="dm-inbox-preview">まだメッセージはありません</p>
                    )}
                  </span>
                  <span
                    className="dm-inbox-unread"
                    hidden={item.unread_count <= 0}
                  >
                    {item.unread_count > 0 ? item.unread_count : null}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>

      <Link
        className="dm-create-fab"
        to="/dm/groups/new"
        aria-label="グループを作成"
      >
        +
      </Link>
    </div>
  );
}
