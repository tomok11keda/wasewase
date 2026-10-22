import { useNavigate } from "react-router-dom";
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

export const PERSONAL_POSTING_NOTE =
  "現在、投稿は個人アカウントから行われます。";

export function PersonalPostingNote({ className }: { className?: string }) {
  return (
    <p className={className || "account-switcher__note"}>
      {PERSONAL_POSTING_NOTE}
    </p>
  );
}

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
  const user = me?.user;

  if (!user) return null;
  if (organizations.length === 0 && !error) return null;

  const goPersonal = () => {
    selectPersonal();
    onNavigate?.();
    navigate(`/users/${user.id}/posts`);
  };

  const goOrganization = (organization: ManagedOrganization) => {
    const selected = selectOrganization(organization.id);
    if (!selected) return;
    onNavigate?.();
    navigate(`/orgs/${selected.slug}`);
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
      {actor.type === "organization" ? <PersonalPostingNote /> : null}
    </div>
  );
}
