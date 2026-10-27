import { NavLink } from "react-router-dom";
import {
  recruitingChatApplicationsPath,
  recruitingChatInfoPath,
  recruitingChatInvitesPath,
  recruitingChatMembersPath,
  recruitingChatPath,
  recruitingChatSettingsPath,
} from "./recruitingChat";

type Props = {
  slug: string;
  chatId?: number | null;
  pendingCount?: number;
};

export function RecruitingManageNav({ slug, chatId, pendingCount }: Props) {
  return (
    <nav className="org-recruiting-manage-nav" aria-label="団体チャット管理">
      <NavLink to={recruitingChatPath(slug, chatId)} end>
        チャット
      </NavLink>
      <NavLink to={recruitingChatInfoPath(slug, chatId)}>詳細</NavLink>
      <NavLink to={recruitingChatSettingsPath(slug, chatId)}>設定</NavLink>
      <NavLink to={recruitingChatApplicationsPath(slug, chatId)}>
        申請管理
        {typeof pendingCount === "number" && pendingCount > 0
          ? `（${pendingCount}）`
          : ""}
      </NavLink>
      <NavLink to={recruitingChatMembersPath(slug, chatId)}>参加者管理</NavLink>
      <NavLink to={recruitingChatInvitesPath(slug, chatId)}>学生を招待</NavLink>
    </nav>
  );
}
