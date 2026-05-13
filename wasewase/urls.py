from django.contrib import admin
from django.urls import path

from app import views as app_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", app_views.index, name="home"),
]
