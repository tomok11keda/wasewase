import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import type { InboxItem } from "../features/dm/api";
import {
  clearInboxCache,
  isInboxCacheFresh,
  loadDmInbox,
  readInboxCache,
} from "../features/dm/inboxCache";
import { inboxSpaHref } from "../features/orgs/recruitingChat";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";
import { PullToRefresh } from "../lib/usePullToRefresh";

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
  if (item.kind === "recruiting" || item.kind === "recruiting_invite") {
    if (item.thumbnail_url || item.organization_avatar_url) {
      return (
        <img
          src={item.thumbnail_url || item.organization_avatar_url}
          alt=""
        />
      );
    }
    return (item.display_name || "団").slice(0, 1);
  }
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
      body: "プロフィールやタイムラインの「DM」ボタンから会話を始めるか、右下の＋からチャットを作成できます。",
    };
  }
  if (tab === "course") {
    return {
      title: "参加中の授業掲示板はありません",
      body: "授業詳細の「授業掲示板」を開くと、ここに表示されます。履修前の質問もOKです。",
    };
  }
  return {
    title: "まだ会話がありません",
    body: "通常のDM・グループ、団体チャット、授業掲示板、またはフリマの取引チャットがここに表示されます。",
  };
}

function InboxSkeleton() {
  return (
    <ul
      className="dm-inbox-list dm-inbox-skeleton"
      aria-busy="true"
      aria-label="読み込み中"
    >
      {Array.from({ length: 7 }, (_, index) => (
        <li key={index} className="dm-inbox-skeleton-item">
          <span className="dm-inbox-skeleton-avatar" />
          <span className="dm-inbox-skeleton-lines">
            <span className="dm-inbox-skeleton-line is-name" />
            <span className="dm-inbox-skeleton-line is-preview" />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DmInboxPage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") || "all";
  const userId = me?.authenticated ? me.user?.id ?? null : null;
  const prevUserIdRef = useRef<number | null>(null);
  const [items, setItems] = useState<InboxItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [requestCount, setRequestCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (
      mode: "initial" | "soft" = "initial",
      signal?: AbortSignal,
      forUserId?: number
    ) => {
      const scopedUserId = forUserId ?? userId;
      if (scopedUserId == null) return false;
      if (mode === "initial") {
        setLoading(true);
        setError(null);
      }
      try {
        const entry = await loadDmInbox(scopedUserId, tab, {
          force: mode === "soft",
        });
        if (signal?.aborted) return false;
        setItems(entry.items);
        setCounts(entry.counts);
        setRequestCount(entry.requestCount);
        setError(null);
        return true;
      } catch (err) {
        if (signal?.aborted) return false;
        if (mode === "soft") return false;
        setError(err instanceof Error ? err.message : "load_failed");
        return false;
      } finally {
        if (mode === "initial" && !signal?.aborted) setLoading(false);
      }
    },
    [tab, userId]
  );

  useEffect(() => {
    const previousUserId = prevUserIdRef.current;
    if (previousUserId != null && previousUserId !== userId) {
      clearInboxCache(previousUserId);
      setItems([]);
      setCounts({});
      setRequestCount(0);
    }
    if (userId == null) {
      clearInboxCache();
      setItems([]);
      setCounts({});
      setRequestCount(0);
    }
    prevUserIdRef.current = userId;
  }, [userId]);

  useEffect(() => {
    if (sessionLoading) return;
    if (userId == null) {
      navigate(spaLoginPath("/app/dm"), { replace: true });
      return;
    }
    const cached = readInboxCache(userId, tab);
    if (cached) {
      setItems(cached.items);
      setCounts(cached.counts);
      setRequestCount(cached.requestCount);
      setLoading(false);
      setError(null);
    } else {
      setItems([]);
      setCounts({});
      setRequestCount(0);
      setLoading(true);
      setError(null);
    }
    const ac = new AbortController();
    if (cached && isInboxCacheFresh(cached)) {
      return () => ac.abort();
    }
    void load(cached ? "soft" : "initial", ac.signal, userId);
    return () => ac.abort();
  }, [sessionLoading, userId, tab, load, navigate]);

  const showSafeChrome = sessionLoading || userId == null;
  const showSkeleton = showSafeChrome || (loading && items.length === 0);
  const empty = emptyCopy(tab);

  return (
    <div className="dm-page" data-spa-page="メッセージ">
      <PullToRefresh
        enabled={!loading && !showSafeChrome}
        onRefresh={async () => {
          if (!(await load("soft"))) throw new Error("refresh_failed");
        }}
      />
      <main className="main-inner" data-dm-inbox>
        <header className="dm-inbox-header">
          <p>DM・授業掲示板・取引チャットをまとめて確認できます。</p>
          <nav className="dm-inbox-tabs" aria-label="メッセージの種類">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                className={`dm-inbox-tab${tab === t.key ? " is-active" : ""}`}
                aria-current={tab === t.key ? "page" : undefined}
                disabled={showSafeChrome}
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

        {!showSafeChrome && requestCount > 0 ? (
          <Link className="dm-request-entry" to="/dm/requests">
            <span className="dm-request-entry__label">
              💬 メッセージリクエスト
            </span>
            <span className="dm-request-entry__count" aria-label={`${requestCount}件`}>
              {requestCount}
            </span>
          </Link>
        ) : null}

        {showSkeleton ? (
          <InboxSkeleton />
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
                  }${
                    item.kind === "group_invite" || item.kind === "recruiting_invite"
                      ? " is-invite"
                      : ""
                  }`}
                  to={inboxSpaHref(item.spa_path)}
                >
                  <span
                    className={`dm-inbox-avatar${
                      item.kind === "group" || item.kind === "group_invite"
                        ? " is-group"
                        : item.kind === "trade"
                          ? " is-trade"
                          : item.kind === "course"
                            ? " is-course"
                            : item.kind === "recruiting" ||
                                item.kind === "recruiting_invite"
                              ? " is-recruiting"
                              : ""
                    }`}
                    aria-hidden="true"
                  >
                    {avatarContent(item)}
                  </span>
                  <span className="dm-inbox-body">
                    <span className="dm-inbox-top">
                      <span className="dm-inbox-name">
                        {item.kind === "dm" && !item.is_blocked ? (
                          <AccountDisplayName
                            name={item.display_name}
                            verified={item.partner?.is_operator_verified}
                          />
                        ) : (
                          item.display_name
                        )}
                      </span>
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
                            相手:{" "}
                            <AccountDisplayName
                              name={item.partner.display_name}
                              verified={item.partner.is_operator_verified}
                            />
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
                    ) : item.kind === "group_invite" ||
                      item.kind === "recruiting_invite" ? (
                      <>
                        <span className="dm-inbox-status is-invite">
                          {item.status_label || "招待あり"}
                        </span>
                        <span className="dm-inbox-handle">{item.subtitle}</span>
                      </>
                    ) : item.kind === "recruiting" ? (
                      <>
                        <span className="dm-inbox-status is-recruiting">
                          {item.status_label || "団体チャット"}
                        </span>
                        <span className="dm-inbox-handle">{item.subtitle}</span>
                      </>
                    ) : (
                      <span className="dm-inbox-handle">{item.subtitle}</span>
                    )}
                    {item.kind === "group_invite" ||
                    item.kind === "recruiting_invite" ? (
                      <p className="dm-inbox-preview">
                        タップして参加するか辞退してください
                      </p>
                    ) : item.latest_body ? (
                      <p className="dm-inbox-preview">
                        {item.latest_sender_name ? (
                          <span className="dm-inbox-preview-prefix">
                            <AccountDisplayName
                              name={item.latest_sender_name}
                              verified={item.latest_sender_is_operator_verified}
                            />
                            :{" "}
                          </span>
                        ) : null}
                        <span className="dm-inbox-preview-text">
                          {item.latest_body}
                        </span>
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

      {userId != null ? (
        <Link
          className="dm-create-fab"
          to="/dm/new"
          aria-label="チャットを作成"
        >
          +
        </Link>
      ) : null}
    </div>
  );
}
