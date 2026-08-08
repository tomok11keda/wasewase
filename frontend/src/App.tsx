import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShellLayout } from "./layouts/AppShellLayout";
import { AuthLayout } from "./layouts/AuthLayout";
import { SessionProvider } from "./lib/session";
import { NativeSpaBridge } from "./components/NativeSpaBridge";
import { UnauthorizedRedirect } from "./components/UnauthorizedRedirect";
import { CommunitiesPage } from "./pages/CommunitiesPage";
import { CommunityThreadPage } from "./pages/CommunityThreadPage";
import { DmInboxPage } from "./pages/DmInboxPage";
import { DmRoomPage } from "./pages/DmRoomPage";
import { ExhibitPage } from "./pages/ExhibitPage";
import { FleaPage } from "./pages/FleaPage";
import { GroupCreatePage } from "./pages/GroupCreatePage";
import { GroupRoomPage } from "./pages/GroupRoomPage";
import { HomePage } from "./pages/HomePage";
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
import { TradeChatPage } from "./pages/TradeChatPage";
import { VerifyOtpPage } from "./pages/VerifyOtpPage";
import { MorePage } from "./pages/tabs";

const BASENAME = "/app";

function SpaRuntimeHooks() {
  return (
    <>
      <UnauthorizedRedirect />
      <NativeSpaBridge />
    </>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <BrowserRouter basename={BASENAME}>
        <SpaRuntimeHooks />
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

          <Route element={<AppShellLayout />}>
            <Route index element={<HomePage />} />
            <Route path="communities" element={<CommunitiesPage />} />
            <Route
              path="communities/:slug/threads/:threadPk"
              element={<CommunityThreadPage />}
            />
            <Route path="flea" element={<FleaPage />} />
            <Route path="flea/exhibit" element={<ExhibitPage />} />
            <Route path="flea/products/:pk" element={<ProductDetailPage />} />
            <Route path="flea/chats/:roomPk" element={<TradeChatPage />} />
            <Route path="timetable" element={<TimetablePage />} />
            <Route path="timetable/user/:userPk" element={<TimetablePage />} />
            <Route path="users/:userId" element={<ProfilePage />} />
            <Route path="users/:userId/:tab" element={<ProfilePage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="notifications" element={<NotificationsPage />} />
            <Route path="dm" element={<DmInboxPage />} />
            <Route path="dm/groups/new" element={<GroupCreatePage />} />
            <Route path="dm/groups/:roomPk" element={<GroupRoomPage />} />
            <Route path="dm/:roomPk" element={<DmRoomPage />} />
            <Route path="more" element={<MorePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SessionProvider>
  );
}
