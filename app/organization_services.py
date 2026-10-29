"""学生団体の所属・権限判定（将来の団体管理者向け API 用）。

Django Admin の運営操作（is_staff / is_superuser）とは分離する。
staff であることは団体管理者権限を与えない。

add / remove / set_role は権限を検査しないプリミティブ。
呼び出し側（Admin は staff 権限、将来 API は can_manage_organization）が認可する。
"""

from __future__ import annotations

from collections.abc import Iterable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import Notification, Organization, OrganizationMember

_MANAGING_ROLES = (
    OrganizationMember.Role.OWNER,
    OrganizationMember.Role.ADMIN,
)

_LAST_OWNER_DELETE_MESSAGE = (
    "最後の代表管理者は削除できません。先に別の代表管理者を追加してください。"
)
_LAST_OWNER_DEMOTE_MESSAGE = (
    "最後の代表管理者は降格できません。先に別の代表管理者を追加してください。"
)
_LAST_OWNER_ACCOUNT_DELETION_GUIDE = (
    "プロフィールだけを削除する場合は、先に団体のメンバー管理から"
    "別の代表管理者へ権限を移してください。"
)
FULL_WITHDRAWAL_ORG_UNPUBLISH_WARNING = (
    "代表管理者のまま退会すると、他に代表管理者がいない団体は非公開になります。"
    "団体そのものと残っているメンバーは削除されません。"
)


class LastOrganizationOwnerError(ValueError):
    """最後の代表管理者を削除・降格しようとした。"""

    code = "last_organization_owner"

    def __init__(self, message: str = "", *, organizations=None):
        self.organizations = list(organizations or [])
        super().__init__(message or _LAST_OWNER_DELETE_MESSAGE)


class OrganizationMembershipError(ValueError):
    """所属の追加・変更ができない。"""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def is_site_operator(user: AbstractBaseUser | None) -> bool:
    """Django Admin / 運営ツール用。団体管理者 API には使わない。"""
    if user is None or not getattr(user, "pk", None):
        return False
    return bool(
        getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
    )


def _actor_can_hold_org_role(user: AbstractBaseUser | None) -> bool:
    if user is None or not getattr(user, "pk", None):
        return False
    if getattr(user, "is_authenticated", True) is False:
        return False
    if not getattr(user, "is_active", False):
        return False
    return True


def _is_active_site_operator(user: AbstractBaseUser | None) -> bool:
    return _actor_can_hold_org_role(user) and is_site_operator(user)


def is_organization_owner(
    user: AbstractBaseUser | None,
    organization: Organization | None,
) -> bool:
    """所属 role=owner かつ利用可能な個人ユーザーか。団体の status は見ない。"""
    if not _actor_can_hold_org_role(user) or organization is None:
        return False
    if not getattr(organization, "pk", None):
        return False
    return OrganizationMember.objects.filter(
        organization_id=organization.pk,
        user_id=user.pk,
        role=OrganizationMember.Role.OWNER,
    ).exists()


def is_organization_admin(
    user: AbstractBaseUser | None,
    organization: Organization | None,
) -> bool:
    """所属 role が owner または admin か。staff 権限は見ない。status は見ない。"""
    if not _actor_can_hold_org_role(user) or organization is None:
        return False
    if not getattr(organization, "pk", None):
        return False
    return OrganizationMember.objects.filter(
        organization_id=organization.pk,
        user_id=user.pk,
        role__in=_MANAGING_ROLES,
    ).exists()


def can_manage_organization(
    user: AbstractBaseUser | None,
    organization: Organization | None,
) -> bool:
    """将来の団体管理者向け通常操作。suspended は不可。staff では代行しない。"""
    if not is_organization_admin(user, organization):
        return False
    if getattr(organization, "status", None) == Organization.Status.SUSPENDED:
        return False
    return True


