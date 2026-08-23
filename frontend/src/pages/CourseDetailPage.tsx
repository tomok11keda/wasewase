import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  createAbsenceRecord,
  deleteAbsenceRecord,
  fetchOfferingDetail,
  fetchReviews,
  offeringScheduleText,
  submitReview,
  unenrollOffering,
  type CourseAttendancePayload,
  type CourseOffering,
  type CourseReview,
  type ReviewSummary,
} from "../features/courses/api";
import { analytics } from "../lib/analytics/events";

function formatAbsenceDate(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return `${m}/${d}`;
}

function Stars({
  value,
  onChange,
  readOnly = false,
}: {
  value: number;
  onChange?: (n: number) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="course-stars" role={readOnly ? "img" : "group"}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          className={`course-stars__btn${value >= n ? " is-on" : ""}`}
          disabled={readOnly}
          aria-label={`${n}`}
          onClick={() => onChange?.(n)}
        >
          ★
        </button>
      ))}
    </div>
  );
}

export function CourseDetailPage() {
  const { offeringPk } = useParams();
  const navigate = useNavigate();
  const { me } = useSession();
  const pk = Number(offeringPk);
  const [offering, setOffering] = useState<CourseOffering | null>(null);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [reviews, setReviews] = useState<CourseReview[]>([]);
  const [attendance, setAttendance] = useState<CourseAttendancePayload | null>(
    null
  );
  const [showRecordPicker, setShowRecordPicker] = useState(false);
  const [absenceToast, setAbsenceToast] = useState<{
    message: string;
    recordId: number;
    date: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showReviewForm, setShowReviewForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({
    overall_rating: 3,
    difficulty_rating: 3,
    workload_rating: 3,
    attendance_rating: 3,
    exam_rating: 3,
    comment: "",
  });

  const load = async () => {
    if (!Number.isFinite(pk)) {
      setError("invalid");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const detail = await fetchOfferingDetail(pk);
      setOffering(detail.offering);
      setSummary(detail.review_summary);
      setAttendance(detail.attendance || null);
      const rev = await fetchReviews(detail.offering.id);
      setReviews(rev.reviews);
      setSummary(rev.summary);
      analytics.courseDetailViewed();
      const own = rev.reviews.find((r) => r.is_own);
      if (own) {
        setDraft({
          overall_rating: own.overall_rating,
          difficulty_rating: own.difficulty_rating,
          workload_rating: own.workload_rating,
          attendance_rating: own.attendance_rating,
          exam_rating: own.exam_rating,
          comment: own.comment || "",
        });
      }
    } catch {
      setError("load_failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pk]);

  useEffect(() => {
    if (!absenceToast) return;
    const t = window.setTimeout(() => setAbsenceToast(null), 6000);
    return () => window.clearTimeout(t);
  }, [absenceToast]);

  const recordedDates = new Set(
    (attendance?.records || []).map((r) => r.date)
  );
  const availableDates = (attendance?.meeting_dates || []).filter(
    (d) => !recordedDates.has(d)
  );

  const onRecordAbsence = async (date: string) => {
    if (!offering) return;
    setBusy(true);
    try {
      const result = await createAbsenceRecord(offering.id, date);
      setAttendance(result.attendance);
      setShowRecordPicker(false);
      analytics.courseAbsenceRecorded({
        offering_id: offering.id,
        date,
        source: "course_detail",
      });
      setAbsenceToast({
        message: `${formatAbsenceDate(date)}を欠席として記録しました`,
        recordId: result.record.id,
        date,
      });
    } catch (err) {
      const code = err instanceof Error ? err.message : "";
      if (code === "date_calendar_skipped") {
        window.alert(
          "この日はカレンダーで予定を非表示にしています。欠席記録はできません。"
        );
      } else if (code === "current_enrollment_required") {
        window.alert("履修中の授業のみ欠席を記録できます。");
      } else {
        window.alert("欠席の記録に失敗しました。");
      }
    } finally {
      setBusy(false);
    }
  };

  const onRemoveAbsence = async (
    recordId: number,
    date: string,
    source: "course_detail" | "undo"
  ) => {
    if (!offering) return;
    setBusy(true);
    try {
      const result = await deleteAbsenceRecord(recordId);
      if (result.attendance) setAttendance(result.attendance);
      else {
        setAttendance((prev) =>
          prev
            ? {
                ...prev,
                records: prev.records.filter((r) => r.id !== recordId),
                absence_count: Math.max(0, prev.absence_count - 1),
              }
            : prev
        );
      }
      analytics.courseAbsenceRemoved({
        offering_id: offering.id,
        date,
        source,
      });
      if (absenceToast?.recordId === recordId) setAbsenceToast(null);
    } catch {
      window.alert("欠席記録の取消に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  const onRemove = async () => {
    if (!offering) return;
    if (!window.confirm("時間割からこの授業を削除しますか？")) return;
    setBusy(true);
    try {
      await unenrollOffering(offering.id);
      analytics.timetableCourseRemoved();
      navigate("/timetable");
    } catch {
      window.alert("削除に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  const onSubmitReview = async (e: FormEvent) => {
    e.preventDefault();
    if (!offering || !me?.authenticated) return;
    setBusy(true);
    try {
      const data = await submitReview(offering.id, draft);
      setSummary(data.summary);
      setReviews((prev) => {
        const rest = prev.filter((r) => !r.is_own);
        return [{ ...data.review, is_own: true }, ...rest];
      });
      setShowReviewForm(false);
      analytics.courseReviewCreated();
    } catch (err) {
      const code = err instanceof Error ? err.message : "";
      if (code === "enrollment_required") {
        window.alert(
          "レビューするには、この授業を時間割に登録した実績が必要です。"
        );
      } else if (code === "rate_limited") {
        window.alert("操作が多すぎます。時間をおいて再度お試しください。");
      } else {
        window.alert("レビューの保存に失敗しました。");
      }
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="course-detail-page" data-spa-page="時間割">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (error || !offering) {
    return (
      <div className="course-detail-page" data-spa-page="時間割">
        <div className="main-inner">
          <p>授業が見つかりませんでした。</p>
          <Link to="/timetable">時間割へ戻る</Link>
        </div>
      </div>
    );
  }

  const enrolled = offering.viewer_enrollment === "current";
  const canReview =
    offering.viewer_enrollment === "current" ||
    offering.viewer_enrollment === "past";

  return (
    <div className="course-detail-page" data-spa-page="時間割">
      <div className="main-inner course-detail">
        <button
          type="button"
          className="course-detail__back"
          onClick={() => navigate(-1)}
        >
          ← 戻る
        </button>

        <h1 className="course-detail__title">{offering.title}</h1>
        <p className="course-detail__instructor">{offering.instructor}</p>
        <p className="course-detail__schedule">
          {offeringScheduleText(offering)}
          {" · "}
          {offering.academic_year}年度 {offering.semester_label}
        </p>

        <div className="course-detail__enrollment">
          履修中 <strong>{offering.enrollment_count}</strong>人
        </div>

        <div className="course-detail__actions">
          {me?.authenticated ? (
            <Link
              className="course-detail__talk-cta"
              to={`/courses/${offering.id}/talk`}
            >
              授業トーク
              <span className="course-detail__talk-cta-sub">
                質問・口コミを話す
              </span>
            </Link>
          ) : (
            <Link
              className="course-detail__talk-cta"
              to={spaLoginPath(`/app/courses/${offering.id}/talk`)}
            >
              ログインして授業トーク
            </Link>
          )}
        </div>

        <dl className="course-detail__meta">
          {offering.school ? (
            <>
              <dt>学部</dt>
              <dd>{offering.school}</dd>
            </>
          ) : null}
          {offering.campus ? (
            <>
              <dt>キャンパス</dt>
              <dd>{offering.campus}</dd>
            </>
          ) : null}
          {offering.room ? (
            <>
              <dt>教室</dt>
              <dd>{offering.room}</dd>
            </>
          ) : null}
          {offering.credits ? (
            <>
              <dt>単位</dt>
              <dd>{offering.credits}</dd>
            </>
          ) : null}
        </dl>

        {attendance ? (
          <section className="course-detail__attendance" aria-label="欠席記録">
            <div className="course-detail__attendance-head">
              <h2>欠席 {attendance.absence_count}回</h2>
              <p className="course-detail__section-hint">自分だけに表示</p>
            </div>
            {attendance.meetings.length > 1 ? (
              <p className="course-detail__attendance-meetings">
                開講:{" "}
                {attendance.meetings
                  .map((m) => `${m.day_label}${m.period_label}`)
                  .join("・")}
              </p>
            ) : null}
            {attendance.can_record ? (
              <button
                type="button"
                className="course-detail__attendance-cta"
                disabled={busy}
                onClick={() => setShowRecordPicker((v) => !v)}
              >
                ＋ 欠席を記録
              </button>
            ) : (
              <p className="course-detail__avg">
                履修中のみ新しい欠席を記録できます。
              </p>
            )}
            {showRecordPicker && attendance.can_record ? (
              <div className="course-detail__date-picker">
                <p className="course-detail__date-picker-label">
                  授業がある日を選ぶ
                </p>
                {availableDates.length === 0 ? (
                  <p className="course-detail__avg">
                    記録できる日付がありません
                  </p>
                ) : (
                  <ul className="course-detail__date-list">
                    {availableDates.slice(0, 24).map((d) => (
                      <li key={d}>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void onRecordAbsence(d)}
                        >
                          {formatAbsenceDate(d)}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}
            {attendance.records.length > 0 ? (
              <div className="course-detail__absence-history">
                <h3>最近の欠席</h3>
                <ul>
                  {attendance.records.map((r) => (
                    <li key={r.id}>
                      <span>
                        {formatAbsenceDate(r.date)}
                        {r.day_label ? `（${r.day_label}）` : ""}
                      </span>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          void onRemoveAbsence(r.id, r.date, "course_detail")
                        }
                      >
                        欠席記録を取り消す
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        ) : null}

        <section className="course-detail__reviews">
          <div className="course-detail__reviews-head">
            <h2>レビュー</h2>
            <p className="course-detail__section-hint">履修した人の評価</p>
            {summary && summary.count > 0 ? (
              <p className="course-detail__avg">
                総合 {summary.overall}（{summary.count}件）
              </p>
            ) : (
              <p className="course-detail__avg">まだレビューがありません</p>
            )}
          </div>

          {me?.authenticated && canReview ? (
            <button
              type="button"
              className="course-detail__review-cta"
              onClick={() => setShowReviewForm((v) => !v)}
            >
              {offering.viewer_has_review || reviews.some((r) => r.is_own)
                ? "レビューを編集"
                : "レビューを書く"}
            </button>
          ) : me?.authenticated ? (
            <p className="course-detail__avg">
              レビューするには、この授業を時間割へ登録してください。
            </p>
          ) : (
            <Link
              className="course-detail__review-cta"
              to={spaLoginPath(`/app/courses/${offering.id}`)}
            >
              ログインしてレビュー
            </Link>
          )}

          {showReviewForm && canReview ? (
            <form className="course-review-form" onSubmit={onSubmitReview}>
              {(
                [
                  ["overall_rating", "総合評価"],
                  ["difficulty_rating", "単位取得難易度"],
                  ["workload_rating", "課題量"],
                  ["attendance_rating", "出席重要度"],
                  ["exam_rating", "試験"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="course-review-form__row">
                  <span>{label}</span>
                  <Stars
                    value={draft[key]}
                    onChange={(n) => setDraft((d) => ({ ...d, [key]: n }))}
                  />
                </label>
              ))}
              <label>
                コメント（任意）
                <textarea
                  maxLength={1000}
                  value={draft.comment}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, comment: e.target.value }))
                  }
                  placeholder="授業の雰囲気や注意点など"
                />
              </label>
              <button type="submit" className="btn-compose" disabled={busy}>
                保存
              </button>
            </form>
          ) : null}

          <ul className="course-review-list">
            {reviews.map((r) => (
              <li key={r.id} className="course-review-list__item">
                <div className="course-review-list__top">
                  <Stars value={r.overall_rating} readOnly />
                  {r.is_own ? (
                    <span className="course-review-list__own">自分</span>
                  ) : null}
                </div>
                {r.comment ? <p>{r.comment}</p> : null}
              </li>
            ))}
          </ul>
        </section>

        <p className="course-detail__report">
          授業情報に誤りがある場合は、運営までお知らせください（β版では Admin
          から修正します）。
        </p>

        {enrolled ? (
          <button
            type="button"
            className="course-detail__remove"
            disabled={busy}
            onClick={() => void onRemove()}
          >
            時間割から削除
          </button>
        ) : null}
      </div>

      {absenceToast ? (
        <div className="course-detail__toast" role="status">
          <span>{absenceToast.message}</span>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void onRemoveAbsence(
                absenceToast.recordId,
                absenceToast.date,
                "undo"
              )
            }
          >
            元に戻す
          </button>
        </div>
      ) : null}
    </div>
  );
}
