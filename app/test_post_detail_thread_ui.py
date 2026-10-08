"""Post-detail conversation thread UI (timeline comments)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class PostDetailThreadUiTests(SimpleTestCase):
    def test_detail_card_uses_thread_connector_and_nested_reply_fields(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        api = _read("frontend/src/features/timeline/api.ts")
        self.assertIn("tweet-thread-line", card)
        self.assertIn("tweet-thread-root", card)
        self.assertIn("hasThreadLine", card)
        self.assertIn("tweet-comment-thread", card)
        self.assertIn("tweet-comment-replies", card)
        self.assertIn("groupTimelineComments", card)
        self.assertNotIn("next.parent_comment_id === c.id", card)
        comment_type = api.split("export type TimelineComment =")[1].split(
            "export type QuotedPost"
        )[0]
        self.assertIn("parent_comment_id", comment_type)
        self.assertIn("reply_to", comment_type)

    def test_comment_identity_includes_username_and_existing_actions_only(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        comments = card.split("{showComments ? (")[1]
        self.assertIn("tweet-comment__identity", card)
        self.assertIn("tweet-comment__handle", card)
        self.assertIn("@{comment.author.username}", card)
        self.assertIn("削除済みユーザー", card)
        self.assertIn("replyTarget", comments)
        self.assertIn("clearReplyTarget", comments)
        self.assertIn("tweet-comment__reply-to", card)
        self.assertNotIn("toggleLike", comments)
        self.assertNotIn("toggleBookmark", comments)

    def test_detail_composer_is_compact_dock_and_detail_styles_are_scoped(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        css = _read("frontend/src/styles/post-detail.css")
        page = _read("frontend/src/pages/TimelinePostDetailPage.tsx")
        self.assertIn("tweet-comment-form--dock", card)
        self.assertIn("tweet-comment-form__target", card)
        self.assertIn("clearReplyTarget", card)
        self.assertIn("composerUser={me?.user ?? null}", page)
        self.assertIn(".post-detail-page .tweet-thread-line", css)
        self.assertIn(".post-detail-page .tweet-comment-form--dock", css)
        self.assertIn(".post-detail-page .tweet-comment.is-reply", css)
        self.assertIn("padding-left: 12px", css)
        self.assertNotIn("is-reply-2", css)
        self.assertNotIn("is-reply-3", css)
        self.assertIn("var(--nav-h)", css)
        self.assertNotIn("twitter", css.lower())
        self.assertNotIn("x.com", css.lower())

    def test_comment_groups_use_actual_parent_not_previous_row(self):
        helper = _read("frontend/src/features/timeline/commentThread.ts")
        self.assertIn("export function groupTimelineComments", helper)
        self.assertIn("visibleIds.has(parentId)", helper)
        self.assertIn("isDescendantOf(comment, current.root.id, comments)", helper)
        self.assertIn("parentId === current.root.id", helper)
        self.assertIn("UNAVAILABLE_REPLY_LABEL", helper)
        self.assertIn("返信先は表示できません", helper)
        self.assertIn("reply_to.is_unavailable", helper)
        self.assertIn("comment.parent_comment_id", helper)
        self.assertNotIn("comments[index - 1]", helper)

    def test_reply_label_is_button_and_jumps_only_when_available(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        helper = _read("frontend/src/features/timeline/commentThread.ts")
        self.assertIn("canJumpToReplyParent", helper)
        self.assertIn("timelineCommentDomId(comment.parent_comment_id)", card)
        self.assertIn("scrollIntoView", card)
        self.assertIn("is-flash", card)
        self.assertIn("COMMENT_FLASH_MS", card)
        self.assertIn("prefers-reduced-motion", card)
        self.assertIn('className={`tweet-comment__reply-to${', card)
        self.assertIn("disabled={!canJump}", card)
        self.assertIn("event.stopPropagation()", card)
        self.assertIn("if (!el) return", card)
        self.assertIn("if (!canJumpToReplyParent(comment)", card)

    def test_reply_post_still_sends_clicked_comment_id(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        api = _read("frontend/src/features/timeline/api.ts")
        self.assertIn("addComment(", card)
        self.assertIn("replyTarget?.id ?? null", card)
        self.assertIn("id: row.id", card)
        self.assertIn("insertThreadedComment(post.comments, comment)", card)
        self.assertIn("parent_comment_id?: number", api)

    def test_indent_stays_one_level_and_rail_is_group_scoped(self):
        css = _read("frontend/src/styles/post-detail.css")
        self.assertIn(".post-detail-page .tweet-comment-replies::before", css)
        self.assertIn(
            "left: calc(var(--tweet-avatar-size, 40px) / 2 - 1px)", css
        )
        self.assertIn("padding-left: 12px", css)
        self.assertNotIn("padding-left: 24px", css)
        self.assertNotIn("padding-left: 36px", css)
        self.assertNotIn("padding-left: 48px", css)
        self.assertIn("scroll-margin-top: var(--wase-chrome-offset", css)
        self.assertIn("var(--nav-h)", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("@media (max-width: 430px)", css)
        self.assertIn("@media (max-width: 320px)", css)
        self.assertIn("is-flash", css)

    def test_comment_ui_stays_detail_scoped_and_skips_other_surfaces(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        home = _read("frontend/src/pages/HomePage.tsx")
        community = _read("frontend/src/pages/CommunityThreadPage.tsx")
        self.assertIn('variant === "detail"', card)
        self.assertIn("showComments", card)
        self.assertNotIn("tweet-comment-thread", home)
        self.assertNotIn("groupTimelineComments", community)
        self.assertIn("scrollToReply", community)

    def test_executable_comment_thread_script_matches_source(self):
        helper = _read("frontend/src/features/timeline/commentThread.ts")
        script = _read("frontend/scripts/verify_comment_thread.mjs")
        self.assertIn("返信先は表示できません", helper)
        self.assertIn("返信先は表示できません", script)
        self.assertIn("export function groupTimelineComments", helper)
        result = subprocess.run(
            ["node", "frontend/scripts/verify_comment_thread.mjs"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("comment thread tests ok", result.stdout)
