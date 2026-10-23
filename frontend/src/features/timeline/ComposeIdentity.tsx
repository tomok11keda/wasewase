import { AccountDisplayName } from "../../components/VerifiedAccountBadge";
import { VerifiedOrganizationBadge } from "../../components/VerifiedOrganizationBadge";
import { organizationInitial } from "../orgs/orgProfile";
import {
  composeModeCaption,
  type ComposeActorSnapshot,
} from "./composeActor";

export function ComposeIdentity({
  actor,
  personalName,
  personalAvatarUrl,
  personalInitial,
  personalVerified,
}: {
  actor: ComposeActorSnapshot;
  personalName: string;
  personalAvatarUrl?: string;
  personalInitial?: string;
  personalVerified?: boolean | null;
}) {
  if (actor.type === "organization") {
    const org = actor.organization;
    return (
      <div className="spa-compose__identity" data-compose-actor="organization">
        {org.avatar_url ? (
          <img className="spa-compose__identity-avatar" src={org.avatar_url} alt="" />
        ) : (
          <span className="spa-compose__identity-avatar is-initial" aria-hidden="true">
            {organizationInitial(org.name)}
          </span>
        )}
        <div className="spa-compose__identity-text">
          <strong className="account-verified-name">
            <span className="account-verified-name__text">{org.name}</span>
            <VerifiedOrganizationBadge verified={org.is_verified} compact />
          </strong>
          <p>{composeModeCaption(actor)}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="spa-compose__identity" data-compose-actor="personal">
      {personalAvatarUrl ? (
        <img
          className="spa-compose__identity-avatar"
          src={personalAvatarUrl}
          alt=""
        />
      ) : (
        <span className="spa-compose__identity-avatar is-initial" aria-hidden="true">
          {personalInitial || "?"}
        </span>
      )}
      <div className="spa-compose__identity-text">
        <strong>
          <AccountDisplayName name={personalName} verified={personalVerified} />
        </strong>
        <p>{composeModeCaption(actor)}</p>
      </div>
    </div>
  );
}
