"""Django Admin for OfficialClass Option B (no auto-merge)."""

from __future__ import annotations

from django.contrib import admin, messages
from django.utils.html import format_html

from .models import (
    OfficialClass,
    OfficialClassImportBatch,
    OfficialClassImportRow,
    OfficialMeeting,
    OfferingOfficialLink,
)
from .official_course_services import (
    enrollment_readiness,
    find_offering_match_candidates,
    set_canonical_offering,
)


class OfficialMeetingInline(admin.TabularInline):
    model = OfficialMeeting
    extra = 0
    fields = ("day_of_week", "period", "period_kind", "raw", "fingerprint")
    readonly_fields = ("fingerprint",)


class OfferingOfficialLinkInline(admin.TabularInline):
    model = OfferingOfficialLink
    extra = 0
    fields = ("offering", "match_method", "confidence", "reviewed_at")
    raw_id_fields = ("offering",)
    readonly_fields = ("reviewed_at",)
    show_change_link = True


@admin.action(description="候補Offeringを代表に設定（先頭候補・統合なし）")
def set_first_candidate_as_canonical(modeladmin, request, queryset):
    ok = 0
    for official in queryset:
        candidates = find_offering_match_candidates(official, limit=1)
        if not candidates:
            messages.warning(
                request, f"#{official.pk} {official.title}: 候補なし（スキップ）"
            )
            continue
        try:
            set_canonical_offering(official, candidates[0], ensure_link=True)
            ok += 1
        except ValueError as exc:
            messages.error(request, f"#{official.pk}: {exc}")
    if ok:
        messages.success(
            request,
            f"{ok} 件の代表CourseOfferingを設定しました（既存Offeringは統合していません）。",
        )


@admin.action(description="代表CourseOfferingをクリア（削除・統合なし）")
def clear_canonical_offering(modeladmin, request, queryset):
    updated = queryset.update(canonical_offering=None)
    messages.success(request, f"{updated} 件の代表設定をクリアしました。")


@admin.register(OfficialClass)
class OfficialClassAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "academic_year",
        "school",
        "title",
        "haibun_class_no",
        "instructor",
        "semester_code",
        "publication_status",
        "is_cancelled",
        "needs_human_review",
        "canonical_offering_id",
        "enrollment_status",
        "updated_at",
    )
    list_filter = (
        "publication_status",
        "academic_year",
        "school",
        "semester_code",
        "is_cancelled",
        "needs_human_review",
    )
    search_fields = (
        "title",
        "instructor",
        "provisional_identity",
        "haibun_class_no",
        "subject_key",
        "section",
    )
    readonly_fields = (
        "provisional_identity",
        "title_normalized",
        "instructor_normalized",
        "created_at",
        "updated_at",
        "enrollment_status_detail",
        "candidate_offerings",
    )
    raw_id_fields = ("canonical_offering",)
    inlines = [OfficialMeetingInline, OfferingOfficialLinkInline]
    actions = [set_first_candidate_as_canonical, clear_canonical_offering]
    fieldsets = (
        (
            "基本",
            {
                "fields": (
                    "academic_year",
                    "school",
                    "section",
                    "title",
                    "title_normalized",
                    "haibun_class_no",
                    "instructor",
                    "instructor_normalized",
                    "semester_code",
                    "semester_label",
                    "credits",
                    "modality_raw",
                    "is_cancelled",
                )
            },
        ),
        (
            "識別子（推測生成禁止）",
            {
                "fields": (
                    "provisional_identity",
                    "subject_key",
                    "syllabus_class_code",
                    "course_code",
                )
            },
        ),
        (
            "公開・レビュー",
            {
                "fields": (
                    "publication_status",
                    "needs_human_review",
                    "parse_flags",
                    "source_url",
                    "source_listing_page",
                    "source_extract_line",
                    "source_raw_line",
                )
            },
        ),
        (
            "代表CourseOffering（人手のみ）",
            {
                "fields": (
                    "canonical_offering",
                    "enrollment_status_detail",
                    "candidate_offerings",
                ),
                "description": (
                    "新規履修の受け皿。未設定のままでは学生履修不可。"
                    "既存Offeringの自動統合・削除は行いません。"
                ),
            },
        ),
        ("メタ", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="履修状態")
    def enrollment_status(self, obj: OfficialClass) -> str:
        return enrollment_readiness(obj)["status"]

    @admin.display(description="履修可否詳細")
    def enrollment_status_detail(self, obj: OfficialClass) -> str:
        info = enrollment_readiness(obj)
        return format_html(
            "<code>{}</code> ready={} linked={}",
            info.get("status"),
            info.get("ready"),
            info.get("active_linked_count"),
        )

    @admin.display(description="候補Offering（参考・自動適用なし）")
    def candidate_offerings(self, obj: OfficialClass) -> str:
        if not obj.pk:
            return "—"
        candidates = find_offering_match_candidates(obj, limit=5)
        if not candidates:
            return "候補なし"
        lines = [
            f"#{c.pk} {c.title} / {c.instructor} ({c.academic_year} {c.semester})"
            for c in candidates
        ]
        return format_html("<br>".join(lines))

    def save_model(self, request, obj, form, change):
        # If admin picked canonical via raw_id, ensure link exists without merge.
        super().save_model(request, obj, form, change)
        if obj.canonical_offering_id:
            try:
                set_canonical_offering(
                    obj,
                    obj.canonical_offering,
                    ensure_link=True,
                    actor=request.user,
                )
            except ValueError as exc:
                messages.error(request, f"代表Offering設定に失敗: {exc}")


@admin.register(OfficialMeeting)
class OfficialMeetingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "official_class",
        "day_of_week",
        "period",
        "period_kind",
        "raw",
        "fingerprint",
    )
    list_filter = ("period_kind", "day_of_week")
    search_fields = ("official_class__title", "raw", "fingerprint")
    raw_id_fields = ("official_class",)


