/**
 * β-critical product events. No PII / no message bodies.
 */
import { captureEvent } from "./client";

export const analytics = {
  signupCompleted() {
    captureEvent("signup_completed");
  },

  loginCompleted() {
    captureEvent("login_completed");
  },

  timelineViewed() {
    captureEvent("timeline_viewed");
  },

  timelinePostCreated(props?: { has_image?: boolean; is_quote?: boolean }) {
    captureEvent("timeline_post_created", {
      has_image: Boolean(props?.has_image),
      is_quote: Boolean(props?.is_quote),
    });
  },

  commentCreated() {
    captureEvent("comment_created");
  },

  likeCreated() {
    captureEvent("like_created");
  },

  communityViewed() {
    captureEvent("community_viewed");
  },

  communityPostCreated() {
    captureEvent("community_post_created");
  },

  fleaViewed() {
    captureEvent("flea_viewed");
  },

  fleaItemViewed(props?: { status?: string; faculty?: string; campus?: string }) {
    captureEvent("flea_item_viewed", {
      status: props?.status || undefined,
      faculty: props?.faculty || undefined,
      campus: props?.campus || undefined,
    });
  },

  fleaItemCreated(props?: { faculty?: string; campus?: string }) {
    captureEvent("flea_item_created", {
      faculty: props?.faculty || undefined,
      campus: props?.campus || undefined,
    });
  },

  /** 値下げ交渉チャット開始（問い合わせ） */
  fleaInquiryCreated() {
    captureEvent("flea_inquiry_created");
  },

  /** 即決購入 or 出品者の取引開始（pending 確定） */
  tradeStarted(props: { method: "instant_purchase" | "confirm_negotiation" }) {
    captureEvent("trade_started", { method: props.method });
  },

  /** 出品者の受け渡し完了 → sold */
  tradeCompleted() {
    captureEvent("trade_completed");
  },

  timetableViewed() {
    captureEvent("timetable_viewed");
  },

  timetableSlotSaved(props?: { filled?: boolean }) {
    captureEvent("timetable_slot_saved", {
      filled: Boolean(props?.filled),
    });
  },

  courseSearchOpened(props?: { from_slot?: boolean }) {
    captureEvent("course_search_opened", {
      from_slot: Boolean(props?.from_slot),
    });
  },

  courseSearchPerformed(props?: { query_len?: number; result_count?: number }) {
    captureEvent("course_search_performed", {
      query_len: props?.query_len ?? 0,
      result_count: props?.result_count ?? 0,
    });
  },

  /**
   * グローバル検索タブ（おすすめ/最新/授業/ユーザー/商品）。
   * クエリ文字列を収集し、後から検索改善に使う（0件把握用に zero_results も付与）。
   */
  searchPerformed(props: {
    query: string;
    tab: string;
    result_count: number;
  }) {
    const query = (props.query || "").trim();
    const resultCount = Math.max(0, Number(props.result_count) || 0);
    captureEvent("search_performed", {
      query,
      query_len: query.length,
      tab: props.tab || "all",
      result_count: resultCount,
      zero_results: resultCount === 0,
    });
  },

  courseCalendarEventSkipped(props: {
    offering_id: number;
    date: string;
    source: "event_detail" | "hidden_events_list" | "undo_toast" | string;
  }) {
    captureEvent("course_calendar_event_skipped", {
      offering_id: props.offering_id,
      date: props.date,
      source: props.source,
    });
  },

  courseCalendarEventRestored(props: {
    offering_id: number;
    date: string;
    source: "event_detail" | "hidden_events_list" | "undo_toast" | string;
  }) {
    captureEvent("course_calendar_event_restored", {
      offering_id: props.offering_id,
      date: props.date,
      source: props.source,
    });
  },

  courseAbsenceRecorded(props: {
    offering_id: number;
    date: string;
    source: "course_detail" | "calendar" | "undo" | string;
  }) {
    captureEvent("course_absence_recorded", {
      offering_id: props.offering_id,
      date: props.date,
      source: props.source,
    });
  },

  courseAbsenceRemoved(props: {
    offering_id: number;
    date: string;
    source: "course_detail" | "calendar" | "undo" | string;
  }) {
    captureEvent("course_absence_removed", {
      offering_id: props.offering_id,
      date: props.date,
      source: props.source,
    });
  },

  existingCourseAdded(props?: { from_slot?: boolean }) {
    captureEvent("existing_course_added", {
      from_slot: Boolean(props?.from_slot),
    });
  },

  newCourseCreated(props?: { forced?: boolean }) {
    captureEvent("new_course_created", {
      forced: Boolean(props?.forced),
    });
  },

  courseDetailViewed() {
    captureEvent("course_detail_viewed");
  },

  timetableCourseRemoved() {
    captureEvent("timetable_course_removed");
  },

  courseReviewCreated() {
    captureEvent("course_review_created");
  },

  courseChatOpened(props?: { from_detail?: boolean; from_inbox?: boolean }) {
    captureEvent("course_chat_opened", {
      from_detail: Boolean(props?.from_detail),
      from_inbox: Boolean(props?.from_inbox),
    });
  },

  courseChatOpenedFromDetail() {
    captureEvent("course_chat_opened_from_detail");
  },

  courseChatOpenedFromInbox() {
    captureEvent("course_chat_opened_from_inbox");
  },

  courseChatJoined() {
    captureEvent("course_chat_joined");
  },

  courseChatLeft() {
    captureEvent("course_chat_left");
  },

  courseChatMessageSent() {
    captureEvent("course_chat_message_sent");
  },

  chatMessageLongPressed(props?: { kind?: string }) {
    captureEvent("chat_message_long_pressed", {
      kind: props?.kind || undefined,
    });
  },

  chatReplyStarted(props?: { kind?: string }) {
    captureEvent("chat_reply_started", { kind: props?.kind || undefined });
  },

  chatReplySent(props?: { kind?: string }) {
    captureEvent("chat_reply_sent", { kind: props?.kind || undefined });
  },

  chatMessageCopied(props?: { kind?: string }) {
    captureEvent("chat_message_copied", { kind: props?.kind || undefined });
  },

  chatMessageDeleted(props?: { kind?: string }) {
    captureEvent("chat_message_deleted", { kind: props?.kind || undefined });
  },

  chatMessageReported(props?: { kind?: string }) {
    captureEvent("chat_message_reported", { kind: props?.kind || undefined });
  },

  dmStarted(props?: { created_new?: boolean }) {
    captureEvent("dm_started", {
      created_new: props?.created_new !== false,
    });
  },

  groupChatStarted() {
    captureEvent("group_chat_started");
  },

  notificationOpened() {
    captureEvent("notification_opened");
  },
};
