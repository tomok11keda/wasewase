from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from app import views as app_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", app_views.index, name="home"),
    path("exhibit/", app_views.exhibit, name="exhibit"),
    path("product/<int:pk>/", app_views.product_detail, name="product_detail"),
    path("product/<int:pk>/like/", app_views.toggle_like, name="toggle_like"),
    path("product/<int:pk>/purchase/", app_views.purchase_product, name="purchase_product"),
    path("product/<int:pk>/trade/", app_views.product_trade, name="product_trade"),
    path("product/<int:pk>/trade/complete/", app_views.complete_trade, name="complete_trade"),
    path("product/<int:pk>/review/", app_views.submit_review, name="submit_review"),
    path(
        "product/<int:pk>/trade-message/",
        app_views.send_trade_message,
        name="send_trade_message",
    ),
    path("user/<int:pk>/", app_views.user_profile, name="user_profile"),
    path("notifications/", app_views.notifications, name="notifications"),
    path("mypage/", app_views.mypage, name="mypage"),
    path("board/compose/", app_views.board_compose, name="board_compose"),
    path("board/post/<int:pk>/tip/", app_views.board_timeline_tip, name="board_timeline_tip"),
    path("board/post/<int:pk>/god/", app_views.board_timeline_god, name="board_timeline_god"),
    path("board/post/<int:pk>/comment/", app_views.board_timeline_comment, name="board_timeline_comment"),
    path("login/", app_views.AppLoginView.as_view(), name="login"),
    path("logout/", app_views.logout_view, name="logout"),
    path("signup/", app_views.signup, name="signup"),
    path("verify-otp/", app_views.verify_otp, name="verify_otp"),
    path("verify-otp/resend/", app_views.verify_otp_resend, name="verify_otp_resend"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
