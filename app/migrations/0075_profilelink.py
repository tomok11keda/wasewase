from django.conf import settings
from django.db import migrations, models

PROFILE_LINK_MAX = 5
LEGACY_INSTAGRAM_TITLE = "Instagram"
LEGACY_WEBSITE_TITLE = "公式Webサイト"


def _legacy_url_key(url):
    return str(url or "").strip().rstrip("/").lower()


def copy_organization_legacy_urls(apps, schema_editor):
    """Copy Organization Instagram/website columns into ProfileLink rows.

    Uses historical apps.get_model only. Do not import live service modules
    or the current ProfileLink model — later service edits must not break an
    empty-database migrate.
    """
    Organization = apps.get_model("app", "Organization")
    ProfileLink = apps.get_model("app", "ProfileLink")

    urls_by_org = {}
    counts = {}
    for org_id, url in ProfileLink.objects.exclude(organization_id=None).values_list(
        "organization_id", "url"
    ):
        urls_by_org.setdefault(org_id, set()).add(_legacy_url_key(url))
        counts[org_id] = counts.get(org_id, 0) + 1

    to_create = []
    orgs = Organization.objects.exclude(instagram_url="", website_url="").only(
        "id", "instagram_url", "website_url"
    )
    for org in orgs.iterator():
        seen = urls_by_org.setdefault(org.pk, set())
        position = counts.get(org.pk, 0)
        for title, raw_url in (
            (LEGACY_INSTAGRAM_TITLE, org.instagram_url or ""),
            (LEGACY_WEBSITE_TITLE, org.website_url or ""),
        ):
            url = str(raw_url).strip()
            if not url:
                continue
            key = _legacy_url_key(url)
            if not key or key in seen:
                continue
            if position >= PROFILE_LINK_MAX:
                break
            to_create.append(
                ProfileLink(
                    organization_id=org.pk,
                    title=title,
                    url=url,
                    position=position,
                )
            )
            seen.add(key)
            position += 1
            counts[org.pk] = position
    if to_create:
        ProfileLink.objects.bulk_create(to_create)


class Migration(migrations.Migration):
    """Create ProfileLink and copy existing organization Instagram/website URLs.

    Production warning:
        Reversing this migration drops the ProfileLink table and deletes every
        stored profile link. Organization.instagram_url / website_url columns
        are not removed, but extra links (3rd–5th) cannot be recovered from
        those columns. Do not reverse this migration in production.

        The RunPython reverse is a no-op because CreateModel reverse already
        drops the table. That table drop is the destructive step.
    """

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0074_timelinepost_organization_visibility"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProfileLink",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        blank=True, default="", max_length=40, verbose_name="表示名"
                    ),
                ),
                ("url", models.URLField(max_length=200, verbose_name="URL")),
                (
                    "position",
                    models.PositiveSmallIntegerField(default=0, verbose_name="表示順"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.CASCADE,
                        related_name="profile_links",
                        to="app.organization",
                        verbose_name="団体",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.CASCADE,
                        related_name="profile_links",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="ユーザー",
                    ),
                ),
            ],
            options={
                "verbose_name": "プロフィールリンク",
                "verbose_name_plural": "プロフィールリンク",
                "ordering": ["position", "pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="profilelink",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(user_id__isnull=False, organization_id__isnull=True)
                    | models.Q(user_id__isnull=True, organization_id__isnull=False)
                ),
                name="app_profilelink_owner_xor",
            ),
        ),
        migrations.AddConstraint(
            model_name="profilelink",
            constraint=models.UniqueConstraint(
                condition=models.Q(user_id__isnull=False),
                fields=("user", "position"),
                name="app_profilelink_user_pos_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="profilelink",
            constraint=models.UniqueConstraint(
                condition=models.Q(organization_id__isnull=False),
                fields=("organization", "position"),
                name="app_profilelink_org_pos_uniq",
            ),
        ),
        migrations.RunPython(
            copy_organization_legacy_urls,
            migrations.RunPython.noop,
        ),
    ]
