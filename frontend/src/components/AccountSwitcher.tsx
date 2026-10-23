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
import { useAccount } from "../lib/accountContext";
import { useSession } from "../lib/session";
import { AccountAvatar } from "./AccountAvatar";
import { AccountDisplayName } from "./VerifiedAccountBadge";
import { VerifiedOrganizationBadge } from "./VerifiedOrganizationBadge";

type Props = {
  onNavigate?: () => void;
};

export function AccountSwitcher({ onNavigate }: Props) {
  const { me } = useSession();
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

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 1800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  if (!user) return null;
  if (organizations.length === 0 && !error) return null;

  const finishSwitch = (nextOrgSlug: string | null, message: string) => {
    onNavigate?.();
    setToast(message);
    if (shouldLeaveOrganizationEdit(location.pathname, nextOrgSlug)) {
      navigate("/", { replace: true });
    }
  };

  const goPersonal = () => {
    if (actor.type === "personal") {
      onNavigate?.();
      return;
    }
    selectPersonal();
    finishSwitch(null, accountSwitchMessage("個人アカウント"));
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
      <ul className="account-switcher__list">
        <li>
          <button
            type="button"
            className={`account-switcher__item${
              personalActive ? " is-current" : ""
            }`}
            onClick={goPersonal}
            aria-current={personalActive ? "true" : undefined}
          >
            <AccountAvatar
              url={user.avatar_url}
              initial={user.initial}
              className="account-switcher__avatar"
            />
            <span className="account-switcher__meta">
              <span className="account-switcher__name">
                <AccountDisplayName
                  name={user.display_name}
                  verified={user.is_operator_verified}
                />
              </span>
              <span className="account-switcher__role">個人アカウント</span>
            </span>
            {personalActive ? (
              <span className="account-switcher__check" aria-hidden="true">
                ✓
              </span>
            ) : null}
          </button>
        </li>
        {organizations.map((organization) => {
          const active =
            actor.type === "organization" &&
            actor.organization.id === organization.id;
          return (
            <li key={organization.id}>
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