def get_organization_membership_role(
    user: AbstractBaseUser | None,
    organization: Organization | None,
) -> str | None:
    """表示用の所属 role。非アクティブ・未認証は None。"""
    if not _actor_can_hold_org_role(user) or organization is None:
        return None
    if not getattr(organization, "pk", None):
        return None
    return (
        OrganizationMember.objects.filter(
            organization_id=organization.pk,
            user_id=user.pk,
        )
        .values_list("role", flat=True)
        .first()
    )


def can_view_organization_profile(
    viewer: AbstractBaseUser | None,
    organization: Organization | None,
) -> bool:
    """プロフィール閲覧可否（将来の公開 API 用）。検索掲載とは独立。"""
    if organization is None or not getattr(organization, "pk", None):
        return False
    status = organization.status
    if status == Organization.Status.ACTIVE:
        return True
    if status == Organization.Status.DRAFT:
        return _is_active_site_operator(viewer) or is_organization_admin(
            viewer, organization
        )
    if status == Organization.Status.SUSPENDED:
        return _is_active_site_operator(viewer) or is_organization_admin(
            viewer, organization
        )
    return False


def can_list_organization(
    organization: Organization | None,
) -> bool:
    """検索・一覧への掲載可否。閲覧可否とは独立。viewer は見ない。"""
    if organization is None or not getattr(organization, "pk", None):
        return False
    return (
        organization.status == Organization.Status.ACTIVE
        and bool(organization.is_listed)
    )


def can_select_managed_organization(
    organization: Organization | None,
) -> bool:
    """学生アプリの団体選択。公開掲載中に加え、作成途中の draft は残す。"""
    if organization is None or not getattr(organization, "pk", None):
        return False
    if organization.status == Organization.Status.DRAFT:
        return True
    return can_list_organization(organization)


