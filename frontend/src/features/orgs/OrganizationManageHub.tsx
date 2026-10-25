import { Link } from "react-router-dom";
import {
  organizationEventManagePath,
  organizationEventNewPath,
} from "./orgEvents";
import {
  recruitingChatApplicationsPath,
  recruitingChatInvitesPath,
  recruitingChatPath,
  recruitingChatSettingsPath,
  type RecruitingChatEnvelope,
} from "./recruitingChat";

type Props = {
  slug: string;
  canManage: boolean;
  recruiting: RecruitingChatEnvelope | null;
  onComposeAsOrg: () => void;
};

export function OrganizationManageHub({
  slug,
  canManage,
  recruiting,
  onComposeAsOrg,
}: Props) {
  if (!canManage) return null;
  const chat = recruiting?.recruiting_chat ?? null;
  const canCreate = Boolean(recruiting?.can_create);
  const pending = chat?.pending_count;

  return (
    <section className="org-recruiting-card org-manage-hub" aria-label="団体の管理">
      <h2 className="org-recruiting-card__title">団体の管理</h2>
      <p className="org-recruiting-card__lead">
        プロフィール・投稿・イベント・団体チャットをここから操作できます。
      </p>
      <ul className="org-manage-hub__list">
        <li>
          <Link className="org-manage-hub__link" to={`/orgs/${slug}/edit`}>
            団体プロフィールを編集
          </Link>
        </li>
        <li>
          <button
            type="button"
            className="org-manage-hub__link"
            onClick={onComposeAsOrg}
          >
            団体名義で投稿する
          </button>
        </li>
        <li>
          <Link className="org-manage-hub__link" to={organizationEventNewPath(slug)}>
            イベントを作成
          </Link>
        </li>
        <li>
          <Link className="org-manage-hub__link" to={organizationEventManagePath(slug)}>
            イベント管理
          </Link>
        </li>
        {chat ? (
          <>
            <li>
              <Link className="org-manage-hub__link" to={recruitingChatPath(slug)}>
                団体チャットを開く
              </Link>
            </li>
            <li>
              <Link
                className="org-manage-hub__link"
                to={recruitingChatSettingsPath(slug)}
              >
                団体チャット設定
              </Link>
            </li>
            <li>
              <Link
                className="org-manage-hub__link"
                to={recruitingChatApplicationsPath(slug)}
              >
                参加申請を管理
                {typeof pending === "number" && pending > 0 ? `（${pending}）` : ""}
              </Link>
            </li>
            <li>
              <Link
                className="org-manage-hub__link"
                to={recruitingChatInvitesPath(slug)}
              >
                学生を招待
              </Link>
            </li>
          </>
        ) : canCreate ? (
          <li>
            <Link
              className="org-manage-hub__link"
              to={recruitingChatSettingsPath(slug)}
            >
              団体チャットを作成
            </Link>
          </li>
        ) : null}
      </ul>
    </section>
  );
}
