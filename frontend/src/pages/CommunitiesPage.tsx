import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  createCommunityThread,
  fetchCommunityThreads,
  type ThreadSummary,
} from "../features/community/api";
import {
  fetchCourseDiscover,
  type CourseDiscoverCard,
} from "../features/courses/api";
import { CourseDiscoveryPanel } from "../features/courses/CourseDiscoveryPanel";
import { FacultyFilterTabs } from "../components/FacultyFilterTabs";
import { LocalSearchBar } from "../components/LocalSearchBar";
import { useSoftTabRefetch } from "../layouts/TabKeepAliveLayout";
import { analytics } from "../lib/analytics/events";

type Hub = "community" | "courses";

export function CommunitiesPage() {
  const { me } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const hub: Hub =
    searchParams.get("hub") === "courses" ? "courses" : "community";
  const tag = searchParams.get("tag") || "";
  const qParam = searchParams.get("q") || "";
  const sort = (
    searchParams.get("sort") === "latest" ? "latest" : "recommended"
  ) as "recommended" | "latest";
  const ownFaculty = me?.user?.department || "";

  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [composeOpen, setComposeOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const hasDataRef = useRef(false);

  const [enrolled, setEnrolled] = useState<CourseDiscoverCard[]>([]);
  const [active, setActive] = useState<CourseDiscoverCard[]>([]);
  const [popular, setPopular] = useState<CourseDiscoverCard[]>([]);
  const [courseLoading, setCourseLoading] = useState(false);
  const [courseError, setCourseError] = useState<string | null>(null);
  const hasCourseDataRef = useRef(false);

  const patchParams = useCallback(
    (patch: Record<string, string>) => {
      const next = new URLSearchParams(searchParams);
      Object.entries(patch).forEach(([key, value]) => {
        if (value) next.set(key, value);
        else next.delete(key);
      });
      setSearchParams(next);
    },
    [searchParams, setSearchParams]
  );

  const setHub = (next: Hub) => {
    patchParams({ hub: next === "courses" ? "courses" : "" });
    if (next === "courses") {
      analytics.communityCourseTabOpened();
    }
  };

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
          sort,
        });
        setThreads(data.threads);
        hasDataRef.current = true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        setLoading(false);
      }
    },
    [tag, qParam, sort]
  );

  const loadCourses = useCallback(
    async (mode: "initial" | "soft" = "initial") => {
      if (mode === "initial" && !hasCourseDataRef.current) {
        setCourseLoading(true);
      }
      setCourseError(null);
      try {
        const data = await fetchCourseDiscover();
        setEnrolled(data.enrolled);
        setActive(data.active);
        setPopular(data.popular);
        hasCourseDataRef.current = true;
      } catch (err) {
        setCourseError(err instanceof Error ? err.message : "load_failed");
      } finally {
        setCourseLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (hub === "community") {
      void load(hasDataRef.current ? "soft" : "initial");
    }
  }, [hub, load]);

  useEffect(() => {
    if (hub === "courses") {
      void loadCourses(hasCourseDataRef.current ? "soft" : "initial");
    }
  }, [hub, loadCourses]);

  useEffect(() => {
    analytics.communityViewed();
  }, []);

  useSoftTabRefetch("communities", () => {
    if (hub === "courses") return loadCourses("soft");
    return load("soft");
  });

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
      analytics.communityPostCreated();
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
          {hub === "community" ? (
            me?.authenticated ? (
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
            )
          ) : null}
        </div>

        <nav className="ranking-sort-tabs" aria-label="コミュニティと授業">
          <button
            type="button"
            className={`ranking-sort-tab${hub === "community" ? " is-active" : ""}`}
            onClick={() => setHub("community")}
          >
            コミュニティ
          </button>
          <button
            type="button"
            className={`ranking-sort-tab${hub === "courses" ? " is-active" : ""}`}
            onClick={() => setHub("courses")}
          >
            授業
          </button>
        </nav>

        {hub === "community" ? (
          <>
            <FacultyFilterTabs
              value={tag}
              ownFaculty={ownFaculty}
              onChange={(next) => patchParams({ tag: next })}
            />

            <nav className="ranking-sort-tabs" aria-label="コミュニティ並び順">
              <button
                type="button"
                className={`ranking-sort-tab${sort === "recommended" ? " is-active" : ""}`}
                onClick={() => patchParams({ sort: "" })}
              >
                おすすめ
              </button>
              <button
                type="button"
                className={`ranking-sort-tab${sort === "latest" ? " is-active" : ""}`}
                onClick={() => patchParams({ sort: "latest" })}
              >
                最新
              </button>
            </nav>

            <LocalSearchBar
              value={qParam}
              placeholder="コミュニティのスレッドを検索"
              ariaLabel="コミュニティ内検索"
              onSubmit={(q) => patchParams({ q })}
              onClear={() => patchParams({ q: "" })}
            />
            {qParam ? (
              <p className="local-search-hint">
                「{qParam}」のコミュニティ検索結果（タイムライン・フリマは含みません）
              </p>
            ) : null}
          </>
        ) : (
          <p className="communities-hub-hint">
            履修中・活発・人気の授業を見つけられます
          </p>
        )}
      </div>

      {hub === "courses" ? (
        <CourseDiscoveryPanel
          enrolled={enrolled}
          active={active}
          popular={popular}
          loading={courseLoading && !hasCourseDataRef.current}
          error={courseError}
          authenticated={Boolean(me?.authenticated)}
        />
      ) : (
        <>
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
            <p className="empty-message">
              {qParam
                ? "一致するスレッドはありません。"
                : "スレッドがありません。"}
            </p>
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
        </>
      )}
    </div>
  );
}
