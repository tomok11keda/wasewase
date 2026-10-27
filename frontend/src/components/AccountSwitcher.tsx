import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import {
  accountSwitchMessage,
  shouldLeaveOrganizationEdit,
} from "../features/orgs/accountSwitch";
import {
  organizationRoleLabel,
  type ManagedOrganization,
} from "../features/orgs/managedOrganizations";
import { organizationInitial } from "../features/orgs/orgProfile";
import { switchLinkedProfile } from "../features/linkedProfiles/api";
import {
  canAddLinkedProfile,
  linkedProfilesFromMe,
  shouldOpenOwnProfileAfterSwitch,
} from "../features/linkedProfiles/linkedProfiles";
import { useAccount } from "../lib/accountContext";
import { useSession } from "../lib/session";
import { AccountAvatar } from "./AccountAvatar";
import { AccountDisplayName } from "./VerifiedAccountBadge";
import { VerifiedOrganizationBadge } from "./VerifiedOrganizationBadge";

type Props = {
  onNavigate?: () => void;
};

export function AccountSwitcher({ onNavigate }: Props) {
  const { me, setMeFromAuth } = useSession();
  const {
    actor,
    organizations,
    error,
    selectPersonal,
    selectOrganization,
    refreshOrganizations,
  } = useAccount();
  const navigate = useNavigate();
  const location = useLocation();
  const user = me?.user;
  const [toast, setToast] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const profiles = linkedProfilesFromMe(me);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 1800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  if (!user) return null;

  const finishSwitch = (nextOrgSlug: string | null, message: string) => {
    onNavigate?.();
    setToast(message);
    if (shouldLeaveOrganizationEdit(location.pathname, nextOrgSlug)) {
      navigate("/", { replace: true });
    }
  };

  const goPersonalProfile = async (profileId: number, displayName: string) => {
    if (busyId != null) return;
    if (actor.type === "personal" && profileId === user.id) {
      onNavigate?.();
      return;
    }
    if (profileId === user.id) {
      selectPersonal();
      finishSwitch(null, accountSwitchMessage(displayName));
      return;
    }
    setBusyId(profileId);
    setSwitchError(null);
    try {
      const previousId = user.id;
      const { res, data } = await switchLinkedProfile(profileId);
      if (!res.ok || !data.ok || !data.me) {
        setSwitchError(data.message || "切り替えできませんでした。");
        return;
      }
      setMeFromAuth(data.me);
      selectPersonal();
      const nextId = data.me.user?.id ?? profileId;
      finishSwitch(null, accountSwitchMessage(displayName));
      if (
        shouldOpenOwnProfileAfterSwitch(location.pathname, previousId, nextId)
      ) {
        navigate(`/users/${nextId}/posts`, { replace: true });
      }
    } catch {
      setSwitchError("切り替えできませんでした。");
    } finally {
      setBusyId(null);
    }
  };

  const goOrganization = (organization: ManagedOrganization) => {
    const alreadySelected =
      actor.type === "organization" &&
      actor.organization.id === organization.id;
    if (alreadySelected) {
      onNavigate?.();
      return;
    }
    const selected = selectOrganization(organization.id);
    if (!selected) return;
    finishSwitch(selected.slug, accountSwitchMessage(selected.name));
  };

  const personalActive = actor.type === "personal";
  const showAdd = canAddLinkedProfile(me);

  return (
    <div className="account-switcher">
      <p className="more-section-title">アカウントを切り替える</p>
      {error ? (
        <p className="account-switcher__error">
          団体一覧を読み込めませんでした。
          <button
            type="button"
            className="account-switcher__retry"
            onClick={() => void refreshOrganizations()}
          >
            再試行
          </button>
        </p>
      ) : null}
      {switchError ? (
        <p className="account-switcher__error">{switchError}</p>
      ) : null}
      <ul className="account-switcher__list">
        {profiles.map((profile) => {
          const active = personalActive && profile.id === user.id;
          return (
            <li key={profile.id}>
              <button
                type="button"
                className={`account-switcher__item${
                  active ? " is-current" : ""
                }`}
                onClick={() =>
                  void goPersonalProfile(profile.id, profile.display_name)
                }
                aria-current={active ? "true" : undefined}
                disabled={busyId != null}
              >
                <AccountAvatar
                  url={profile.avatar_url}
                  initial={profile.initial}
                  className="account-switcher__avatar"
                />
                <span className="account-switcher__meta">
                  <span className="account-switcher__name">
                    <AccountDisplayName
                      name={profile.display_name}
                      verified={
                        profile.id === user.id
                          ? user.is_operator_verified
                          : false
                      }
                    />
                  </span>
                  <span className="account-switcher__role">
                    @{profile.username}
                  </span>
                </span>
                {active ? (
                  <span className="account-switcher__check" aria-hidden="true">
                    ✓
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
        {organizations.map((organization) => {
          const active =
            actor.type === "organization" &&
            actor.organization.id === organization.id;
          return (
            <li key={`org-${organization.id}`}>
              <button
                type="button"
                className={`account-switcher__item${
                  active ? " is-current" : ""
                }`}
                onClick={() => goOrganization(organization)}
                aria-current={active ? "true" : undefined}
              >
                <AccountAvatar
                  url={organization.avatar_url}
                  initial={organizationInitial(organization.name)}
                  className="account-switcher__avatar"
                />
                <span className="account-switcher__meta">
                  <span className="account-switcher__name">
                    {organization.name}
                    <VerifiedOrganizationBadge
                      verified={organization.is_verified}
                    />
                  </span>
                  <span className="account-switcher__role">
                    {organizationRoleLabel(organization.my_role)}
                  </span>
                </span>
                {active ? (
                  <span className="account-switcher__check" aria-hidden="true">
                    ✓
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
      {showAdd ? (
        <button
          type="button"
          className="account-switcher__add"
          onClick={() => {
            onNavigate?.();
            navigate("/settings/linked-account");
          }}
        >
          アカウントを追加
        </button>
      ) : null}
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
    </div>
  );
}
