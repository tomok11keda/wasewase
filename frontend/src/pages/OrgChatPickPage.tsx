import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ListRowSkeleton } from "../components/skeleton";
import { VerifiedOrganizationBadge } from "../components/VerifiedOrganizationBadge";
import { spaLoginPath } from "../features/auth/api";
import {
  organizationInitial,
} from "../features/orgs/orgProfile";
import {
  ORG_CHAT_PICK_LEAD,
  organizationRoleLabel,
  organizationsForChatPick,
  type ManagedOrganization,
} from "../features/orgs/managedOrganizations";
import {
  recruitingChatErrorMessage,
  resolveRecruitingChatDestination,
} from "../features/orgs/recruitingChat";
import { fetchRecruitingChat } from "../features/orgs/recruitingChatApi";
import { OrganizationRequestError } from "../features/orgs/api";
import { useAccount } from "../lib/accountContext";
import { useSession } from "../lib/session";

function errorText(err: unknown): string {
  if (err instanceof OrganizationRequestError) {
    return err.message;
  }
  if (err instanceof Error && err.message) {
    return recruitingChatErrorMessage(err.message, err.message);
  }
  return "団体チャットを開けませんでした。";
}

export function OrgChatPickPage() {
  const { me, loading: sessionLoading } = useSession();
  const {
    actor,
    organizations,
    loading,
    error,
    refreshOrganizations,
  } = useAccount();
  const navigate = useNavigate();
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/dm/new/org-chat"), { replace: true });
    }
  }, [sessionLoading, me?.authenticated, navigate]);

  const currentId =
    actor.type === "organization" ? actor.organization.id : null;
  const sorted = useMemo(
    () => organizationsForChatPick(organizations, currentId),
    [organizations, currentId]
  );

  const pick = async (organization: ManagedOrganization) => {
    if (busySlug) return;
    setBusySlug(organization.slug);
    setActionError(null);
    try {
      const envelope = await fetchRecruitingChat(organization.slug);
      const dest = resolveRecruitingChatDestination(envelope, organization.slug);
      if (!dest) {
        setActionError("この団体の団体チャットを作成または開く権限がありません。");
        return;
      }
      navigate(dest.path);
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusySlug(null);
    }
  };

  return (
    <div className="dm-page" data-spa-page="団体チャット">
      <main className="main-inner" aria-label="団体チャット">
        <div className="dm-group-header">
          <p>
            {ORG_CHAT_PICK_LEAD}
          </p>
        </div>
        {actor.type === "organization" ? (
          <p className="org-chat-pick-current" role="status">
            現在は「{actor.organization.name}」として操作しています。
          </p>
        ) : null}
        {actionError ? (
          <p className="org-edit-error" role="alert">
            {actionError}
          </p>
        ) : null}
        {error ? (
          <p className="dm-empty">
            団体一覧を読み込めませんでした。
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void refreshOrganizations()}
            >
              再試行
            </button>
          </p>
        ) : null}
        {loading && organizations.length === 0 ? (
          <ListRowSkeleton rows={3} />
        ) : organizations.length === 0 ? (
          <p className="dm-empty">
            管理している団体がありません。団体のownerまたはadminだけが団体チャットを作成できます。
          </p>
        ) : (
          <ul className="org-chat-pick-list">
            {sorted.map((organization) => {
              const selected = organization.id === currentId;
              return (
                <li key={organization.id}>
                  <button
                    type="button"
                    className={`org-chat-pick-item${selected ? " is-current" : ""}`}
                    disabled={busySlug != null}
                    onClick={() => void pick(organization)}
                  >
                    {organization.avatar_url ? (
                      <img
                        className="org-chat-pick-avatar"
                        src={organization.avatar_url}
                        alt=""
                      />
                    ) : (
                      <span className="org-chat-pick-avatar org-chat-pick-avatar--icon">
                        {organizationInitial(organization.name)}
                      </span>
                    )}
                    <span className="org-chat-pick-meta">
                      <span className="org-chat-pick-name">
                        {organization.name}
                        <VerifiedOrganizationBadge
                          verified={organization.is_verified}
                        />
                      </span>
                      <span className="org-chat-pick-role">
                        {organizationRoleLabel(organization.my_role)}
                      </span>
                      {selected ? (
                        <span className="org-chat-pick-selected">現在選択中</span>
                      ) : null}
                    </span>
                    <span className="org-chat-pick-action">
                      {busySlug === organization.slug ? "確認中…" : "開く"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <p className="dm-group-actions">
          <Link className="dm-btn dm-btn-ghost" to="/dm/new">
            戻る
          </Link>
        </p>
      </main>
    </div>
  );
}
