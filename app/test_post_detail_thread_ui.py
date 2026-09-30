"""Post-detail conversation thread UI (timeline comments)."""

from __future__ import annotations

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
        comment_type = api.split("export type TimelineComment =")[1].split(
            "export type QuotedPost"
        )[0]
        self.assertIn("parent_comment_id", comment_type)
        self.assertIn("reply_to", comment_type)

    def test_comment_identity_includes_username_and_existing_actions_only(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        comments = card.split("{showComments ? (")[1]
        self.assertIn("tweet-comment__identity", comments)
        self.assertIn("tweet-comment__handle", comments)
        self.assertIn("@{c.author.username}", comments)
        self.assertIn("削除済みユーザー", comments)
        self.assertIn("replyTarget", comments)
        self.assertIn("parent_comment_id", comments)
        self.assertIn("clearReplyTarget", comments)
        self.assertIn("tweet-comment__reply-to", comments)
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
