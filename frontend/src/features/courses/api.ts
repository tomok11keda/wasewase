import { getCsrfToken } from "../timeline/api";

export type CourseOffering = {
  id: number;
  course_id: number;
  title: string;
  instructor: string;
  academic_year: number;
  semester: string;
  semester_label: string;
  day_of_week: number;
  day_label: string;
  period_kind: "period" | "od" | string;
  period: number;
  period_label: string;
  slot_key: string;
  school: string;
  campus: string;
  room: string;
  credits: string;
  status: string;
  enrollment_count: number;
  viewer_enrollment?: string | null;
  viewer_has_review?: boolean;
};

export type CourseMeta = {
  academic_year: number;
  semester: string;
  semesters: Array<{ value: string; label: string }>;
  faculties: Array<{ value: string; label: string }>;
  campuses: Array<{ value: string; label: string }>;
};

export type ReviewSummary = {
  count: number;
  overall: number | null;
  difficulty: number | null;
  workload: number | null;
  attendance: number | null;
  exam: number | null;
};

export type CourseReview = {
  id: number;
  offering_id: number;
  overall_rating: number;
  difficulty_rating: number;
  workload_rating: number;
  attendance_rating: number;
  exam_rating: number;
  comment: string;
  updated_at: string;
  is_own: boolean;
};

export type SlotPayload = {
  slot_key?: string;
  name: string;
  room: string;
  credits: string;
  memo: string;
  offering_id?: number | null;
};

async function parseJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return {};
  }
}

export async function fetchCourseMeta(): Promise<CourseMeta> {
  const res = await fetch("/api/v1/courses/meta/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await parseJson(res);
  if (!res.ok || !data.ok) throw new Error(data.error || "meta_failed");
  return data as CourseMeta;
}

export async function searchCourses(params: {
  q: string;
  day?: number | null;
  period?: number | null;
  period_kind?: string | null;
  semester?: string | null;
  year?: number | null;
}): Promise<CourseOffering[]> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.day != null) qs.set("day", String(params.day));
  if (params.period != null) qs.set("period", String(params.period));
  if (params.period_kind) qs.set("period_kind", params.period_kind);
  if (params.semester) qs.set("semester", params.semester);
  if (params.year != null) qs.set("year", String(params.year));
  const res = await fetch(`/api/v1/courses/search/?${qs.toString()}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await parseJson(res);
  if (!res.ok || !data.ok) throw new Error(data.error || "search_failed");
  return (data.results || []) as CourseOffering[];
}

export async function fetchOfferingDetail(offeringPk: number): Promise<{
  offering: CourseOffering;
  review_summary: ReviewSummary;
}> {
  const res = await fetch(`/api/v1/courses/offerings/${offeringPk}/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await parseJson(res);
  if (!res.ok || !data.ok) throw new Error(data.error || "detail_failed");
  return data;
}

export async function enrollOffering(
  offeringPk: number,
  slotKey?: string | null
): Promise<{ offering: CourseOffering; slot: SlotPayload }> {
  const res = await fetch(`/api/v1/courses/offerings/${offeringPk}/enroll/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(slotKey ? { slot_key: slotKey } : {}),
  });
  const data = await parseJson(res);
  if (!res.ok || !data.ok) throw new Error(data.error || "enroll_failed");
  return data;
}

export async function unenrollOffering(offeringPk: number): Promise<void> {
  const res = await fetch(`/api/v1/courses/offerings/${offeringPk}/unenroll/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: "{}",
  });
  const data = await parseJson(res);
  if (!res.ok || !data.ok) throw new Error(data.error || "unenroll_failed");
}

export type CreateOfferingInput = {
  title: string;
  instructor: string;
  academic_year: number;
  semester: string;
  day_of_week: number;
  period: number;
  period_kind: string;
  school?: string;
  campus?: string;
  room?: string;
  credits?: string;
  slot_key?: string | null;
  enroll?: boolean;
  force_create?: boolean;
};

export async function createOffering(input: CreateOfferingInput): Promise<{
  ok: boolean;
  error?: string;
  created?: boolean;
  offering?: CourseOffering;
  slot?: SlotPayload;
  duplicates?: CourseOffering[];
}> {
  const res = await fetch("/api/v1/courses/offerings/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(input),
  });
  const data = await parseJson(res);
  if (import.meta.env.DEV && (!res.ok || !data.ok)) {
    console.error("[course:create]", res.status, data);
  }
  // Ensure error code surfaces even when body is empty (HTML 403 etc.)
  if (!res.ok && !data.error) {
    if (res.status === 401 || res.status === 403) {
      return { ok: false, error: "authentication_required" };
    }
    if (res.status === 429) {
      return { ok: false, error: "rate_limited" };
    }
    return { ok: false, error: `http_${res.status}` };
  }
  return data;
}

export async function fetchReviews(offeringPk: number): Promise<{
  summary: ReviewSummary;
  reviews: CourseReview[];
}> {
  const res = await fetch(`/api/v1/courses/offerings/${offeringPk}/reviews/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await parseJson(res);
  if (!res.ok || !data.ok) throw new Error(data.error || "reviews_failed");
  return data;
}

export async function submitReview(
  offeringPk: number,
  payload: {
    overall_rating: number;
    difficulty_rating: number;
    workload_rating: number;
    attendance_rating: number;
    exam_rating: number;
    comment: string;
  }
): Promise<{ review: CourseReview; summary: ReviewSummary }> {
  const res = await fetch(`/api/v1/courses/offerings/${offeringPk}/reviews/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });
  const data = await parseJson(res);
  if (!res.ok || !data.ok) throw new Error(data.error || "review_failed");
  return data;
}

export function offeringScheduleText(o: CourseOffering): string {
  return `${o.day_label}曜${o.period_label}`;
}
