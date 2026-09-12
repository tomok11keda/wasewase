import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useSession } from "../../lib/session";

export function OnboardingGate() {
  const { me, loading } = useSession();
  const location = useLocation();

  if (loading) {
    return (
      <div className="main-inner">
        <p>読み込み中…</p>
      </div>
    );
  }

  if (me?.authenticated && me.onboarding_required) {
    return <Navigate to="/onboarding" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
