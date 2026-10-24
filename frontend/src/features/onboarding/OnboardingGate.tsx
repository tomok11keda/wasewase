import { Navigate, Outlet, useLocation } from "react-router-dom";
import { BootSkeleton } from "../../components/BootSkeleton";
import { useSession } from "../../lib/session";

export function OnboardingGate() {
  const { me, loading } = useSession();
  const location = useLocation();

  if (loading) {
    return <BootSkeleton pathname={location.pathname} />;
  }

  if (me?.authenticated && me.onboarding_required) {
    return <Navigate to="/onboarding" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
