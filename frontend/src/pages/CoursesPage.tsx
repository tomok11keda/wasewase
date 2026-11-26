import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import {
  fetchCourseDiscover,
  type CourseDiscoverCard,
} from "../features/courses/api";
import { CourseDiscoveryPanel } from "../features/courses/CourseDiscoveryPanel";
import {
  useActiveMainTab,
  useSoftTabRefetch,
} from "../layouts/TabKeepAliveLayout";
import { analytics } from "../lib/analytics/events";
import { listContentPhase } from "../lib/listContentPhase";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";
import { isBrowsePreview, useSession } from "../lib/session";
import { PullToRefresh } from "../lib/usePullToRefresh";

/**
 * Bottom-nav「授業」tab — course discovery hub.
 * Detail routes stay at /courses/:id (not this page).
 */
export function CoursesPage() {
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const activeTab = useActiveMainTab();
  const [enrolled, setEnrolled] = useState<CourseDiscoverCard[]>([]);
  const [active, setActive] = useState<CourseDiscoverCard[]>([]);
  const [popular, setPopular] = useState<CourseDiscoverCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const hasDataRef = useRef(false);
  const requestIdRef = useRef(0);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const prevUserIdRef = useRef(sessionUserId);

  const load = useCallback(
    async (mode: "initial" | "soft" = "initial") => {
      const requestId = nextRequestId(requestIdRef);
      const startedUserId = userIdRef.current;
      if (browsePreview) {
        setEnrolled([]);
        setActive([]);
        setPopular([]);
        setError(null);
        setLoading(false);
        hasDataRef.current = false;
        return true;
      }
      if (mode === "initial" && !hasDataRef.current) {
        setLoading(true);
      }
      if (mode !== "soft") setError(null);
      try {
        const data = await fetchCourseDiscover();
        if (!isLatestRequest(requestIdRef, requestId)) return false;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return false;
        setEnrolled(data.enrolled);
        setActive(data.active);
        setPopular(data.popular);
        hasDataRef.current = true;
        setError(null);
        return true;
      } catch (err) {
        if (!isLatestRequest(requestIdRef, requestId)) return false;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return false;
        if (mode === "soft") return false;
        setError(err instanceof Error ? err.message : "load_failed");
        return false;
      } finally {
        if (isLatestRequest(requestIdRef, requestId)) {
          setLoading(false);
        }
      }
    },
    [browsePreview]
  );

  useEffect(() => {
    if (prevUserIdRef.current === sessionUserId) return;
    prevUserIdRef.current = sessionUserId;
    nextRequestId(requestIdRef);
    hasDataRef.current = false;
    setEnrolled([]);
    setActive([]);
    setPopular([]);
    setError(null);
  }, [sessionUserId]);

  useEffect(() => {
    if (sessionLoading) return;
    void load(hasDataRef.current ? "soft" : "initial");
  }, [sessionLoading, load]);

  useEffect(() => {
    analytics.communityCourseTabOpened();
  }, []);

  useSoftTabRefetch("courses", () => {
    void load("soft");
  });

  const phase = listContentPhase({
    browsePreview,
    loading: sessionLoading || loading,
    error,
    itemCount: enrolled.length + active.length + popular.length || 1,
    matchesCurrentQuery: true,
  });

  return (
    <div
      className="courses-tab-page ptr-shift"
      data-spa-page="授業"
      data-tab-active={activeTab === "courses" ? "1" : "0"}
    >
      <PullToRefresh
        enabled={!browsePreview && activeTab === "courses"}
        onRefresh={async () => {
          const ok = await load("soft");
          if (!ok) throw new Error("refresh_failed");
        }}
      />
      <div className="main-inner">
        <header className="courses-tab-header">
          <h2 className="courses-tab-title">授業</h2>
          <p className="courses-tab-lead">
            履修中の授業、活発なトーク、人気の口コミを探せます。時間割への登録は時間割タブから。
          </p>
          <div className="courses-tab-actions">
            <Link className="courses-tab-link" to="/timetable">
              時間割を開く
            </Link>
            <Link className="courses-tab-link" to="/search?tab=courses">
              授業を検索
            </Link>
            <Link className="courses-tab-link courses-tab-link--muted" to="/communities">
              コミュニティで相談
            </Link>
          </div>
        </header>

        {browsePreview ? (
          <BrowsePreviewNotice nextPath="/app/courses">
            授業の発見はログイン後に利用できます。
          </BrowsePreviewNotice>
        ) : (
          <CourseDiscoveryPanel
            enrolled={enrolled}
            active={active}
            popular={popular}
            loading={phase === "skeleton"}
            error={error}
            authenticated={Boolean(me?.authenticated)}
          />
        )}
      </div>
    </div>
  );
}