@admin.register(OfferingOfficialLink)
class OfferingOfficialLinkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "offering",
        "official_class",
        "match_method",
        "confidence",
        "reviewed_at",
        "updated_at",
    )
    list_filter = ("match_method",)
    search_fields = (
        "offering__title",
        "offering__instructor",
        "official_class__title",
        "official_class__provisional_identity",
    )
    raw_id_fields = ("offering", "official_class")
    readonly_fields = ("created_at", "updated_at")
    actions = ["action_set_as_canonical"]

    @admin.action(description="リンク先Offeringを代表に設定（統合なし）")
    def action_set_as_canonical(self, request, queryset):
        ok = 0
        for link in queryset.select_related("offering", "official_class"):
            try:
                set_canonical_offering(
                    link.official_class,
                    link.offering,
                    ensure_link=False,
                    actor=request.user,
                )
                ok += 1
            except ValueError as exc:
                messages.error(request, f"link#{link.pk}: {exc}")
        if ok:
            messages.success(request, f"{ok} 件を代表に設定しました。")


class OfficialClassImportRowInline(admin.TabularInline):
    model = OfficialClassImportRow
    extra = 0
    can_delete = False
    fields = (
        "line_no",
        "action",
        "title",
        "provisional_identity",
        "reasons",
        "official_class",
    )
    readonly_fields = fields
    raw_id_fields = ("official_class",)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OfficialClassImportBatch)
class OfficialClassImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "started_at",
        "status",
        "dry_run",
        "publication_status",
        "total_rows",
        "created_count",
        "updated_count",
        "skipped_duplicate_count",
        "rejected_count",
        "started_by",
        "source_path_short",
    )
    list_filter = ("status", "dry_run", "publication_status")
    search_fields = ("source_path", "source_sha256", "error_message")
    readonly_fields = (
        "source_path",
        "source_sha256",
        "dry_run",
        "publication_status",
        "status",
        "total_rows",
        "created_count",
        "updated_count",
        "skipped_duplicate_count",
        "rejected_count",
        "summary_json",
        "error_message",
        "started_by",
        "started_at",
        "finished_at",
    )
    inlines = [OfficialClassImportRowInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="CSV")
    def source_path_short(self, obj: OfficialClassImportBatch) -> str:
        path = obj.source_path or ""
        if len(path) > 60:
            return "…" + path[-57:]
        return path


@admin.register(OfficialClassImportRow)
class OfficialClassImportRowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "batch",
        "line_no",
        "action",
        "title",
        "provisional_identity",
        "reasons",
    )
    list_filter = ("action",)
    search_fields = ("title", "provisional_identity", "reasons")
    raw_id_fields = ("batch", "official_class")
    readonly_fields = (
        "batch",
        "line_no",
        "action",
        "provisional_identity",
        "title",
        "reasons",
        "official_class",
    )

    def has_add_permission(self, request):
        return False
