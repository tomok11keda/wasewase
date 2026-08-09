import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  createCommunityThread,
  fetchCommunityThreads,
  type ThreadSummary,
} from "../features/community/api";
import { FacultyFilterTabs } from "../components/FacultyFilterTabs";
import { useSoftTabRefetch } from "../layouts/TabKeepAliveLayout";

export function CommunitiesPage() {
  const { me } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tag = searchParams.get("tag") || "";
  const qParam = searchParams.get("q") || "";
  const ownFaculty = me?.user?.department || "";

  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [qInput, setQInput] = useState(qParam);
  const [composeOpen, setComposeOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const hasDataRef = useRef(false);

  const load = useCallback(
    async (mode: "initial" | "soft" = "initial") => {
      if (mode === "initial" && !hasDataRef.current) {
        setLoading(true);
      }
      setError(null);
      try {
        const data = await fetchCommunityThreads({
          tag: tag || undefined,
          q: qParam || undefined,
        });
        setThreads(data.threads);
        hasDataRef.current = true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        setLoading(false);
      }
    },
    [tag, qParam]
  );

  useEffect(() => {
    void load(hasDataRef.current ? "soft" : "initial");
  }, [load]);

  useSoftTabRefetch("communities", () => load("soft"));

  useEffect(() => {
    setQInput(qParam);
  }, [qParam]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (tag) next.set("tag", tag);
    if (qInput.trim()) next.set("q", qInput.trim());
    setSearchParams(next);
  };

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/communities"));
      return;
    }
    setBusy(true);
    try {
      const thread = await createCommunityThread({
        title: title.trim(),
        body: body.trim(),
        tag: tag || undefined,
      });
      setThreads((prev) => [thread, ...prev]);
      setTitle("");
      setBody("");
      setComposeOpen(false);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "作成に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-spa-page="コミュニティ">
      <div className="communities-header">
        <div className="communities-header-top">
          <h2>コミュニティ</h2>
          {me?.authenticated ? (
            <button
              type="button"
              className="btn-new-thread"
              onClick={() => setComposeOpen((v) => !v)}
            >
              新規スレッド
            </button>
          ) : (
            <Link
              className="btn-new-thread"
              to={spaLoginPath("/app/communities")}
              style={{ display: "inline-flex", alignItems: "center" }}
            >
              ログインして投稿
            </Link>
          )}
        </div>

        <FacultyFilterTabs
          value={tag}
          ownFaculty={ownFaculty}
          onChange={(next) => {
            const params = new URLSearchParams();
            if (next) params.set("tag", next);
            if (qParam) params.set("q", qParam);
            setSearchParams(params);
          }}
        />

        <form className="communities-search" onSubmit={onSearch}>
          <input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder="スレッドを検索"
            aria-label="スレッド検索"
          />
          <button type="submit">検索</button>
        </form>
      </div>

      {composeOpen ? (
        <form className="community-compose" onSubmit={onCreate}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={120}
            placeholder="スレッドタイトル"
            required
          />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={2000}
            rows={5}
            placeholder="相談内容や共有したいことを書いてください"
            required
          />
          <button type="submit" disabled={busy}>
            作成する
          </button>
        </form>
      ) : null}

      {loading && threads.length === 0 ? (
        <p className="empty-message">読み込み中…</p>
      ) : error && threads.length === 0 ? (
        <p className="empty-message">読み込みに失敗しました（{error}）</p>
      ) : threads.length === 0 ? (
        <p className="empty-message">スレッドがありません。</p>
      ) : (
        <ul className="thread-list">
          {threads.map((thread) => (
            <li key={thread.id}>
              <Link
                className="thread-card"
                to={`/communities/${thread.community.slug}/threads/${thread.id}`}
              >
                <h3 className="thread-card__title">{thread.title}</h3>
                <p className="thread-card__meta">
                  {thread.author?.display_name || "ユーザー"} · 返信{" "}
                  {thread.replies_count}
                </p>
                <p className="thread-card__preview">{thread.body_preview}</p>
                <span className="thread-card__board">
                  {thread.community.name}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
