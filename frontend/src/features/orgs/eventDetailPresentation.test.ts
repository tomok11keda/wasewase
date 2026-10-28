import assert from "node:assert/strict";
import test from "node:test";
import {
  eventDetailAdminActionLabel,
  eventDetailAdminLayout,
  eventPublicationStatusLabel,
  eventSignupModeLabel,
  eventVenueText,
  formatTokyoEventSchedule,
  visibleEventDetailAdminActions,
  type EventDetailAdminAction,
} from "./eventDetailPresentation.ts";
import { parseOrganizationEvent, type OrganizationEvent } from "./orgEvents.ts";

const published = {
  id: 11,
  organization_id: 3,
  organization_slug: "tennis",
  organization_name: "テニスサークル",
  organization_avatar_url: "",
  title: "新歓説明会",
  description: "紹介",
  starts_at: "2026-10-28T20:25:00Z",
  ends_at: "2026-10-29T03:30:00Z",
  venue_name: "大隈講堂",
  venue_address: "早稲田",
  registration_deadline: null,
  status: "published",
  signup_mode: "registration",
  registration_open: true,
  registered_count: 12,
  is_ended: false,
  is_deadline_passed: false,
  viewer_status: null,
  viewer_registered: false,
  can_register: true,
  can_cancel_registration: false,
  can_manage: true,
  has_lottery: false,
  lottery_executed_at: null,
  lottery_applicant_count: null,
  lottery_eligible_count: null,
  lottery_winner_count: null,
  lottery_not_selected_count: null,
  lottery_excluded_count: null,
  lottery_shared: false,
  viewer_lottery_result: null,
  can_run_lottery: false,
  can_view_lottery: false,
  can_share_lottery: false,
  can_share_to_timeline: true,
  can_reopen_registration: true,
  created_at: "2026-04-01T00:00:00Z",
  updated_at: "2026-04-01T00:00:00Z",
};

function event(overrides: Record<string, unknown> = {}): OrganizationEvent {
  const parsed = parseOrganizationEvent({ ...published, ...overrides });
  assert.ok(parsed);
  return parsed;
}

function placed(eventValue: OrganizationEvent): EventDetailAdminAction[] {
  const layout = eventDetailAdminLayout(eventValue);
  return [
    layout.primary,
    ...layout.secondary,
    ...layout.manage,
    ...layout.more,
    ...layout.danger,
    layout.shareChat ? "chat_share" : null,
  ].filter((action): action is EventDetailAdminAction => action != null);
}

test("same-day Tokyo range uses one date line and a compact time range", () => {
  const schedule = formatTokyoEventSchedule(
    "2026-10-28T20:25:00Z",
    "2026-10-29T03:30:00Z"
  );
  assert.equal(schedule.sameDay, true);
  assert.equal(schedule.startDateLine, "2026年10月29日（木）");
  assert.equal(schedule.timeRange, "05:25〜12:30");
});

test("overnight Tokyo range splits start and end onto separate dates", () => {
  const schedule = formatTokyoEventSchedule(
    "2026-10-29T06:00:00Z",
    "2026-10-29T16:00:00Z"
  );
  assert.equal(schedule.sameDay, false);
  assert.equal(schedule.startDateLine, "2026年10月29日（木）");
  assert.equal(schedule.startTime, "15:00");
  assert.equal(schedule.endDateLine, "2026年10月30日（金）");
  assert.equal(schedule.endTime, "01:00");
});

test("publication and signup badges stay independent of lottery copy", () => {
  assert.equal(eventPublicationStatusLabel("draft"), "下書き");
  assert.equal(eventPublicationStatusLabel("published"), "公開");
  assert.equal(eventPublicationStatusLabel("cancelled"), "中止");
  assert.equal(eventSignupModeLabel("announcement"), "告知のみ");
  assert.equal(eventSignupModeLabel("registration"), "申込あり");
});

test("venue and description omit empty fields", () => {
  assert.equal(
    eventVenueText(event({ venue_name: "大隈講堂", venue_address: "早稲田" })),
    "大隈講堂（早稲田）"
  );
  assert.equal(
    eventVenueText(event({ venue_name: "大隈講堂", venue_address: "" })),
    "大隈講堂"
  );
  assert.equal(eventVenueText(event({ venue_name: "", venue_address: "" })), "");
});

test("draft admin layout keeps publish edit duplicate and danger actions", () => {
  const draft = event({
    status: "draft",
    can_share_to_timeline: false,
    can_register: false,
  });
  const layout = eventDetailAdminLayout(draft);
  assert.equal(layout.primary, "publish");
  assert.deepEqual(layout.secondary, ["edit", "duplicate"]);
  assert.deepEqual(layout.danger, ["cancel", "delete"]);
  assert.equal(layout.shareChat, false);
  assert.equal(eventDetailAdminActionLabel("publish", draft), "イベントを公開する");
  assert.deepEqual(placed(draft).sort(), visibleEventDetailAdminActions(draft).sort());
});

test("published admin layout keeps share edit management and danger actions", () => {
  const live = event({
    can_run_lottery: true,
    can_share_to_timeline: true,
  });
  const layout = eventDetailAdminLayout(live);
  assert.equal(layout.primary, "timeline_share");
  assert.deepEqual(layout.secondary, ["edit"]);
  assert.deepEqual(layout.manage, ["registrations", "run_lottery"]);
  assert.equal(layout.more.includes("unpublish"), true);
  assert.equal(layout.more.includes("duplicate"), true);
  assert.equal(layout.more.includes("manage"), true);
  assert.deepEqual(layout.danger, ["cancel", "delete"]);
  assert.equal(layout.shareChat, true);
  assert.deepEqual(placed(live).sort(), visibleEventDetailAdminActions(live).sort());
});

test("cancelled admin layout keeps edit and hides cancel/delete", () => {
  const cancelled = event({
    status: "cancelled",
    can_share_to_timeline: false,
    can_register: false,
    registration_open: false,
    can_reopen_registration: false,
  });
  const layout = eventDetailAdminLayout(cancelled);
  assert.equal(layout.primary, null);
  assert.deepEqual(layout.secondary, ["edit"]);
  assert.equal(layout.danger.length, 0);
  assert.equal(layout.shareChat, false);
  assert.equal(visibleEventDetailAdminActions(cancelled).includes("cancel"), false);
  assert.equal(visibleEventDetailAdminActions(cancelled).includes("delete"), false);
  assert.deepEqual(placed(cancelled).sort(), visibleEventDetailAdminActions(cancelled).sort());
});

test("announcement events skip registrant management", () => {
  const announcement = event({
    signup_mode: "announcement",
    can_register: false,
    registration_open: false,
    can_reopen_registration: false,
  });
  const layout = eventDetailAdminLayout(announcement);
  assert.equal(layout.manage.includes("registrations"), false);
  assert.equal(layout.more.includes("registration_toggle"), false);
  assert.equal(eventSignupModeLabel(announcement.signup_mode), "告知のみ");
});
