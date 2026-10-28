import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { FormSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import {
  emptyChatEventForm,
  recruitingChatEventPath,
  recruitingChatEventsPath,
  type OrganizationChatEventForm,
} from "../features/orgs/orgChatEvents";
import {
  createOrganizationChatEvent,
  fetchOrganizationChatEvent,
  updateOrganizationChatEvent,
} from "../features/orgs/orgChatEventsApi";
import { isoToTokyoInput, tokyoInputToIso } from "../features/orgs/orgEvents";
import { parseRecruitingChatIdFromSearch } from "../features/orgs/recruitingChat";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function OrganizationChatEventFormPage() {
  const { slug, eventId: eventIdRaw } = useParams();
  const [searchParams] = useSearchParams();
  const chatId = parseRecruitingChatIdFromSearch(searchParams.toString());
  const eventId = eventIdRaw ? Number(eventIdRaw) : null;
  const isEdit = eventId != null && Number.isInteger(eventId) && eventId > 0;
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const busyRef = useRef(false);
  const [form, setForm] = useState<OrganizationChatEventForm>(emptyChatEventForm());
  const [loading, setLoading] = useState(isEdit);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setForm(emptyChatEventForm());
    setError(null);
    setFieldErrors({});
    setLoading(isEdit);
  }, [slug, eventId, chatId, sessionUserId, isEdit]);

  const load = useCallback(async () => {
    if (!slug || !isEdit || eventId == null || chatId == null) {
      setLoading(false);
      return;
    }
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    try {
      const event = await fetchOrganizationChatEvent(slug, eventId, chatId);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      if (!event.can_manage) {
        setError("forbidden");
        return;
      }
      setForm({
        title: event.title,
        description: event.description,
        starts_at: isoToTokyoInput(event.starts_at),
        ends_at: event.ends_at ? isoToTokyoInput(event.ends_at) : "",
        venue_name: event.venue_name,
        rsvp_deadline: event.rsvp_deadline
          ? isoToTokyoInput(event.rsvp_deadline)
          : "",
      });
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setError(err instanceof OrganizationRequestError ? err.code : "load_failed");
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [chatId, eventId, isEdit, slug]);

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load();
  }, [browsePreview, load, sessionLoading, sessionUserId]);

  if (!slug || chatId == null) {
    return <Navigate to="/" replace />;
  }

  const loginNext = `/app/organizations/${slug}/recruiting-chat/events/new?chat=${chatId}`;
  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="チャット内イベント">
        <div className="main-inner">
          <p>チャット内イベントの作成にはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  function setField<K extends keyof OrganizationChatEventForm>(
    key: K,
    value: OrganizationChatEventForm[K]
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (!slug || chatId == null || busyRef.current) return;
    const errors: Record<string, string> = {};
    if (!form.title.trim()) errors.title = "イベント名を入力してください。";
    if (!form.starts_at.trim() || !tokyoInputToIso(form.starts_at)) {
      errors.starts_at = "開始日時を入力してください。";
    }
    if (Object.keys(errors).length) {
      setFieldErrors(errors);
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setFieldErrors({});
    try {
      const saved =
        isEdit && eventId != null
          ? await updateOrganizationChatEvent(slug, eventId, chatId, form)
          : await createOrganizationChatEvent(slug, chatId, form);
      navigate(recruitingChatEventPath(slug, saved.id, chatId));
    } catch (err) {
      if (err instanceof OrganizationRequestError) {
        setError(err.message);
        if (err.fieldErrors) setFieldErrors(err.fieldErrors);
      } else {
        setError("保存できませんでした。");
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="org-edit-page" data-spa-page="チャット内イベント">
      <div className="main-inner">
        {loading || sessionLoading ? (
          <FormSkeleton />
        ) : error === "forbidden" || error === "not_found" ? (
          <p>このイベントを編集する権限がありません。</p>
        ) : (
          <>
            <p className="org-event-kicker">チャット内イベント · 公開されません</p>
            <h1>{isEdit ? "イベントを編集" : "チャット内イベントを作成"}</h1>
            {error ? (
              <p className="org-edit-error" role="alert">
                {error}
              </p>
            ) : null}
            <form className="org-event-form" onSubmit={onSubmit}>
              <div className="form-group">
                <label htmlFor="chat-event-title">イベント名</label>
                <input
                  id="chat-event-title"
                  value={form.title}
                  onChange={(e) => setField("title", e.target.value)}
                  autoComplete="off"
                  required
                />
                {fieldErrors.title ? (
                  <p className="org-edit-field-error">{fieldErrors.title}</p>
                ) : null}
              </div>
              <div className="form-group">
                <label htmlFor="chat-event-description">説明（任意）</label>
                <textarea
                  id="chat-event-description"
                  value={form.description}
                  onChange={(e) => setField("description", e.target.value)}
                  rows={5}
                />
              </div>
              <div className="org-event-form__when">
                <div className="form-group">
                  <label htmlFor="chat-event-starts">開始日時（日本時間）</label>
                  <input
                    id="chat-event-starts"
                    type="datetime-local"
                    value={form.starts_at}
                    onChange={(e) => setField("starts_at", e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="chat-event-ends">終了日時（任意）</label>
                  <input
                    id="chat-event-ends"
                    type="datetime-local"
                    value={form.ends_at}
                    onChange={(e) => setField("ends_at", e.target.value)}
                  />
                </div>
              </div>
              <div className="form-group">
                <label htmlFor="chat-event-venue">場所（任意）</label>
                <input
                  id="chat-event-venue"
                  value={form.venue_name}
                  onChange={(e) => setField("venue_name", e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="form-group">
                <label htmlFor="chat-event-deadline">回答期限（任意・日本時間）</label>
                <input
                  id="chat-event-deadline"
                  type="datetime-local"
                  value={form.rsvp_deadline}
                  onChange={(e) => setField("rsvp_deadline", e.target.value)}
                />
              </div>
              <div className="org-event-form__actions">
                <button type="submit" className="btn-submit" disabled={busy}>
                  {busy ? "保存中…" : isEdit ? "変更を保存" : "作成してチャットに掲載"}
                </button>
                <Link className="org-edit-back" to={recruitingChatEventsPath(slug, chatId)}>
                  キャンセル
                </Link>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
