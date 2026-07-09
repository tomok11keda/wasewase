from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from app import views as app_views
from app import marketplace_views as flea_views

_HOME_REDIRECT = RedirectView.as_view(url="/", permanent=True)

urlpatterns = [
    path("manifest.json", app_views.pwa_manifest, name="pwa_manifest"),
    path("service-worker.js", app_views.pwa_service_worker, name="pwa_service_worker"),
    path("ads.txt", app_views.ads_txt, name="ads_txt"),
    path("privacy/", app_views.privacy_policy, name="privacy"),
    path("terms/", app_views.terms_of_service, name="terms"),
    path("support/", app_views.support_page, name="support"),
    path("admin/", admin.site.urls),
    path("", app_views.index, name="home"),
    path("search/", app_views.search, name="search"),
    path("flea/", flea_views.flea_index, name="flea_index"),
    path("more/", app_views.more_index, name="more_index"),
    path("communities/", app_views.communities_index, name="communities_index"),
    path("communities/thread/", app_views.create_community_thread, name="create_community_thread"),
    path(
        "communities/<slug:slug>/",
        app_views.community_detail,
        name="community_detail",
    ),
    path(
        "communities/<slug:slug>/threads/<int:thread_pk>/",
        app_views.community_thread_detail,
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
    path("exhibit/", flea_views.exhibit, name="exhibit"),
    path("product/<int:pk>/", flea_views.product_detail, name="product_detail"),
    path("product/<int:pk>/delete/", flea_views.delete_product, name="delete_product"),
    path("product/<int:pk>/like/", flea_views.toggle_like, name="toggle_like"),
    path(
        "product/<int:pk>/share-to-timeline/",
        flea_views.share_product_to_timeline,
        name="share_product_to_timeline",
    ),
    path("product/<int:pk>/purchase/", flea_views.purchase_product, name="purchase_product"),
    path("product/<int:pk>/chat/start/", flea_views.start_product_chat, name="start_product_chat"),
    path("chat/<int:room_pk>/", flea_views.chat_room, name="chat_room"),
    path("chat/<int:room_pk>/messages/", flea_views.chat_room_messages, name="chat_room_messages"),
    path("chat/<int:room_pk>/message/", flea_views.send_chat_message, name="send_chat_message"),
    path("product/<int:pk>/trade/", flea_views.product_trade, name="product_trade"),
    path("product/<int:pk>/trade/complete/", flea_views.complete_trade, name="complete_trade"),
    path("product/<int:pk>/review/", flea_views.submit_review, name="submit_review"),
    path("product/<int:pk>/trade-message/", flea_views.send_trade_message, name="send_trade_message"),
    path("user/<int:pk>/", app_views.user_profile, name="user_profile"),
    path("user/<int:pk>/dm/start/", app_views.start_user_dm, name="start_user_dm"),
    path("dm/", app_views.user_dm_inbox, name="user_dm_inbox"),
    path("api/dm/unread-summary/", app_views.dm_unread_summary, name="dm_unread_summary"),
    path("dm/<int:room_pk>/", app_views.user_dm_room, name="user_dm_room"),
    path(
        "dm/groups/create/",
        app_views.dm_group_create,
        name="dm_group_create",
    ),
    path(
        "dm/groups/<int:room_pk>/",
        app_views.dm_group_room,
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
    path("notifications/", app_views.notifications, name="notifications"),
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
    path("account/delete/", app_views.delete_account, name="delete_account"),
    path("user/<int:pk>/follow/", app_views.toggle_follow, name="toggle_follow"),
    path("user/<int:pk>/block/", app_views.toggle_block, name="toggle_block"),
    path("report/", app_views.submit_report, name="submit_report"),
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
    path("login/", app_views.AppLoginView.as_view(), name="login"),
    path("logout/", app_views.logout_view, name="logout"),
    path("signup/", app_views.signup, name="signup"),
    path("verify-otp/", app_views.verify_otp, name="verify_otp"),
    path("verify-otp/resend/", app_views.verify_otp_resend, name="verify_otp_resend"),
    path("api/push-token/", app_views.register_push_token, name="register_push_token"),
]

if settings.DEBUG or getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
