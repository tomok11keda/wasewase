import assert from "node:assert/strict";
import test from "node:test";
import {
  canShowEventManage,
  defaultLotteryEligibleIds,
  eventCapacityLabel,
  eventFormToPayload,
  formFromOrganizationEvent,
  eventPageView,
  eventStatusLabel,
  formatTokyoDateTime,
  isoToTokyoInput,
  lotteryResultLabel,
  organizationEventEditPath,
  organizationEventErrorMessage,
  organizationEventLotteryPath,
  organizationEventManagePath,
  organizationEventPath,
  parseOrganizationEvent,
  parseOrganizationEventListPayload,
  parseOrganizationEventLottery,
  parseOrganizationEventLotteryShareCard,
  parseOrganizationEventShareCard,
  parseOrganizationEventRegistrant,
  tokyoInputToIso,
  validateEventForm,
  validateLotterySetup,
  viewerLotteryRegistrationLabel,
  emptyEventForm,
  EVENT_SIGNUP_MODE_OPTIONS,
} from "./orgEvents.ts";

const published = {
  id: 11,
  organization_id: 3,
  organization_slug: "tennis",
  organization_name: "テニスサークル",
  organization_avatar_url: "",
  title: "新歓説明会",
  description: "紹介",
  starts_at: "2026-04-10T09:00:00Z",
  ends_at: "2026-04-10T11:00:00Z",
  venue_name: "大隈講堂",
  venue_address: "早稲田",
  registration_deadline: null,
  status: "published",
  registration_open: true,
  registered_count: 12,
  is_ended: false,
  is_deadline_passed: false,
  viewer_status: null,
  viewer_registered: false,
  can_register: true,
  can_cancel_registration: false,
  can_manage: false,
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
  can_reopen_registration: false,
  created_at: "2026-04-01T00:00:00Z",
  updated_at: "2026-04-01T00:00:00Z",
};

test("parses event list and rejects email on registrants", () => {
  const parsed = parseOrganizationEvent(published);
  assert.ok(parsed);
  assert.equal(parsed?.title, "新歓説明会");
  assert.equal(parsed?.can_register, true);
  assert.equal(parsed?.signup_mode, "registration");
  assert.equal(parsed?.can_share_to_timeline, false);
  assert.equal(parsed?.image_url, "");
  assert.equal(
    parseOrganizationEvent({ ...published, image_url: "/media/event_images/a.gif" })
      ?.image_url,
    "/media/event_images/a.gif"
  );
  const list = parseOrganizationEventListPayload({
    ok: true,
    events: [published],
    has_more: false,
    next_offset: 1,
    can_manage: false,
  });
  assert.equal(list?.events.length, 1);
  assert.equal(
    parseOrganizationEventRegistrant({
      id: 1,
      status: "registered",
      created_at: "2026-04-01T00:00:00Z",
      user: {
        id: 9,
        username: "hana",
        display_name: "花",
        avatar_url: "",
        initial: "花",
        email: "hana@waseda.jp",
      },
    }),
    null
  );
});

test("status labels distinguish ended cancelled registered and lottery", () => {
  assert.equal(eventStatusLabel(parseOrganizationEvent(published)!), "募集中");
  assert.equal(
    eventStatusLabel(parseOrganizationEvent({ ...published, is_ended: true })!),
    "終了"
  );
  assert.equal(
    eventStatusLabel(
      parseOrganizationEvent({ ...published, status: "cancelled" })!
    ),
    "中止"
  );
  assert.equal(
    eventStatusLabel(
      parseOrganizationEvent({
        ...published,
        viewer_registered: true,
        can_register: false,
      })!
    ),
    "申込済み"
  );
  assert.equal(
    eventStatusLabel(
      parseOrganizationEvent({
        ...published,
        has_lottery: true,
        viewer_lottery_result: "selected",
      })!
    ),
    "当選"
  );
  assert.equal(
    eventCapacityLabel(parseOrganizationEvent(published)!),
    "申込 12人"
  );
});

test("admin UI stays hidden until the server confirms manage", () => {
  assert.equal(canShowEventManage({ hydrated: false, canManage: true }), false);
  assert.equal(canShowEventManage({ hydrated: true, canManage: false }), false);
  assert.equal(canShowEventManage({ hydrated: true, canManage: true }), true);
});

test("event page view maps 404 to missing and network to error", () => {
  assert.equal(
    eventPageView({ loading: true, error: null, event: null }),
    "loading"
  );
  assert.equal(
    eventPageView({ loading: false, error: "not_found", event: null }),
    "missing"
  );
  assert.equal(
    eventPageView({ loading: false, error: "load_failed", event: null }),
    "error"
  );
  assert.equal(
    eventPageView({
      loading: false,
      error: null,
      event: parseOrganizationEvent(published),
    }),
    "ready"
  );
});

