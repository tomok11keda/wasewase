import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShellLayout } from "./layouts/AppShellLayout";
import {
  MainTabRoute,
  TabKeepAliveLayout,
} from "./layouts/TabKeepAliveLayout";
import { AuthLayout } from "./layouts/AuthLayout";
import { SessionProvider } from "./lib/session";
import { PostHogIdentitySync } from "./lib/analytics/PostHogAppProvider";
import { NativeSpaBridge } from "./components/NativeSpaBridge";
import { UnauthorizedRedirect } from "./components/UnauthorizedRedirect";
import { CommunityThreadPage } from "./pages/CommunityThreadPage";
import { DmInboxPage } from "./pages/DmInboxPage";
import { DmRoomPage } from "./pages/DmRoomPage";
import { MessageRequestsPage } from "./pages/MessageRequestsPage";
import { ExhibitPage } from "./pages/ExhibitPage";
import { GroupCreatePage } from "./pages/GroupCreatePage";
import { GroupRoomPage } from "./pages/GroupRoomPage";
import { LoginPage } from "./pages/LoginPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import {
  PasswordResetRequestPage,
  PasswordResetSetPage,
  PasswordResetVerifyPage,
} from "./pages/PasswordResetPages";
import { ProductDetailPage } from "./pages/ProductDetailPage";
import { ProfilePage } from "./pages/ProfilePage";
import { SearchPage } from "./pages/SearchPage";
import { SignupPage } from "./pages/SignupPage";
import { TimetablePage } from "./pages/TimetablePage";
import { CourseDetailPage } from "./pages/CourseDetailPage";
import { TradeChatPage } from "./pages/TradeChatPage";
import { VerifyOtpPage } from "./pages/VerifyOtpPage";
import { CommunitiesPage } from "./pages/CommunitiesPage";
import { FleaPage } from "./pages/FleaPage";
import { HomePage } from "./pages/HomePage";
import { MorePage } from "./pages/tabs";
import { SettingsPage } from "./pages/SettingsPage";
import { FollowRequestsPage } from "./pages/FollowRequestsPage";
import { useSpaNavDiag } from "./lib/spaNavDiag";

const BASENAME = "/app";

function SpaRuntimeHooks() {
  return (
    <>
      <PostHogIdentitySync />
      <UnauthorizedRedirect />
      <NativeSpaBridge />
    </>
  );
}

function NestedAppRoutes() {
  return (
    <>
      <Route
        path="communities/:slug/threads/:threadPk"
        element={<CommunityThreadPage />}
      />
      <Route path="flea/exhibit" element={<ExhibitPage />} />
      <Route path="flea/products/:pk" element={<ProductDetailPage />} />
      <Route path="flea/chats/:roomPk" element={<TradeChatPage />} />
      <Route path="timetable/user/:userPk" element={<TimetablePage />} />
      <Route path="courses/:offeringPk" element={<CourseDetailPage />} />
      <Route path="users/:userId" element={<ProfilePage />} />
      <Route path="users/:userId/:tab" element={<ProfilePage />} />
      <Route path="notifications" element={<NotificationsPage />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="settings/follow-requests" element={<FollowRequestsPage />} />
      <Route path="dm" element={<DmInboxPage />} />
      <Route path="dm/requests" element={<MessageRequestsPage />} />
      <Route path="dm/groups/new" element={<GroupCreatePage />} />
      <Route path="dm/groups/:roomPk" element={<GroupRoomPage />} />
      <Route path="dm/:roomPk" element={<DmRoomPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </>
  );
}

/** Must be a component under BrowserRouter (hooks need Router context). */
function AppRoutes() {
  const diag = useSpaNavDiag();

  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="login" element={<LoginPage />} />
        <Route path="signup" element={<SignupPage />} />
        <Route path="verify" element={<VerifyOtpPage />} />
        <Route path="password-reset" element={<PasswordResetRequestPage />} />
        <Route
          path="password-reset/verify"
          element={<PasswordResetVerifyPage />}
        />
        <Route path="password-reset/set" element={<PasswordResetSetPage />} />
      </Route>

      {diag.disableKeepAlive ? (
        <Route element={<AppShellLayout />}>
          <Route index element={<HomePage />} />
          <Route path="communities" element={<CommunitiesPage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="flea" element={<FleaPage />} />
          <Route path="timetable" element={<TimetablePage />} />
          <Route path="more" element={<MorePage />} />
          {NestedAppRoutes()}
        </Route>
      ) : (
        <Route element={<AppShellLayout />}>
          <Route element={<TabKeepAliveLayout />}>
            <Route index element={<MainTabRoute />} />
            <Route path="communities" element={<MainTabRoute />} />
            <Route path="search" element={<MainTabRoute />} />
            <Route path="flea" element={<MainTabRoute />} />
            <Route path="timetable" element={<MainTabRoute />} />
            <Route path="more" element={<MorePage />} />
            {NestedAppRoutes()}
          </Route>
        </Route>
      )}
    </Routes>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <BrowserRouter basename={BASENAME}>
        <SpaRuntimeHooks />
        <AppRoutes />
      </BrowserRouter>
    </SessionProvider>
  );
}
