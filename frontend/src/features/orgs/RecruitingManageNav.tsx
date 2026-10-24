import { NavLink } from "react-router-dom";
import {
  recruitingChatApplicationsPath,
  recruitingChatInfoPath,
  recruitingChatMembersPath,
  recruitingChatPath,
  recruitingChatSettingsPath,
} from "./recruitingChat";

type Props = {
  slug: string;
  pendingCount?: number;
};

export function RecruitingManageNav({ slug, pendingCount }: Props) {
  return (
    <nav className="org-recruiting-manage-nav" aria-label="新歓チャット管理">
      <NavLink to={recruitingChatPath(slug)} end>
        チャット
      </NavLink>
      <NavLink to={recruitingChatInfoPath(slug)}>詳細</NavLink>
      <NavLink to={recruitingChatSettingsPath(slug)}>設定</NavLink>
      <NavLink to={recruitingChatApplicationsPath(slug)}>
        申請管理
        {typeof pendingCount === "number" && pendingCount > 0
          ? `（${pendingCount}）`
          : ""}
      </NavLink>
      <NavLink to={recruitingChatMembersPath(slug)}>参加者管理</NavLink>
    </nav>
  );
}
