import { useEffect } from "react";
import { Outlet } from "react-router-dom";

/** Marks auth routes so body BottomNav padding / #root height match (no tab bar). */
const AUTH_SHELL_CLASS = "shell-auth";

/** Standalone auth chrome (no app shell) — matches classic login templates. */
export function AuthLayout() {
  useEffect(() => {
    document.body.classList.add(AUTH_SHELL_CLASS);
    document.documentElement.classList.add(AUTH_SHELL_CLASS);
    return () => {
      document.body.classList.remove(AUTH_SHELL_CLASS);
      document.documentElement.classList.remove(AUTH_SHELL_CLASS);
    };
  }, []);

  return (
    <div className="auth-page">
      <Outlet />
    </div>
  );
}
