# Onboarding step + completion timestamp. Existing rows stay incomplete
# (completed_at=NULL) so pre-beta users still see Follow onboarding.
# Do not backfill completed_at=now().

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0054_userprofile_terms_acceptance_history"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="onboarding_completed_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Welcome CTA でセット。NULL の一般ユーザーはオンボーディング対象。",
                null=True,
                verbose_name="オンボーディング完了日時",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="onboarding_exempt",
            field=models.BooleanField(
                default=False,
                help_text="staff/superuser 以外のテストアカウントをゲートから除外する。",
                verbose_name="オンボーディング対象外",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="onboarding_step",
            field=models.CharField(
                choices=[
                    ("profile", "プロフィール"),
                    ("follow", "フォロー"),
                    ("welcome", "完了画面"),
                ],
                default="profile",
                help_text="未完了ユーザーが再開するステップ。完了後は参照しない。",
                max_length=16,
                verbose_name="オンボーディングの位置",
            ),
        ),
    ]
