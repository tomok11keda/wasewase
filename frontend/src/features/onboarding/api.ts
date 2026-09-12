import { getCsrfToken } from "../timeline/api";

export type OnboardingStep = "profile" | "follow" | "welcome";

export type OnboardingProfile = {
  name: string;
  username: string;
  username_is_placeholder: boolean;
  department: string;
  avatar_url: string;
};

export type OnboardingStatus = {
  ok: boolean;
  required: boolean;
  completed: boolean;
  step: OnboardingStep;
  follow_goal: number;
  profile: OnboardingProfile;
  faculties: { value: string; label: string }[];
};

export type OnboardingSuggestion = {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
  department: string;
  is_following: boolean;
  follow_state: string;
};

async function readJson(res: Response) {
  return res.json().catch(() => ({}));
}

export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  const res = await fetch("/api/v1/onboarding/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await readJson(res);
  if (!res.ok || !data.ok) {
    throw new Error(data.error || `onboarding_${res.status}`);
  }
  return data as OnboardingStatus;
}

export async function saveOnboardingProfile(input: {
  name: string;
  username: string;
  department: string;
  avatar: File | null;
}): Promise<{ ok: boolean; step?: OnboardingStep; errors?: Record<string, string[]>; error?: string }> {
  const body = new FormData();
  body.append("name", input.name);
  body.append("username", input.username);
  body.append("department", input.department);
  if (input.avatar) body.append("avatar", input.avatar);
  const res = await fetch("/api/v1/onboarding/profile/", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken(), Accept: "application/json" },
    body,
  });
  const data = await readJson(res);
  if (!res.ok || !data.ok) {
    return {
      ok: false,
      error: data.error || "validation",
      errors: data.errors || {},
    };
  }
  return { ok: true, step: data.step };
}

export async function fetchOnboardingSuggestions(): Promise<{
  users: OnboardingSuggestion[];
  follow_goal: number;
  following_count: number;
}> {
  const res = await fetch("/api/v1/onboarding/suggestions/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await readJson(res);
  if (!res.ok || !data.ok) {
    throw new Error(data.error || `suggestions_${res.status}`);
  }
  return {
    users: (data.users || []) as OnboardingSuggestion[],
    follow_goal: Number(data.follow_goal || 3),
    following_count: Number(data.following_count || 0),
  };
}

export async function completeFollowStep(): Promise<void> {
  const res = await fetch("/api/v1/onboarding/follow-step/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  const data = await readJson(res);
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "follow_step_failed");
  }
}

export async function completeOnboarding(): Promise<void> {
  const res = await fetch("/api/v1/onboarding/complete/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  const data = await readJson(res);
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "complete_failed");
  }
}
