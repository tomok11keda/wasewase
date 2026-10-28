import assert from "node:assert/strict";
import test from "node:test";
import {
  chatEventAnswerLabel,
  chatEventSafeFallbackPath,
  parseOrganizationChatEvent,
  parseOrganizationChatEventShareCard,
  recruitingChatEventPath,
} from "./orgChatEvents.ts";

test("parses chat event RSVP payload without email", () => {
  const parsed = parseOrganizationChatEvent({
    id: 4,
    organization_id: 1,
    organization_slug: "circle",
    chat_id: 9,
    title: "練習",
    description: "",
    starts_at: "2026-04-10T09:00:00Z",
    ends_at: null,
    venue_name: "体育館",
    rsvp_deadline: null,
    status: "scheduled",
    is_cancelled: false,
    is_ended: false,
    is_deadline_passed: false,
    viewer_answer: "going",
    can_rsvp: true,
    can_manage: true,
    chat_is_active: true,
    path: "/organizations/circle/recruiting-chat/events/4?chat=9",
    going_count: 1,
    not_going_count: 0,
    maybe_count: 0,
    unanswered_count: 3,
    member_count: 4,
    respondents: {
      going: [
        {
          user: {
            id: 2,
            username: "hana",
            display_name: "花",
            avatar_url: "",
            initial: "花",
          },
          answer: "going",
        },
      ],
      not_going: [],
      maybe: [],
      unanswered: [],
    },
  });
  assert.ok(parsed);
  assert.equal(parsed?.viewer_answer, "going");
  assert.equal(parsed?.unanswered_count, 3);
  assert.equal(chatEventAnswerLabel("going"), "参加");
  assert.equal(
    recruitingChatEventPath("circle", 4, 9),
    "/organizations/circle/recruiting-chat/events/4?chat=9"
  );
  assert.equal(chatEventSafeFallbackPath("circle"), "/orgs/circle");
});

test("chat event share cards stay private-path only", () => {
  const card = parseOrganizationChatEventShareCard({
    type: "org_chat_event",
    id: 4,
    available: true,
    content: {
      event_id: 4,
      organization_slug: "circle",
      chat_id: 9,
      title: "練習",
      starts_at: "2026-04-10T09:00:00Z",
      venue_name: "体育館",
      status: "scheduled",
      status_label: "チャット内",
      path: "/organizations/circle/recruiting-chat/events/4?chat=9",
    },
  });
  assert.equal(card?.type, "org_chat_event");
  assert.match(card?.content?.path || "", /recruiting-chat\/events\/4/);
});
