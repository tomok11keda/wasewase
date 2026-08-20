import { ensureAuthCsrf } from "../auth/api";
import { apiGetJson, apiPostJson } from "../../lib/http";

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

export async function fetchCourseMeta(): Promise<CourseMeta> {
  const { ok, data, error } = await apiGetJson("/api/v1/courses/meta/");
  if (!ok) throw new Error(error || "meta_failed");
  return data as unknown as CourseMeta;
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
  const { ok, data, error } = await apiGetJson(
    `/api/v1/courses/search/?${qs.toString()}`
  );
  if (!ok) throw new Error(error || "search_failed");
  return ((data.results as CourseOffering[]) || []) as CourseOffering[];
}

export async function fetchOfferingDetail(offeringPk: number): Promise<{
  offering: CourseOffering;
  review_summary: ReviewSummary;
}> {
  const { ok, data, error } = await apiGetJson(
    `/api/v1/courses/offerings/${offeringPk}/`
  );
  if (!ok) throw new Error(error || "detail_failed");
  return data as unknown as {
    offering: CourseOffering;
    review_summary: ReviewSummary;
  };
}

export async function enrollOffering(
  offeringPk: number,
  slotKey?: string | null
): Promise<{ offering: CourseOffering; slot: SlotPayload }> {
  await ensureAuthCsrf();
  const { ok, data, error, status } = await apiPostJson(
    `/api/v1/courses/offerings/${offeringPk}/enroll/`,
    slotKey ? { slot_key: slotKey } : {}
  );
  if (!ok) {
    const err = new Error(error || "enroll_failed") as Error & {
      status?: number;
    };
    err.status = status;
    throw err;
  }
  return data as unknown as { offering: CourseOffering; slot: SlotPayload };
}

export async function unenrollOffering(offeringPk: number): Promise<void> {
  await ensureAuthCsrf();
  const { ok, data, error } = await apiPostJson(
    `/api/v1/courses/offerings/${offeringPk}/unenroll/`,
    {}
  );
  if (!ok) throw new Error(error || "unenroll_failed");
  void data;
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
  status: number;
  error?: string;
  created?: boolean;
  offering?: CourseOffering;
  slot?: SlotPayload;
  duplicates?: CourseOffering[];
}> {
  await ensureAuthCsrf();
  const { ok, status, data, error } = await apiPostJson(
    "/api/v1/courses/offerings/",
    input
  );
  if (import.meta.env.DEV && (!ok || error)) {
    console.error("[course:create]", status, data);
  }
  return {
    ok,
    status,
    error: ok ? undefined : error || (data.error as string | undefined),
    created: Boolean(data.created),
    offering: data.offering as CourseOffering | undefined,
    slot: data.slot as SlotPayload | undefined,
    duplicates: data.duplicates as CourseOffering[] | undefined,
  };
}

export async function fetchReviews(offeringPk: number): Promise<{
  summary: ReviewSummary;
  reviews: CourseReview[];
}> {
  const { ok, data, error } = await apiGetJson(
    `/api/v1/courses/offerings/${offeringPk}/reviews/`
  );
  if (!ok) throw new Error(error || "reviews_failed");
  return data as unknown as { summary: ReviewSummary; reviews: CourseReview[] };
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
  await ensureAuthCsrf();
  const { ok, data, error } = await apiPostJson(
    `/api/v1/courses/offerings/${offeringPk}/reviews/`,
    payload
  );
  if (!ok) throw new Error(error || "review_failed");
  return data as unknown as { review: CourseReview; summary: ReviewSummary };
}

export function offeringScheduleText(o: CourseOffering): string {
  return `${o.day_label}曜${o.period_label}`;
}

export type CourseTalkMessage = {
  id: number;
  sender_id: number | null;
  sender_name: string;
  sender_initial?: string;
  avatar_url?: string;
  body: string;
  created_at: string;
  is_mine: boolean;
  is_deleted?: boolean;
  reply_to?: {
    id: number;
    sender_name: string;
    text_preview: string;
    is_unavailable?: boolean;
  } | null;
  enrollment_role?: string | null;
  enrollment_label?: string | null;
};

export type CourseTalkRoom = {
  id: number;
  kind: "course";
  name: string;
  offering_id: number;
  can_send: boolean;
  membership_status: string;
  latest_id: number;
  member_count: number;
};

export type CourseTalkPayload = {
  ok: boolean;
  joined?: boolean;
  joined_now?: boolean;
  offering: CourseOffering;
  viewer_enrollment?: string | null;
  room: CourseTalkRoom;
  messages: CourseTalkMessage[];
};

export async function openCourseTalk(
  offeringPk: number
): Promise<CourseTalkPayload> {
  await ensureAuthCsrf();
  // Prefer POST semantics for join; GET also joins for bookmark/reload
  const { ok, data, error, status } = await apiPostJson(
    `/api/v1/courses/offerings/${offeringPk}/talk/`,
    {}
  );
  if (!ok) {
    const err = new Error(error || "talk_open_failed") as Error & {
      status?: number;
    };
    err.status = status;
    throw err;
  }
  return data as unknown as CourseTalkPayload;
}

export async function leaveCourseTalk(offeringPk: number): Promise<void> {
  await ensureAuthCsrf();
  const { ok, error } = await apiPostJson(
    `/api/v1/courses/offerings/${offeringPk}/talk/leave/`,
    {}
  );
  if (!ok) throw new Error(error || "talk_leave_failed");
}

export async function pollCourseTalkMessages(
  roomPk: number,
  afterId: number,
  signal?: AbortSignal
): Promise<{ messages: CourseTalkMessage[]; latest_id: number }> {
  const qs = afterId > 0 ? `?after=${afterId}` : "";
  const res = await fetch(`/api/v1/courses/talk/${roomPk}/messages/${qs}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || "poll_failed");
  }
  return {
    messages: (data.messages || []) as CourseTalkMessage[],
    latest_id: Number(data.latest_id || 0),
  };
}

export async function sendCourseTalkMessage(
  roomPk: number,
  body: string,
  replyToId?: number | null
): Promise<CourseTalkMessage> {
  await ensureAuthCsrf();
  const { ok, data, error } = await apiPostJson(
    `/api/v1/courses/talk/${roomPk}/messages/send/`,
    {
      body,
      ...(replyToId ? { reply_to_id: replyToId } : {}),
    }
  );
  if (!ok) throw new Error(error || "send_failed");
  return data.message as unknown as CourseTalkMessage;
}

export async function deleteCourseTalkMessage(
  roomPk: number,
  messagePk: number
): Promise<CourseTalkMessage> {
  await ensureAuthCsrf();
  const { ok, data, error } = await apiPostJson(
    `/api/v1/courses/talk/${roomPk}/messages/${messagePk}/delete/`,
    {}
  );
  if (!ok) throw new Error(error || "delete_failed");
  return data.message as unknown as CourseTalkMessage;
}
