import { Outlet } from "react-router-dom";

/** Standalone auth chrome (no app shell) — matches classic login templates. */
export function AuthLayout() {
  return (
    <div className="auth-page">
      <Outlet />
    </div>
  );
}
