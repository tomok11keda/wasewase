from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from app import views as app_views
from app import marketplace_views as flea_views
from app import spa_views
from app import timeline_api_views
from app import community_api_views
from app import flea_api_views
from app import profile_api_views
from app import dm_api_views
from app import notification_api_views
from app import auth_api_views
from app import follow_api_views
from app.spa_canonical import spa_get_redirect

_HOME_REDIRECT = RedirectView.as_view(url="/", permanent=True)

# Classic GET pages → React routes (App.tsx). Views/templates kept for WASE_REACT_SPA=False.
_spa = spa_get_redirect
_home = _spa(lambda request, **kw: "/")(app_views.index)
_search = _spa(lambda request, **kw: "/search")(app_views.search)
_flea = _spa(lambda request, **kw: "/flea")(flea_views.flea_index)
_more = _spa(lambda request, **kw: "/more")(app_views.more_index)
_timetable = _spa(lambda request, **kw: "/timetable")(app_views.timetable_index)
_timetable_user = _spa(lambda request, pk, **kw: f"/timetable/user/{pk}")(
    app_views.timetable_user
)
_communities = _spa(lambda request, **kw: "/communities")(app_views.communities_index)
_community_thread = _spa(
    lambda request, slug, thread_pk, **kw: f"/communities/{slug}/threads/{thread_pk}"
)(app_views.community_thread_detail)
_exhibit = _spa(lambda request, **kw: "/flea/exhibit")(flea_views.exhibit)
_product = _spa(lambda request, pk, **kw: f"/flea/products/{pk}")(
    flea_views.product_detail
)
_product_trade = _spa(lambda request, pk, **kw: f"/flea/products/{pk}")(
    flea_views.product_trade
)
_chat = _spa(lambda request, room_pk, **kw: f"/flea/chats/{room_pk}")(
    flea_views.chat_room
)
_user_profile = _spa(lambda request, pk, **kw: f"/users/{pk}")(app_views.user_profile)
_dm_inbox = _spa(lambda request, **kw: "/dm")(app_views.user_dm_inbox)
_dm_room = _spa(lambda request, room_pk, **kw: f"/dm/{room_pk}")(app_views.user_dm_room)
_dm_group_create = _spa(lambda request, **kw: "/dm/groups/new")(
    app_views.dm_group_create
)
_dm_group_room = _spa(lambda request, room_pk, **kw: f"/dm/groups/{room_pk}")(
    app_views.dm_group_room
)
_notifications = _spa(lambda request, **kw: "/notifications")(app_views.notifications)
_login = _spa(lambda request, **kw: "/login")(app_views.AppLoginView.as_view())
_signup = _spa(lambda request, **kw: "/signup")(app_views.signup)
_verify_otp = _spa(lambda request, **kw: "/verify")(app_views.verify_otp)
_password_reset = _spa(lambda request, **kw: "/password-reset")(
    app_views.password_reset_request
)
_password_reset_verify = _spa(lambda request, **kw: "/password-reset/verify")(
    app_views.password_reset_verify
)
_password_reset_set = _spa(lambda request, **kw: "/password-reset/set")(
    app_views.password_reset_set
)

