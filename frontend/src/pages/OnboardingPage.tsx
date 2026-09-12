import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { performSpaLogout } from "../features/auth/api";
import { FollowStep } from "../features/onboarding/FollowStep";
import { ProfileStep } from "../features/onboarding/ProfileStep";
import { WelcomeStep } from "../features/onboarding/WelcomeStep";
import {
  completeOnboarding,
  fetchOnboardingStatus,
  type OnboardingStatus,
  type OnboardingStep,
} from "../features/onboarding/api";
import { useSession } from "../lib/session";

export function OnboardingPage() {
  const { me, loading, refresh } = useSession();
  const navigate = useNavigate();
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [step, setStep] = useState<OnboardingStep>("profile");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!me?.authenticated) {
      navigate("/login?next=/app/onboarding", { replace: true });
      return;
    }
    if (!me.onboarding_required) {
      navigate("/", { replace: true });
      return;
    }
    void fetchOnboardingStatus()
      .then((data) => {
        setStatus(data);
        setStep(data.step);
      })
      .catch(() => setError("オンボーディングを読み込めません。"));
  }, [loading, me?.authenticated, me?.onboarding_required, navigate]);

  const onWelcome = async () => {
    setBusy(true);
    setError(null);
    try {
      await completeOnboarding();
      await refresh();
      navigate("/", { replace: true });
    } catch {
      setError("完了処理に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  const onLogout = async () => {
    await performSpaLogout();
    await refresh();
    navigate("/login", { replace: true });
  };

  return (
    <main className="main-inner onboarding-page" data-spa-page="オンボーディング">
      <div
        className={`form-card onboarding-card${
          step === "profile" ? " is-wizard" : ""
        }`}
      >
        {error ? <p className="field-error">{error}</p> : null}
        {!status ? <p>読み込み中…</p> : null}
        {status && step === "profile" ? (
          <ProfileStep
            profile={status.profile}
            faculties={status.faculties}
            onDone={() => setStep("follow")}
          />
        ) : null}
        {status && step === "follow" ? (
          <FollowStep onDone={() => setStep("welcome")} />
        ) : null}
        {status && step === "welcome" ? (
          <WelcomeStep busy={busy} onDone={() => void onWelcome()} />
        ) : null}
        <p className="onboarding-legal">
          <button type="button" onClick={() => void onLogout()}>
            ログアウト
          </button>
          {" · "}
          <a href="/terms/">利用規約</a>
        </p>
      </div>
    </main>
  );
}
