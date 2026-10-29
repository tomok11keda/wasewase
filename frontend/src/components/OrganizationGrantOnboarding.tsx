import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { fetchNotifications } from "../features/notifications/api";
import { accountSwitchMessage } from "../features/orgs/accountSwitch";
import {
  markOrgGrantPromptSeen,
  orgGrantGuidanceMessage,
  orgGrantSlugFromNotification,
  ORG_GRANT_LATER_LABEL,
  ORG_GRANT_PROMPT_TITLE,
  ORG_GRANT_SWITCH_LABEL,
  parseOrgGrantLocation,
  pickUnseenOrgGrantNotification,
  readSeenOrgGrantNotificationIds,
  shouldShowOrganizationGrantPrompt,
  stripOrgGrantSearch,
  type OrgGrantCandidate,
} from "../features/orgs/orgGrantPrompt";
import { useAccount } from "../lib/accountContext";
import { useSession } from "../lib/session";

export function OrganizationGrantOnboarding() {
  const { me, loading: sessionLoading } = useSession();
  const {
    actor,
    organizations,
    loading: organizationsLoading,
    selectOrganization,
    refreshOrganizations,
  } = useAccount();
  const location = useLocation();
  const navigate = useNavigate();
  const titleId = useId();
  const userId = me?.authenticated ? me.user?.id ?? null : null;
  const grantLocation = parseOrgGrantLocation(
    location.pathname,
    location.search
  );
  const grantSlug = grantLocation?.slug ?? null;
  const [unseen, setUnseen] = useState<OrgGrantCandidate | null>(null);
  const [guidance, setGuidance] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const handledGrantSlugRef = useRef<string | null>(null);
  const fetchGenRef = useRef(0);

  const activeOrganizationSlug =
    actor.type === "organization" ? actor.organization.slug : null;

  const loadUnseen = useCallback(async (forUserId: number) => {
    const gen = ++fetchGenRef.current;
    try {
      const data = await fetchNotifications(false);
      if (gen !== fetchGenRef.current) return;
      const seen = readSeenOrgGrantNotificationIds(forUserId);
      setUnseen(pickUnseenOrgGrantNotification(data.notifications, seen));
    } catch {
      if (gen !== fetchGenRef.current) return;
      setUnseen(null);
    }
  }, []);

  useEffect(() => {
    if (sessionLoading) return;
    if (userId == null) {
      fetchGenRef.current += 1;
      handledGrantSlugRef.current = null;
      setUnseen(null);
      setGuidance(null);
      return;
    }
    if ((me?.unread_notifications ?? 0) <= 0) return;
    void loadUnseen(userId);
  }, [loadUnseen, me?.unread_notifications, sessionLoading, userId]);

  const markSlugSeen = useCallback(async (forUserId: number, slug: string) => {
    try {
      const data = await fetchNotifications(false);
      for (const item of data.notifications) {
        if (orgGrantSlugFromNotification(item) === slug) {
          markOrgGrantPromptSeen(forUserId, item.id);
        }
      }
      setUnseen(
        pickUnseenOrgGrantNotification(
          data.notifications,
          readSeenOrgGrantNotificationIds(forUserId)
        )
      );
    } catch {
      /* keep current unseen */
    }
  }, []);

  const stripGrantQuery = useCallback(() => {
    const nextSearch = stripOrgGrantSearch(location.search);
    if (nextSearch === (location.search || "")) return;
    navigate(
      {
        pathname: location.pathname,
        search: nextSearch,
        hash: location.hash,
      },
      { replace: true, state: location.state }
    );
  }, [
    location.hash,
    location.pathname,
    location.search,
    location.state,
    navigate,
  ]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 1800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (sessionLoading || userId == null || !grantSlug) return;
    const handledKey = `${userId}:${grantSlug}`;
    if (handledGrantSlugRef.current === handledKey) return;
    let cancelled = false;
    void (async () => {
      const list = await refreshOrganizations();
      if (cancelled) return;
      handledGrantSlugRef.current = handledKey;
      const match = list.find(
        (item) => item.slug === grantSlug && item.can_manage
      );
      if (match) {
        const switched = selectOrganization(match.id);
        if (switched) {
          setToast(accountSwitchMessage(switched.name));
          setGuidance(null);
        } else {
          setGuidance(orgGrantGuidanceMessage(list.length > 0));
        }
      } else {
        setGuidance(orgGrantGuidanceMessage(list.length > 0));
      }
      await markSlugSeen(userId, grantSlug);
      if (!cancelled) stripGrantQuery();
    })();
    return () => {
      cancelled = true;
    };
  }, [
    grantSlug,
    markSlugSeen,
    refreshOrganizations,
    selectOrganization,
    sessionLoading,
    stripGrantQuery,
    userId,
  ]);

  const visible = shouldShowOrganizationGrantPrompt({
    authenticated: Boolean(me?.authenticated),
    onboardingRequired: Boolean(me?.onboarding_required),
    pathname: location.pathname || "/",
    organizationsLoading: sessionLoading || organizationsLoading,
    organizations,
    activeOrganizationSlug,
    unseen,
    handlingGrantLocation: Boolean(grantSlug) || Boolean(guidance),
  });

  const targetOrg = unseen
    ? organizations.find(
        (item) => item.slug === unseen.slug && item.can_manage
      )
    : null;

  const onLater = () => {
    if (userId == null || unseen == null) return;
    markOrgGrantPromptSeen(userId, unseen.id);
    setUnseen(null);
  };

  const onSwitch = () => {
    if (userId == null || unseen == null || targetOrg == null) return;
    const switched = selectOrganization(targetOrg.id);
    markOrgGrantPromptSeen(userId, unseen.id);
    setUnseen(null);
    if (switched) setToast(accountSwitchMessage(switched.name));
  };

  return (
    <>
      {visible && targetOrg
        ? createPortal(
            <div className="push-preperm org-grant-prompt" role="presentation">
              <button
                type="button"
                className="push-preperm__backdrop"
                aria-label="閉じる"
                onClick={onLater}
              />
              <div
                className="push-preperm__panel"
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
              >
                <h2 id={titleId} className="push-preperm__title">
                  {ORG_GRANT_PROMPT_TITLE}
                </h2>
                <p className="push-preperm__body">
                  {targetOrg.name}の管理権限が付与されました
                </p>
                <button
                  type="button"
                  className="push-preperm__primary"
                  onClick={onSwitch}
                >
                  {ORG_GRANT_SWITCH_LABEL}
                </button>
                <button
                  type="button"
                  className="push-preperm__secondary"
                  onClick={onLater}
                >
                  {ORG_GRANT_LATER_LABEL}
                </button>
              </div>
            </div>,
            document.body
          )
        : null}
      {guidance
        ? createPortal(
            <div className="push-preperm org-grant-prompt" role="presentation">
              <button
                type="button"
                className="push-preperm__backdrop"
                aria-label="閉じる"
                onClick={() => setGuidance(null)}
              />
              <div
                className="push-preperm__panel"
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
              >
                <h2 id={titleId} className="push-preperm__title">
                  団体アカウント
                </h2>
                <p className="push-preperm__body">{guidance}</p>
                <button
                  type="button"
                  className="push-preperm__primary"
                  onClick={() => setGuidance(null)}
                >
                  閉じる
                </button>
              </div>
            </div>,
            document.body
          )
        : null}
      {toast
        ? createPortal(
            <div
              className="share-toast account-switch-toast"
              role="status"
              aria-live="polite"
            >
              {toast}
            </div>,
            document.body
          )
        : null}
    </>
  );
}