test("create form starts empty and edit form hydrates Tokyo datetime-local values", () => {
  const empty = emptyEventForm();
  assert.equal(empty.title, "");
  assert.equal(empty.starts_at, "");
  assert.equal(empty.registration_deadline, "");
  assert.equal(empty.registration_open, true);
  const parsed = parseOrganizationEvent({
    ...published,
    starts_at: "2026-04-10T09:00:00Z",
    ends_at: "2026-04-10T11:00:00Z",
    registration_deadline: "2026-04-10T08:00:00Z",
    registration_open: false,
  });
  assert.ok(parsed);
  const hydrated = formFromOrganizationEvent(parsed);
  assert.equal(hydrated.title, "新歓説明会");
  assert.equal(hydrated.venue_name, "大隈講堂");
  assert.equal(hydrated.starts_at, "2026-04-10T18:00");
  assert.equal(hydrated.ends_at, "2026-04-10T20:00");
  assert.equal(hydrated.registration_deadline, "2026-04-10T17:00");
  assert.equal(hydrated.registration_open, false);
});

test("form validation and Tokyo conversion round-trip", () => {
  const empty = validateEventForm(emptyEventForm());
  assert.ok(empty.title);
  assert.ok(empty.starts_at);
  const form = {
    ...emptyEventForm(),
    title: "説明会",
    description: "紹介文は残す",
    venue_name: "戸山キャンパス",
    venue_address: "早稲田",
    starts_at: "2026-04-10T18:00",
    ends_at: "2026-04-10T17:00",
    registration_deadline: "2026-04-10T12:00",
  };
  const errors = validateEventForm(form);
  assert.ok(errors.ends_at);
  assert.equal(form.title, "説明会");
  assert.equal(form.description, "紹介文は残す");
  assert.equal(form.venue_address, "早稲田");
  assert.equal(form.registration_deadline, "2026-04-10T12:00");
  const iso = tokyoInputToIso("2026-04-10T18:00");
  assert.equal(isoToTokyoInput(iso), "2026-04-10T18:00");
  const payload = eventFormToPayload({
    ...form,
    ends_at: "2026-04-10T20:00",
  });
  assert.equal(payload.capacity, undefined);
  assert.equal(typeof payload.starts_at, "string");
  assert.match(String(payload.starts_at), /Z$/);
});

test("Tokyo display stays on Asia/Tokyo independent of UTC storage", () => {
  const label = formatTokyoDateTime("2026-04-10T09:00:00Z");
  assert.match(label, /4月10日|4\/10/);
  assert.match(label, /18:00/);
});

test("paths stay basename-relative and error copy is not cancelled for network", () => {
  assert.equal(
    organizationEventPath("tennis", 11),
    "/organizations/tennis/events/11"
  );
  assert.equal(
    organizationEventManagePath("tennis"),
    "/organizations/tennis/events/manage"
  );
  assert.equal(
    organizationEventEditPath("tennis", 11),
    "/organizations/tennis/events/11/edit"
  );
  assert.equal(
    organizationEventLotteryPath("tennis", 11),
    "/organizations/tennis/events/11/lottery"
  );
  assert.equal(
    organizationEventErrorMessage("load_failed", "通信に失敗しました。"),
    "通信に失敗しました。"
  );
  assert.equal(
    organizationEventErrorMessage("not_found", "x"),
    "イベントが見つからないか、表示できません。"
  );
  assert.equal(
    organizationEventErrorMessage("share_cooldown", "x"),
    "同じイベントは10分間に1回までシェアできます。しばらく待ってからもう一度お試しください。"
  );
});