def search_organizations(query: str) -> QuerySet[Organization]:
    """掲載中の学生団体を名前・slug で部分一致検索。

    並び: 完全一致 > 前方一致 > 部分一致 > 名前 > pk。
    is_verified は必須にしない。can_list_organization と同じ掲載条件。
    """
    q = (query or "").strip()
    if not q:
        return Organization.objects.none()
    return (
        Organization.objects.filter(
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        .filter(Q(name__icontains=q) | Q(slug__icontains=q))
        .annotate(
            search_match_rank=Case(
                When(name__iexact=q, then=Value(0)),
                When(slug__iexact=q, then=Value(0)),
                When(name__istartswith=q, then=Value(1)),
                When(slug__istartswith=q, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by("search_match_rank", "name", "pk")
    )


def organization_has_owner(organization: Organization | None) -> bool:
    if organization is None or not getattr(organization, "pk", None):
        return False
    return OrganizationMember.objects.filter(
        organization_id=organization.pk,
        role=OrganizationMember.Role.OWNER,
    ).exists()


def organizations_left_without_owner_if_users_deleted(
    user_ids: Iterable[int],
) -> list[Organization]:
    """Deleting these users would leave these organizations with no owner."""
    ids = {int(pk) for pk in user_ids if pk}
    if not ids:
        return []
    owned_org_ids = list(
        OrganizationMember.objects.filter(
            user_id__in=ids,
            role=OrganizationMember.Role.OWNER,
        )
        .values_list("organization_id", flat=True)
        .distinct()
    )
    if not owned_org_ids:
        return []
    still_owned = set(
        OrganizationMember.objects.filter(
            organization_id__in=owned_org_ids,
            role=OrganizationMember.Role.OWNER,
        )
        .exclude(user_id__in=ids)
        .values_list("organization_id", flat=True)
    )
    orphan_ids = [org_id for org_id in owned_org_ids if org_id not in still_owned]
    if not orphan_ids:
        return []
    return list(Organization.objects.filter(pk__in=orphan_ids).order_by("name", "pk"))


def account_deletion_last_owner_message(organizations: list[Organization]) -> str:
    names = [
        ((organization.name or "").strip() or organization.slug or "団体")
        for organization in organizations
    ]
    if not names:
        return (
            "最後の代表管理者のため、このアカウントは削除できません。"
            + _LAST_OWNER_ACCOUNT_DELETION_GUIDE
        )
    if len(names) == 1:
        labeled = f"「{names[0]}」"
    else:
        labeled = "、".join(f"「{name}」" for name in names)
    return (
        f"{labeled}の最後の代表管理者のため、このアカウントは削除できません。"
        + _LAST_OWNER_ACCOUNT_DELETION_GUIDE
    )


def serialize_last_owner_organizations(
    organizations: Iterable[Organization],
) -> list[dict[str, object]]:
    payload = []
    for organization in organizations:
        payload.append(
            {
                "id": organization.pk,
                "name": organization.name,
                "slug": organization.slug,
            }
        )
    return payload


def assert_users_can_be_deleted_without_orphaning_organizations(
    user_ids: Iterable[int],
) -> None:
    ids = {int(pk) for pk in user_ids if pk}
    if not ids:
        return
    with transaction.atomic():
        owned_org_ids = list(
            OrganizationMember.objects.filter(
                user_id__in=ids,
                role=OrganizationMember.Role.OWNER,
            )
            .values_list("organization_id", flat=True)
            .distinct()
        )
        for org_id in owned_org_ids:
            _lock_organization_memberships(org_id)
        organizations = organizations_left_without_owner_if_users_deleted(ids)
        if organizations:
            raise LastOrganizationOwnerError(
                account_deletion_last_owner_message(organizations),
                organizations=organizations,
            )


def count_organization_owners(
    organization: Organization,
    *,
    exclude_member_ids: list[int] | None = None,
    exclude_member_id: int | None = None,
) -> int:
    queryset = OrganizationMember.objects.filter(
        organization_id=organization.pk,
        role=OrganizationMember.Role.OWNER,
    )
    excluded = list(exclude_member_ids or [])
    if exclude_member_id:
        excluded.append(exclude_member_id)
    if excluded:
        queryset = queryset.exclude(pk__in=excluded)
    return queryset.count()


def _lock_organization_memberships(organization_id: int) -> list[OrganizationMember]:
    return list(
        OrganizationMember.objects.select_for_update().filter(
            organization_id=organization_id
        )
    )


def apply_organization_visibility_guard(organization: Organization) -> bool:
    """owner 不在のまま active / listed にしない。suspended は維持したまま非掲載にする。"""
    if organization.pk is None:
        return False
    if organization_has_owner(organization):
        return False
    update_fields: list[str] = []
    if organization.status == Organization.Status.ACTIVE:
        organization.status = Organization.Status.DRAFT
        update_fields.append("status")
    if organization.is_listed:
        organization.is_listed = False
        update_fields.append("is_listed")
    if not update_fields:
        return False
    update_fields.append("updated_at")
    organization.save(update_fields=update_fields)
    return True


def activate_and_list_granted_organization(organization: Organization) -> bool:
    """運営付与済み団体を公開フィード掲載可能にする。停止中は触らない。"""
    if organization.pk is None:
        return False
    if organization.status == Organization.Status.SUSPENDED:
        return False
    if not organization_has_owner(organization):
        return False
    update_fields: list[str] = []
    if organization.status != Organization.Status.ACTIVE:
        organization.status = Organization.Status.ACTIVE
        update_fields.append("status")
    if not organization.is_listed:
        organization.is_listed = True
        update_fields.append("is_listed")
    if not update_fields:
        return False
    update_fields.append("updated_at")
    organization.save(update_fields=update_fields)
    return True


def complete_operator_organization_grant(
    organization: Organization,
    *,
    completing_grant: bool,
) -> bool:
    """運営の団体アカウント付与が完了したときだけ active / listed にする。

    後からの意図的な非掲載・停止は維持する。owner がいない付与は公開しない。
    """
    if not completing_grant:
        return False
    return activate_and_list_granted_organization(organization)


def provision_operator_granted_organization(
    *,
    owner: AbstractBaseUser,
    name: str,
    slug: str,
    **kwargs,
) -> Organization:
    """運営が団体アカウントを付与する。owner・active・listed を同一トランザクションで揃える。"""
    if not getattr(owner, "pk", None):
        raise OrganizationMembershipError("invalid_user")
    kwargs.pop("status", None)
    kwargs.pop("is_listed", None)
    with transaction.atomic():
        organization = Organization.objects.create(
            name=name,
            slug=slug,
            status=Organization.Status.DRAFT,
            is_listed=False,
            **kwargs,
        )
        add_organization_member(
            organization, owner, role=OrganizationMember.Role.OWNER
        )
        activate_and_list_granted_organization(organization)
        organization.refresh_from_db()
        return organization


def assert_can_remove_organization_member(member: OrganizationMember) -> None:
    if member.role != OrganizationMember.Role.OWNER:
        return
    if not member.organization_id:
        return
    with transaction.atomic():
        _lock_organization_memberships(member.organization_id)
        remaining = count_organization_owners(
            member.organization,
            exclude_member_id=member.pk,
        )
        if remaining == 0:
            raise LastOrganizationOwnerError(_LAST_OWNER_DELETE_MESSAGE)


def assert_can_change_organization_member_role(
    member: OrganizationMember,
    new_role: str,
) -> None:
    if new_role == OrganizationMember.Role.OWNER:
        return
    if not member.pk or not member.organization_id:
        return
    with transaction.atomic():
        _lock_organization_memberships(member.organization_id)
        previous_role = (
            OrganizationMember.objects.filter(pk=member.pk)
            .values_list("role", flat=True)
            .first()
        )
        if previous_role != OrganizationMember.Role.OWNER:
            return
        remaining = count_organization_owners(
            member.organization,
            exclude_member_id=member.pk,
        )
        if remaining == 0:
            raise LastOrganizationOwnerError(_LAST_OWNER_DEMOTE_MESSAGE)


def assert_queryset_delete_keeps_owner(queryset: QuerySet) -> None:
    """同一団体の owner をまとめて消して 0 人にしない。"""
    rows = list(queryset.values_list("pk", "organization_id", "role"))
    if not rows:
        return
    by_org: dict[int, list[tuple[int, str]]] = {}
    for pk, org_id, role in rows:
        by_org.setdefault(org_id, []).append((pk, role))
    with transaction.atomic():
        for org_id, members in by_org.items():
            _lock_organization_memberships(org_id)
            deleting_pks = [pk for pk, _role in members]
            deleting_owner = any(
                role == OrganizationMember.Role.OWNER for _pk, role in members
            )
            if not deleting_owner:
                continue
            remaining = count_organization_owners(
                Organization(pk=org_id),
                exclude_member_ids=deleting_pks,
            )
            if remaining == 0:
                raise LastOrganizationOwnerError(_LAST_OWNER_DELETE_MESSAGE)


def assert_queryset_role_update_keeps_owner(
    queryset: QuerySet,
    update_kwargs: dict,
) -> None:
    new_role = update_kwargs.get("role")
    if new_role is None or new_role == OrganizationMember.Role.OWNER:
        return
    rows = list(queryset.values_list("pk", "organization_id", "role"))
    if not rows:
        return
    by_org: dict[int, list[int]] = {}
    for pk, org_id, role in rows:
        if role == OrganizationMember.Role.OWNER:
            by_org.setdefault(org_id, []).append(pk)
    if not by_org:
        return
    with transaction.atomic():
        for org_id, owner_pks in by_org.items():
            _lock_organization_memberships(org_id)
            remaining = count_organization_owners(
                Organization(pk=org_id),
                exclude_member_ids=owner_pks,
            )
            if remaining == 0:
                raise LastOrganizationOwnerError(_LAST_OWNER_DEMOTE_MESSAGE)


def add_organization_member(
    organization: Organization,
    user: AbstractBaseUser,
    *,
    role: str = OrganizationMember.Role.ADMIN,
) -> OrganizationMember:
    if not getattr(user, "pk", None):
        raise OrganizationMembershipError("invalid_user")
    if role not in OrganizationMember.Role.values:
        raise OrganizationMembershipError("invalid_role")
    if OrganizationMember.objects.filter(
        organization=organization, user=user
    ).exists():
        raise OrganizationMembershipError("already_member")
    return OrganizationMember.objects.create(
        organization=organization,
        user=user,
        role=role,
    )


def remove_organization_member(member: OrganizationMember) -> None:
    assert_can_remove_organization_member(member)
    super(OrganizationMember, member).delete()


def set_organization_member_role(
    member: OrganizationMember,
    role: str,
) -> OrganizationMember:
    if role not in OrganizationMember.Role.values:
        raise OrganizationMembershipError("invalid_role")
    assert_can_change_organization_member_role(member, role)
    if member.role == role:
        return member
    member.role = role
    member.save(update_fields=["role"])
    return member


ORG_MANAGE_GRANT_QUERY = "org_grant=1"
_GRANT_PREVIOUS_ROLE_ATTR = "_grant_previous_role"
_GRANT_PREVIOUS_USER_ID_ATTR = "_grant_previous_user_id"


def organization_manage_grant_link(organization: Organization) -> str:
    slug = (getattr(organization, "slug", None) or "").strip()
    return f"/orgs/{slug}?{ORG_MANAGE_GRANT_QUERY}"


def organization_manage_grant_message(organization: Organization) -> str:
    name = (getattr(organization, "name", None) or "").strip() or "団体"
    return f"{name}の管理権限が付与されました"


def notify_organization_manage_granted(
    *,
    organization: Organization,
    user: AbstractBaseUser,
    new_role: str,
    previous_role: str | None = None,
    previous_user_id: int | None = None,
) -> Notification | None:
    """Create one inbox row when owner/admin is newly granted. No backfill."""
    if not getattr(user, "pk", None):
        return None
    if new_role not in _MANAGING_ROLES:
        return None
    same_user = previous_user_id in (None, user.pk)
    if same_user and previous_role in _MANAGING_ROLES:
        return None
    from .notification_services import (
        PUSH_KIND_ORG_MANAGE_GRANTED,
        create_notification,
    )

    return create_notification(
        recipient=user,
        message=organization_manage_grant_message(organization),
        link=organization_manage_grant_link(organization),
        push_kind=PUSH_KIND_ORG_MANAGE_GRANTED,
    )


def _bound_member_forms(formset):
    for form in formset.forms:
        cleaned = getattr(form, "cleaned_data", None)
        if not cleaned:
            continue
        if cleaned.get("DELETE"):
            if form.instance.pk:
                yield form
            continue
        if not cleaned.get("user") and not form.instance.pk:
            continue
        yield form


def preview_owner_count_after_formset(organization: Organization, formset) -> int:
    owner_keys: set[str] = {
        f"id:{pk}"
        for pk in OrganizationMember.objects.filter(
            organization=organization,
            role=OrganizationMember.Role.OWNER,
        ).values_list("pk", flat=True)
    }
    for index, form in enumerate(_bound_member_forms(formset)):
        cleaned = form.cleaned_data
        if cleaned.get("DELETE"):
            if form.instance.pk:
                owner_keys.discard(f"id:{form.instance.pk}")
            continue
        key = f"id:{form.instance.pk}" if form.instance.pk else f"new:{index}"
        if cleaned.get("role") == OrganizationMember.Role.OWNER:
            owner_keys.add(key)
        else:
            owner_keys.discard(key)
    return len(owner_keys)


def assert_formset_preserves_last_owner(organization: Organization, formset) -> None:
    if not organization.pk:
        return
    had_owner = organization_has_owner(organization)
    if not had_owner:
        return
    if preview_owner_count_after_formset(organization, formset) < 1:
        raise LastOrganizationOwnerError(_LAST_OWNER_DELETE_MESSAGE)


def save_organization_member_formset(formset, organization: Organization) -> None:
    """インライン保存。owner 追加・昇格を先に行い、削除・降格は後にする。"""
    with transaction.atomic():
        if organization.pk:
            _lock_organization_memberships(organization.pk)
        had_owner = organization_has_owner(organization)
        assert_formset_preserves_last_owner(organization, formset)

        owner_forms = []
        other_forms = []
        delete_forms = []
        for form in _bound_member_forms(formset):
            cleaned = form.cleaned_data
            if cleaned.get("DELETE"):
                delete_forms.append(form)
                continue
            if cleaned.get("role") == OrganizationMember.Role.OWNER:
                owner_forms.append(form)
            else:
                other_forms.append(form)

        formset.new_objects = []
        formset.changed_objects = []
        formset.deleted_objects = []
        for form in owner_forms + other_forms:
            existed = bool(form.instance.pk)
            obj = form.save(commit=False)
            obj.organization = organization
            obj.save()
            if existed:
                formset.changed_objects.append((obj, form.changed_data))
            else:
                formset.new_objects.append(obj)
        for form in delete_forms:
            if form.instance.pk:
                formset.deleted_objects.append(form.instance)
                form.instance.delete()

        if had_owner and not organization_has_owner(organization):
            raise LastOrganizationOwnerError(_LAST_OWNER_DELETE_MESSAGE)


def _origin_is_user(origin) -> bool:
    if origin is None:
        return False
    user_model = get_user_model()
    if isinstance(origin, QuerySet):
        return origin.model is user_model
    return isinstance(origin, user_model)


def _origin_is_organization(origin) -> bool:
    if origin is None:
        return False
    if isinstance(origin, QuerySet):
        return origin.model is Organization
    return isinstance(origin, Organization)


@receiver(
    pre_save,
    sender=OrganizationMember,
    dispatch_uid="wase_organization_member_pre_save_grant",
)
def organization_member_pre_save_grant(sender, instance, **kwargs):
    """Remember prior role/user so duplicate admin saves do not re-notify."""
    if not instance.pk:
        setattr(instance, _GRANT_PREVIOUS_ROLE_ATTR, None)
        setattr(instance, _GRANT_PREVIOUS_USER_ID_ATTR, None)
        return
    previous = (
        OrganizationMember.objects.filter(pk=instance.pk)
        .values("role", "user_id")
        .first()
    )
    setattr(
        instance,
        _GRANT_PREVIOUS_ROLE_ATTR,
        None if previous is None else previous["role"],
    )
    setattr(
        instance,
        _GRANT_PREVIOUS_USER_ID_ATTR,
        None if previous is None else previous["user_id"],
    )


@receiver(
    post_save,
    sender=OrganizationMember,
    dispatch_uid="wase_organization_member_post_save_grant",
)
def organization_member_post_save_grant(
    sender, instance, created, raw=False, **kwargs
):
    if raw:
        return
    user = getattr(instance, "user", None)
    organization = getattr(instance, "organization", None)
    if user is None or organization is None:
        return
    previous_role = None if created else getattr(
        instance, _GRANT_PREVIOUS_ROLE_ATTR, None
    )
    previous_user_id = None if created else getattr(
        instance, _GRANT_PREVIOUS_USER_ID_ATTR, None
    )
    notify_organization_manage_granted(
        organization=organization,
        user=user,
        new_role=instance.role,
        previous_role=previous_role,
        previous_user_id=previous_user_id,
    )


@receiver(
    pre_delete,
    sender=OrganizationMember,
    dispatch_uid="wase_organization_member_pre_delete",
)
def organization_member_pre_delete(sender, instance, origin=None, **kwargs):
    """QuerySet.delete / インスタンス削除を捕捉。User / Organization CASCADE は許可。"""
    if _origin_is_organization(origin) or _origin_is_user(origin):
        return
    assert_can_remove_organization_member(instance)


@receiver(
    post_delete,
    sender=OrganizationMember,
    dispatch_uid="wase_organization_member_post_delete",
)
def organization_member_post_delete(sender, instance, origin=None, **kwargs):
    """退会 CASCADE 後に owner 不在の公開状態を落とす。団体本体は消さない。"""
    if not _origin_is_user(origin):
        return
    org = Organization.objects.filter(pk=instance.organization_id).first()
    if org is not None:
        apply_organization_visibility_guard(org)