urlpatterns = [
    path("manifest.json", app_views.pwa_manifest, name="pwa_manifest"),
    path("service-worker.js", app_views.pwa_service_worker, name="pwa_service_worker"),
    path("ads.txt", app_views.ads_txt, name="ads_txt"),
    path("privacy/", app_views.privacy_policy, name="privacy"),
    path("terms/", app_views.terms_of_service, name="terms"),
    path("support/", app_views.support_page, name="support"),
    path("admin/", admin.site.urls),
    # React SPA (feature-flagged). Classic routes below remain the default UX.
    path("api/v1/me/", spa_views.api_v1_me, name="api_v1_me"),
    path(
        "api/v1/me/privacy/",
        follow_api_views.api_v1_me_privacy,
        name="api_v1_me_privacy",
    ),
    path(
        "api/v1/follow-requests/",
        follow_api_views.api_v1_follow_requests,
        name="api_v1_follow_requests",
    ),
    path(
        "api/v1/follow-requests/<int:pk>/accept/",
        follow_api_views.api_v1_follow_request_accept,
        name="api_v1_follow_request_accept",
    ),
    path(
        "api/v1/follow-requests/<int:pk>/reject/",
        follow_api_views.api_v1_follow_request_reject,
        name="api_v1_follow_request_reject",
    ),
    path(
        "api/v1/timeline/",
        timeline_api_views.api_v1_timeline_collection,
        name="api_v1_timeline_list",
    ),
    path(
        "api/v1/timeline/impressions/",
        timeline_api_views.api_v1_timeline_impressions,
        name="api_v1_timeline_impressions",
    ),
    path(
        "api/v1/timeline/<int:pk>/like/",
        timeline_api_views.api_v1_timeline_like,
        name="api_v1_timeline_like",
    ),
    path(
        "api/v1/timeline/<int:pk>/bookmark/",
        timeline_api_views.api_v1_timeline_bookmark,
        name="api_v1_timeline_bookmark",
    ),
    path(
        "api/v1/timeline/<int:pk>/comments/",
        timeline_api_views.api_v1_timeline_comment,
        name="api_v1_timeline_comment",
    ),
    path(
        "api/v1/timeline/<int:pk>/quote/",
        timeline_api_views.api_v1_timeline_quote,
        name="api_v1_timeline_quote",
    ),
    path(
        "api/v1/timeline/<int:pk>/",
        timeline_api_views.api_v1_timeline_delete,
        name="api_v1_timeline_delete",
    ),
    path(
        "api/v1/timeline/comments/<int:pk>/",
        timeline_api_views.api_v1_timeline_comment_delete,
        name="api_v1_timeline_comment_delete",
    ),
    path(
        "api/v1/communities/threads/",
        community_api_views.api_v1_community_threads,
        name="api_v1_community_threads",
    ),
    path(
        "api/v1/communities/<slug:slug>/threads/<int:thread_pk>/",
        community_api_views.api_v1_community_thread_detail,
        name="api_v1_community_thread_detail",
    ),
    path(
        "api/v1/communities/<slug:slug>/threads/<int:thread_pk>/replies/",
        community_api_views.api_v1_community_thread_reply,
        name="api_v1_community_thread_reply",
    ),
    path(
        "api/v1/communities/<slug:slug>/threads/<int:thread_pk>/delete/",
        community_api_views.api_v1_community_thread_delete,
        name="api_v1_community_thread_delete",
    ),
    path(
        "api/v1/communities/<slug:slug>/threads/<int:thread_pk>/replies/<int:reply_pk>/delete/",
        community_api_views.api_v1_community_reply_delete,
        name="api_v1_community_reply_delete",
    ),
    path(
        "api/v1/communities/<slug:slug>/threads/<int:thread_pk>/replies/<int:reply_pk>/",
        community_api_views.api_v1_community_reply_edit,
        name="api_v1_community_reply_edit",
    ),
    path(
        "api/v1/flea/",
        flea_api_views.api_v1_flea_list,
        name="api_v1_flea_list",
    ),
    path(
        "api/v1/flea/products/",
        flea_api_views.api_v1_flea_products,
        name="api_v1_flea_products",
    ),
    path(
        "api/v1/flea/products/<int:pk>/",
        flea_api_views.api_v1_flea_product_detail,
        name="api_v1_flea_product_detail",
    ),
    path(
        "api/v1/flea/products/<int:pk>/like/",
        flea_api_views.api_v1_flea_product_like,
        name="api_v1_flea_product_like",
    ),
    path(
        "api/v1/flea/products/<int:pk>/bookmark/",
        flea_api_views.api_v1_flea_product_bookmark,
        name="api_v1_flea_product_bookmark",
    ),
    path(
        "api/v1/flea/products/<int:pk>/comments/",
        flea_api_views.api_v1_flea_product_comment,
        name="api_v1_flea_product_comment",
    ),
    path(
        "api/v1/flea/products/<int:pk>/purchase/",
        flea_api_views.api_v1_flea_product_purchase,
        name="api_v1_flea_product_purchase",
    ),
    path(
        "api/v1/flea/products/<int:pk>/chat/start/",
        flea_api_views.api_v1_flea_product_chat_start,
        name="api_v1_flea_product_chat_start",
    ),
    path(
        "api/v1/flea/products/<int:pk>/delete/",
        flea_api_views.api_v1_flea_product_delete,
        name="api_v1_flea_product_delete",
    ),
    path(
        "api/v1/flea/products/<int:pk>/share/",
        flea_api_views.api_v1_flea_product_share,
        name="api_v1_flea_product_share",
    ),
    path(
        "api/v1/flea/products/<int:pk>/review/",
        flea_api_views.api_v1_flea_product_review,
        name="api_v1_flea_product_review",
    ),
    path(
        "api/v1/flea/chats/<int:room_pk>/",
        flea_api_views.api_v1_flea_chat_detail,
        name="api_v1_flea_chat_detail",
    ),
    path(
        "api/v1/flea/chats/<int:room_pk>/messages/",
        flea_api_views.api_v1_flea_chat_messages,
        name="api_v1_flea_chat_messages",
    ),
    path(
        "api/v1/flea/chats/<int:room_pk>/messages/send/",
        flea_api_views.api_v1_flea_chat_send,
        name="api_v1_flea_chat_send",
    ),
    path(
        "api/v1/flea/chats/<int:room_pk>/confirm/",
        flea_api_views.api_v1_flea_chat_confirm,
        name="api_v1_flea_chat_confirm",
    ),
    path(
        "api/v1/flea/chats/<int:room_pk>/handover-complete/",
        flea_api_views.api_v1_flea_chat_handover,
        name="api_v1_flea_chat_handover",
    ),
    path(
        "api/v1/profile/<int:pk>/",
        profile_api_views.api_v1_profile_detail,
        name="api_v1_profile_detail",
    ),
    path(
        "api/v1/profile/<int:pk>/posts/",
        profile_api_views.api_v1_profile_posts,
        name="api_v1_profile_posts",
    ),
    path(
        "api/v1/profile/<int:pk>/products/",
        profile_api_views.api_v1_profile_products,
        name="api_v1_profile_products",
    ),
    path(
        "api/v1/profile/<int:pk>/bookmarks/",
        profile_api_views.api_v1_profile_bookmarks,
        name="api_v1_profile_bookmarks",
    ),
    path(
        "api/v1/profile/<int:pk>/follow/",
        profile_api_views.api_v1_profile_follow,
        name="api_v1_profile_follow",
    ),
    path(
        "api/v1/profile/<int:pk>/block/",
        profile_api_views.api_v1_profile_block,
        name="api_v1_profile_block",
    ),
    path(
        "api/v1/search/",
        profile_api_views.api_v1_search,
        name="api_v1_search",
    ),
    path(
        "api/v1/dm/inbox/",
        dm_api_views.api_v1_dm_inbox,
        name="api_v1_dm_inbox",
    ),
    path(
        "api/v1/dm/start/",
        dm_api_views.api_v1_dm_start,
        name="api_v1_dm_start",
    ),
    path(
        "api/v1/dm/message-requests/",
        dm_api_views.api_v1_dm_message_requests,
        name="api_v1_dm_message_requests",
    ),
    path(
        "api/v1/dm/rooms/<int:room_pk>/",
        dm_api_views.api_v1_dm_room,
        name="api_v1_dm_room",
    ),
    path(
        "api/v1/dm/rooms/<int:room_pk>/messages/",
        dm_api_views.api_v1_dm_messages,
        name="api_v1_dm_messages",
    ),
    path(
        "api/v1/dm/rooms/<int:room_pk>/messages/send/",
        dm_api_views.api_v1_dm_send,
        name="api_v1_dm_send",
    ),
    path(
        "api/v1/dm/rooms/<int:room_pk>/requests/accept/",
        dm_api_views.api_v1_dm_request_accept,
        name="api_v1_dm_request_accept",
    ),
    path(
        "api/v1/dm/rooms/<int:room_pk>/requests/decline/",
        dm_api_views.api_v1_dm_request_decline,
        name="api_v1_dm_request_decline",
    ),
    path(
        "api/v1/dm/groups/",
        dm_api_views.api_v1_dm_groups,
        name="api_v1_dm_groups",
    ),
    path(
        "api/v1/dm/groups/<int:room_pk>/",
        dm_api_views.api_v1_dm_group_room,
        name="api_v1_dm_group_room",
    ),
    path(
        "api/v1/dm/groups/<int:room_pk>/messages/",
        dm_api_views.api_v1_dm_group_messages,
        name="api_v1_dm_group_messages",
    ),
    path(
        "api/v1/dm/groups/<int:room_pk>/messages/send/",
        dm_api_views.api_v1_dm_group_send,
        name="api_v1_dm_group_send",
    ),
    path(
        "api/v1/dm/groups/<int:room_pk>/invite/",
        dm_api_views.api_v1_dm_group_invite,
        name="api_v1_dm_group_invite",
    ),
    path(
        "api/v1/dm/groups/<int:room_pk>/invitations/accept/",
        dm_api_views.api_v1_dm_group_accept,
        name="api_v1_dm_group_accept",
    ),
    path(
        "api/v1/dm/groups/<int:room_pk>/invitations/decline/",
        dm_api_views.api_v1_dm_group_decline,
        name="api_v1_dm_group_decline",
    ),
    path(
        "api/v1/notifications/",
        notification_api_views.api_v1_notifications_list,
        name="api_v1_notifications_list",
    ),
    path(
        "api/v1/notifications/unread-count/",
        notification_api_views.api_v1_notifications_unread,
        name="api_v1_notifications_unread",
    ),
    path(
        "api/v1/notifications/mark-read/",
        notification_api_views.api_v1_notifications_mark_read,
        name="api_v1_notifications_mark_read",
    ),
    path(
        "api/v1/auth/csrf/",
        auth_api_views.api_v1_auth_csrf,
        name="api_v1_auth_csrf",
    ),
    path(
        "api/v1/auth/me/",
        auth_api_views.api_v1_auth_me,
        name="api_v1_auth_me",
    ),
    path(
        "api/v1/auth/signup-meta/",
        auth_api_views.api_v1_auth_signup_meta,
        name="api_v1_auth_signup_meta",
    ),
    path(
        "api/v1/auth/login/",
        auth_api_views.api_v1_auth_login,
        name="api_v1_auth_login",
    ),
    path(
        "api/v1/auth/logout/",
        auth_api_views.api_v1_auth_logout,
        name="api_v1_auth_logout",
    ),
    path(
        "api/v1/auth/browse/",
        auth_api_views.api_v1_auth_browse,
        name="api_v1_auth_browse",
    ),
    path(
        "api/v1/auth/signup/",
        auth_api_views.api_v1_auth_signup,
        name="api_v1_auth_signup",
    ),
    path(
        "api/v1/auth/verify/",
        auth_api_views.api_v1_auth_verify,
        name="api_v1_auth_verify",
    ),
    path(
        "api/v1/auth/verify/resend/",
        auth_api_views.api_v1_auth_verify_resend,
        name="api_v1_auth_verify_resend",
    ),
    path(
        "api/v1/auth/password-reset/",
        auth_api_views.api_v1_auth_password_reset,
        name="api_v1_auth_password_reset",
    ),
    path(
        "api/v1/auth/password-reset/verify/",
        auth_api_views.api_v1_auth_password_reset_verify,
        name="api_v1_auth_password_reset_verify",
    ),
    path(
        "api/v1/auth/password-reset/resend/",
        auth_api_views.api_v1_auth_password_reset_resend,
        name="api_v1_auth_password_reset_resend",
    ),
    path(
        "api/v1/auth/password-reset/set/",
        auth_api_views.api_v1_auth_password_reset_set,
        name="api_v1_auth_password_reset_set",
    ),
    path("app/", spa_views.spa_app, name="spa_app"),
    path("app/<path:rest>", spa_views.spa_app, name="spa_app_path"),
    path("", _home, name="home"),
    path("search/", _search, name="search"),
    path("api/search/", app_views.api_search, name="api_search"),
    path("flea/", _flea, name="flea_index"),
    path("more/", _more, name="more_index"),
    path("timetable/", _timetable, name="timetable_index"),
    path("timetable/user/<int:pk>/", _timetable_user, name="timetable_user"),
    path(
        "api/timetable/visibility/",
        app_views.api_timetable_visibility,
        name="api_timetable_visibility",
    ),
    path(
        "api/timetable/slots/",
        app_views.api_timetable_slots,
        name="api_timetable_slots",
    ),
    path(
        "api/timetable/user/<int:pk>/",
        app_views.api_timetable_user_slots,
        name="api_timetable_user_slots",
    ),
    path(
        "api/timetable/slot/",
        app_views.api_timetable_slot,
        name="api_timetable_slot",
    ),
    path("communities/", _communities, name="communities_index"),
    path("communities/thread/", app_views.create_community_thread, name="create_community_thread"),
    path(
        "communities/<slug:slug>/",
        app_views.community_detail,
        name="community_detail",
    ),
    path(
        "communities/<slug:slug>/threads/<int:thread_pk>/",
        _community_thread,
        name="community_thread_detail",
    ),
    path(
        "communities/<slug:slug>/threads/<int:thread_pk>/reply/",
        app_views.create_community_thread_reply,
        name="create_community_thread_reply",
    ),
    path(
        "communities/<slug:slug>/threads/<int:thread_pk>/delete/",
        app_views.delete_community_thread,
        name="delete_community_thread",
    ),
    path(
        "communities/<slug:slug>/threads/<int:thread_pk>/replies/<int:reply_pk>/delete/",
        app_views.delete_community_thread_reply,
        name="delete_community_thread_reply",
    ),
    path(
        "communities/<slug:slug>/threads/<int:thread_pk>/replies/<int:reply_pk>/edit/",
        app_views.edit_community_thread_reply,
        name="edit_community_thread_reply",
    ),
    # フリマ機能
    path("exhibit/", _exhibit, name="exhibit"),
    path("product/<int:pk>/", _product, name="product_detail"),
    path("product/<int:pk>/delete/", flea_views.delete_product, name="delete_product"),
    path("product/<int:pk>/like/", flea_views.toggle_like, name="toggle_like"),
    path(
        "product/<int:pk>/share-to-timeline/",
        flea_views.share_product_to_timeline,
        name="share_product_to_timeline",
    ),
    path("product/<int:pk>/purchase/", flea_views.purchase_product, name="purchase_product"),
    path("product/<int:pk>/chat/start/", flea_views.start_product_chat, name="start_product_chat"),
    path("chat/<int:room_pk>/", _chat, name="chat_room"),
    path("chat/<int:room_pk>/messages/", flea_views.chat_room_messages, name="chat_room_messages"),
    path("chat/<int:room_pk>/message/", flea_views.send_chat_message, name="send_chat_message"),
    path(
        "chat/<int:room_pk>/confirm/",
        flea_views.confirm_product_trade,
        name="confirm_product_trade",
    ),
    path(
        "chat/<int:room_pk>/handover-complete/",
        flea_views.complete_product_handover,
        name="complete_product_handover",
    ),
    path("product/<int:pk>/trade/", _product_trade, name="product_trade"),
    path("product/<int:pk>/trade/complete/", flea_views.complete_trade, name="complete_trade"),
    path("product/<int:pk>/review/", flea_views.submit_review, name="submit_review"),
    path("product/<int:pk>/trade-message/", flea_views.send_trade_message, name="send_trade_message"),
    path("user/<int:pk>/", _user_profile, name="user_profile"),
    path("user/<int:pk>/dm/start/", app_views.start_user_dm, name="start_user_dm"),
    path("dm/", _dm_inbox, name="user_dm_inbox"),
    path("api/dm/unread-summary/", app_views.dm_unread_summary, name="dm_unread_summary"),
    path("dm/<int:room_pk>/", _dm_room, name="user_dm_room"),
    path(
        "dm/groups/create/",
        _dm_group_create,
        name="dm_group_create",
    ),
    path(
        "dm/groups/<int:room_pk>/",
        _dm_group_room,
        name="dm_group_room",
    ),
    path(
        "dm/groups/<int:room_pk>/messages/",
        app_views.dm_group_room_messages,
        name="dm_group_room_messages",
    ),
    path(
        "dm/groups/<int:room_pk>/message/",
        app_views.send_group_message,
        name="send_group_message",
    ),
    path(
        "dm/<int:room_pk>/messages/",
        app_views.user_dm_room_messages,
        name="user_dm_room_messages",
    ),
    path(
        "dm/<int:room_pk>/message/",
        app_views.send_user_dm_message,
        name="send_user_dm_message",
    ),
    path("notifications/", _notifications, name="notifications"),
    path(
        "api/notifications/unread-count/",
        app_views.notification_unread_count,
        name="notification_unread_count",
    ),
    path(
        "api/notifications/mark-read/",
        app_views.notification_mark_read,
        name="notification_mark_read",
    ),
    path("mypage/", app_views.mypage, name="mypage"),
    path("mypage/edit/", app_views.mypage_edit, name="mypage_edit"),
    path("mypage/settings/", app_views.account_settings, name="account_settings"),
    path(
        "mypage/settings/blocked/",
        app_views.blocked_users,
        name="blocked_users",
    ),
    path("account/delete/", app_views.delete_account, name="delete_account"),
    path("user/<int:pk>/follow/", app_views.toggle_follow, name="toggle_follow"),
    path("user/<int:pk>/block/", app_views.toggle_block, name="toggle_block"),
    path(
        "report/<str:target_type>/<int:target_id>/",
        app_views.submit_report,
        name="submit_report",
    ),
    path("board/compose/", app_views.board_compose, name="board_compose"),
    path("board/post/<int:pk>/quote/", app_views.board_quote, name="board_quote"),
    path("board/feed/", app_views.timeline_feed, name="timeline_feed"),
    path("board/latest/", app_views.get_latest_posts, name="get_latest_posts"),
    path("board/post/<int:pk>/like/", app_views.board_timeline_like, name="board_timeline_like"),
    path(
        "board/post/<int:pk>/bookmark/",
        app_views.board_timeline_bookmark,
        name="board_timeline_bookmark",
    ),
    path("board/post/<int:pk>/comment/", app_views.board_timeline_comment, name="board_timeline_comment"),
    path(
        "board/post/<int:pk>/delete/",
        app_views.delete_timeline_post,
        name="delete_timeline_post",
    ),
    path("comment/<int:pk>/delete/", app_views.delete_comment, name="delete_comment"),
    path("login/", _login, name="login"),
    path("logout/", app_views.logout_view, name="logout"),
    path("browse/", app_views.enter_browse_mode, name="enter_browse_mode"),
    path("signup/", _signup, name="signup"),
    path("verify-otp/", _verify_otp, name="verify_otp"),
    path("verify-otp/resend/", app_views.verify_otp_resend, name="verify_otp_resend"),
    path(
        "password-reset/",
        _password_reset,
        name="password_reset_request",
    ),
    path(
        "password-reset/verify/",
        _password_reset_verify,
        name="password_reset_verify",
    ),
    path(
        "password-reset/verify/resend/",
        app_views.password_reset_verify_resend,
        name="password_reset_verify_resend",
    ),
    path(
        "password-reset/set/",
        _password_reset_set,
        name="password_reset_set",
    ),
    path("api/push-token/", app_views.register_push_token, name="register_push_token"),
]

if settings.DEBUG or getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
