"""Wire the Growth Dashboard into Django Admin (staff-only)."""

from __future__ import annotations

from django.contrib.admin.sites import AdminSite
from django.template.response import TemplateResponse
from django.urls import path

from .growth_metrics import build_growth_dashboard


def install_growth_dashboard(site: AdminSite) -> None:
    if getattr(site, "_growth_dashboard_installed", False):
        return
    site._growth_dashboard_installed = True

    original_index = site.index
    original_get_urls = site.get_urls

    def index(request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["growth"] = build_growth_dashboard()
        return original_index(request, extra_context=extra_context)

    def growth_view(request):
        context = {
            **site.each_context(request),
            "title": "WaseWase Growth Dashboard",
            "growth": build_growth_dashboard(),
        }
        return TemplateResponse(request, "admin/growth_dashboard_page.html", context)

    def get_urls():
        return [
            path(
                "growth/",
                site.admin_view(growth_view),
                name="growth_dashboard",
            ),
        ] + original_get_urls()

    site.index = index
    site.get_urls = get_urls
    site.index_template = "admin/growth_index.html"