test("lottery setup defaults everyone eligible and validates notes", () => {
  const registrations = [
    {
      id: 1,
      status: "registered" as const,
      created_at: "2026-04-01T00:00:00Z",
      user: {
        id: 9,
        username: "hana",
        display_name: "花",
        avatar_url: "",
        initial: "花",
      },
    },
    {
      id: 2,
      status: "registered" as const,
      created_at: "2026-04-01T00:00:00Z",
      user: {
        id: 10,
        username: "ken",
        display_name: "ケン",
        avatar_url: "",
        initial: "ケ",
      },
    },
  ];
  assert.deepEqual(defaultLotteryEligibleIds(registrations), [9, 10]);
  assert.equal(lotteryResultLabel("excluded"), "対象外");
  const tooMany = validateLotterySetup({
    winnerCount: "3",
    eligibleCount: 2,
    notes: {},
  });
  assert.ok(tooMany.winner_count);
  const longNote = validateLotterySetup({
    winnerCount: "1",
    eligibleCount: 2,
    notes: { 9: "あ".repeat(101) },
  });
  assert.ok(longNote.exclusion_note);
  const parsed = parseOrganizationEventLottery({
    id: 4,
    event_id: 11,
    status: "completed",
    executed_at: "2026-04-02T00:00:00Z",
    applicant_count: 2,
    eligible_count: 1,
    excluded_count: 1,
    winner_count: 1,
    not_selected_count: 0,
    shared: false,
    shared_at: null,
    can_share: true,
    can_manage: true,
    can_view: true,
    selected: [
      {
        id: 1,
        result: "selected",
        user: {
          id: 10,
          username: "ken",
          display_name: "ケン",
          avatar_url: "",
          initial: "ケ",
        },
      },
    ],
    not_selected: [],
    excluded: [
      {
        id: 2,
        result: "excluded",
        exclusion_note: "スタッフ",
        user: {
          id: 9,
          username: "hana",
          display_name: "花",
          avatar_url: "",
          initial: "花",
          email: "hana@waseda.jp",
        },
      },
    ],
  });
  assert.equal(parsed, null);
  const card = parseOrganizationEventLotteryShareCard({
    type: "org_event_lottery",
    id: 4,
    available: true,
    content: {
      event_id: 11,
      organization_slug: "tennis",
      title: "新歓説明会",
      applicant_count: 48,
      eligible_count: 44,
      winner_count: 20,
      not_selected_count: 24,
      excluded_count: 4,
      path: "/organizations/tennis/events/11/lottery",
    },
  });
  assert.equal(card?.content?.winner_count, 20);
  assert.equal(card?.content?.path, "/organizations/tennis/events/11/lottery");
  const eventCard = parseOrganizationEventShareCard({
    type: "org_event",
    id: 11,
    available: true,
    content: {
      event_id: 11,
      organization_slug: "tennis",
      title: "新歓説明会",
      starts_at: "2026-04-02T00:00:00Z",
      ends_at: "2026-04-02T02:00:00Z",
      venue_name: "大隈講堂",
      path: "/organizations/tennis/events/11",
    },
  });
  assert.equal(eventCard?.content?.title, "新歓説明会");
  assert.equal(eventCard?.type, "org_event");
  const selfOnly = parseOrganizationEventLottery({
    id: 4,
    event_id: 11,
    status: "completed",
    executed_at: "2026-04-02T00:00:00Z",
    applicant_count: 2,
    eligible_count: 1,
    excluded_count: 1,
    winner_count: 1,
    not_selected_count: 0,
    shared: false,
    shared_at: null,
    can_share: false,
    can_manage: false,
    can_view: false,
    lists_visible: false,
    viewer_entry: {
      id: 2,
      result: "excluded",
      exclusion_note: "スタッフ",
      user: {
        id: 9,
        username: "hana",
        display_name: "花",
        avatar_url: "",
        initial: "花",
      },
    },
  });
  assert.equal(selfOnly?.lists_visible, false);
  assert.equal(selfOnly?.viewer_entry?.result, "excluded");
  assert.equal(selfOnly?.selected.length, 0);
  assert.equal(
    organizationEventErrorMessage("lottery_closed", "x"),
    "抽選が確定しているため、この操作はできません。"
  );
  assert.equal(
    organizationEventErrorMessage("registrants_changed", "x"),
    "申込者が変わったため、最新の一覧を確認してから抽選してください。"
  );
  const declined = parseOrganizationEvent({
    ...published,
    has_lottery: true,
    viewer_status: "cancelled",
    viewer_registered: false,
    viewer_lottery_result: "selected",
    can_register: false,
    can_reopen_registration: false,
  });
  assert.equal(viewerLotteryRegistrationLabel(declined!), "参加辞退");
  assert.equal(eventStatusLabel(declined!), "当選");
});

test("signup mode cards keep both draft payloads without extra fields", () => {
  assert.deepEqual(
    EVENT_SIGNUP_MODE_OPTIONS.map((option) => option.value),
    ["registration", "announcement"]
  );
  const base = {
    ...emptyEventForm(),
    title: "新歓",
    venue_name: "キャンパス",
    starts_at: "2026-11-01T10:00",
    ends_at: "2026-11-01T16:00",
  };
  for (const option of EVENT_SIGNUP_MODE_OPTIONS) {
    const form = { ...base, signup_mode: option.value };
    assert.deepEqual(validateEventForm(form), {});
    const payload = eventFormToPayload(form);
    assert.equal(payload.signup_mode, option.value);
    assert.equal(
      payload.registration_open,
      option.value === "registration"
    );
  }
});

test("announcement events parse as 告知のみ and skip deadline validation", () => {
  const parsed = parseOrganizationEvent({
    ...published,
    signup_mode: "announcement",
    can_register: false,
    registration_open: false,
  });
  assert.equal(parsed?.signup_mode, "announcement");
  assert.equal(eventStatusLabel(parsed!), "告知のみ");
  const form = {
    ...emptyEventForm(),
    title: "早稲田祭屋台",
    venue_name: "キャンパス",
    starts_at: "2026-11-01T10:00",
    ends_at: "2026-11-01T16:00",
    signup_mode: "announcement" as const,
  };
  assert.deepEqual(validateEventForm(form), {});
  const payload = eventFormToPayload(form);
  assert.equal(payload.signup_mode, "announcement");
  assert.equal(payload.registration_open, false);
});
