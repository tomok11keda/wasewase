from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from app import views as app_views

_HOME_REDIRECT = RedirectView.as_view(url="/", permanent=True)

urlpatterns = [
    path("manifest.json", app_views.pwa_manifest, name="pwa_manifest"),
    path("service-worker.js", app_views.pwa_service_worker, name="pwa_service_worker"),
    path("ads.txt", app_views.ads_txt, name="ads_txt"),
    path("privacy/", app_views.privacy_policy, name="privacy"),
    path("terms/", app_views.terms_of_service, name="terms"),
    path("admin/", admin.site.urls),
    path("", app_views.index, name="home"),
    path("search/", app_views.search, name="search"),
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
    # フリマ機能（温存モデル・管理画面のみ。公開ルートはホームへリダイレクト）
    path("exhibit/", _HOME_REDIRECT, name="exhibit"),
    path("product/<int:pk>/", _HOME_REDIRECT, name="product_detail"),
    path("product/<int:pk>/delete/", _HOME_REDIRECT, name="delete_product"),
    path("product/<int:pk>/like/", _HOME_REDIRECT, name="toggle_like"),
    path(
        "product/<int:pk>/share-to-timeline/",
        _HOME_REDIRECT,
        name="share_product_to_timeline",
    ),
    path("product/<int:pk>/purchase/", _HOME_REDIRECT, name="purchase_product"),
    path("product/<int:pk>/chat/start/", _HOME_REDIRECT, name="start_product_chat"),
    path("chat/<int:room_pk>/", _HOME_REDIRECT, name="chat_room"),
    path("chat/<int:room_pk>/messages/", _HOME_REDIRECT, name="chat_room_messages"),
    path("chat/<int:room_pk>/message/", _HOME_REDIRECT, name="send_chat_message"),
    path("product/<int:pk>/trade/", _HOME_REDIRECT, name="product_trade"),
    path("product/<int:pk>/trade/complete/", _HOME_REDIRECT, name="complete_trade"),
    path("product/<int:pk>/review/", _HOME_REDIRECT, name="submit_review"),
    path("product/<int:pk>/trade-message/", _HOME_REDIRECT, name="send_trade_message"),
    path("user/<int:pk>/", app_views.user_profile, name="user_profile"),
    path("user/<int:pk>/dm/start/", app_views.start_user_dm, name="start_user_dm"),
    path("dm/", app_views.user_dm_inbox, name="user_dm_inbox"),
    path("dm/<int:room_pk>/", app_views.user_dm_room, name="user_dm_room"),
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
    path("mypage/", app_views.mypage, name="mypage"),
    path("mypage/edit/", app_views.mypage_edit, name="mypage_edit"),
    path("user/<int:pk>/follow/", app_views.toggle_follow, name="toggle_follow"),
    path("user/<int:pk>/block/", app_views.toggle_block, name="toggle_block"),
    path("report/", app_views.submit_report, name="submit_report"),
    path("board/compose/", app_views.board_compose, name="board_compose"),
    path("board/post/<int:pk>/quote/", app_views.board_quote, name="board_quote"),
    path("board/feed/", app_views.timeline_feed, name="timeline_feed"),
    path("board/post/<int:pk>/like/", app_views.board_timeline_like, name="board_timeline_like"),
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
