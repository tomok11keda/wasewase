from django.db import migrations, models
import django.db.models.deletion


def grant_manager_memberships(apps, schema_editor):
    OrganizationRecruitingChat = apps.get_model("app", "OrganizationRecruitingChat")
    OrganizationMember = apps.get_model("app", "OrganizationMember")
    ChatRoomMembership = apps.get_model("app", "ChatRoomMembership")
    manager_roles = ("owner", "admin")
    for chat in OrganizationRecruitingChat.objects.all().only("id", "room_id", "organization_id"):
        manager_ids = OrganizationMember.objects.filter(
            organization_id=chat.organization_id,
            role__in=manager_roles,
        ).values_list("user_id", flat=True)
        for user_id in manager_ids:
            ChatRoomMembership.objects.get_or_create(
                room_id=chat.room_id,
                user_id=user_id,
                defaults={"role": "member"},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0076_account_identity"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="organizationrecruitingchat",
            name="uniq_org_active_recruiting_chat",
        ),
        migrations.RemoveConstraint(
            model_name="organizationrecruitingchat",
            name="app_recruiting_chat_join_mode_valid",
        ),
        migrations.AddField(
            model_name="organizationrecruitingchat",
            name="visibility",
            field=models.CharField(
                choices=[("public", "公開"), ("private", "非公開")],
                db_index=True,
                default="public",
                max_length=16,
                verbose_name="公開範囲",
            ),
        ),
        migrations.AddField(
            model_name="organizationrecruitingchat",
            name="posting_mode",
            field=models.CharField(
                choices=[
                    ("all", "全参加者が送信可"),
                    ("admins", "管理者のみ送信可"),
                ],
                db_index=True,
                default="all",
                max_length=16,
                verbose_name="投稿権限",
            ),
        ),
        migrations.AddField(
            model_name="organizationrecruitingchat",
            name="pinned_message",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pinned_organization_chats",
                to="app.chatmessage",
                verbose_name="固定メッセージ",
            ),
        ),
        migrations.AlterField(
            model_name="organizationrecruitingchat",
            name="join_mode",
            field=models.CharField(
                choices=[
                    ("open", "自由参加"),
                    ("approval", "承認制"),
                    ("invite", "招待制"),
                ],
                db_index=True,
                default="open",
                max_length=16,
                verbose_name="参加方式",
            ),
        ),
        migrations.AlterField(
            model_name="organizationrecruitingchat",
            name="is_active",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="False はアーカイブ。メッセージと参加者は残す。",
                verbose_name="有効な団体チャット",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationrecruitingchat",
            constraint=models.CheckConstraint(
                condition=models.Q(join_mode__in=["open", "approval", "invite"]),
                name="app_recruiting_chat_join_mode_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationrecruitingchat",
            constraint=models.CheckConstraint(
                condition=models.Q(visibility__in=["public", "private"]),
                name="app_recruiting_chat_visibility_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationrecruitingchat",
            constraint=models.CheckConstraint(
                condition=models.Q(posting_mode__in=["all", "admins"]),
                name="app_recruiting_chat_posting_mode_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationrecruitingchat",
            index=models.Index(
                fields=["organization", "visibility", "is_active"],
                name="app_organiz_organiz_vis_idx",
            ),
        ),
        migrations.CreateModel(
            name="OrganizationChatShare",
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
                    "share_type",
                    models.CharField(
                        choices=[
                            ("org_event", "イベント"),
                            ("org_event_lottery", "抽選結果"),
                        ],
                        db_index=True,
                        max_length=32,
                        verbose_name="共有種別",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_shares",
                        to="app.organizationevent",
                        verbose_name="イベント",
                    ),
                ),
                (
                    "message",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_chat_share",
                        to="app.chatmessage",
                        verbose_name="共有メッセージ",
                    ),
                ),
                (
                    "recruiting_chat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shares",
                        to="app.organizationrecruitingchat",
                        verbose_name="団体チャット",
                    ),
                ),
            ],
            options={
                "verbose_name": "団体チャット共有",
                "verbose_name_plural": "団体チャット共有",
            },
        ),
        migrations.AddConstraint(
            model_name="organizationchatshare",
            constraint=models.UniqueConstraint(
                fields=["event", "recruiting_chat", "share_type"],
                name="uniq_org_chat_share_event_chat_type",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationchatshare",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    share_type__in=["org_event", "org_event_lottery"]
                ),
                name="app_org_chat_share_type_valid",
            ),
        ),
        migrations.RunPython(grant_manager_memberships, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="organizationrecruitingchat",
            options={
                "ordering": ["-updated_at"],
                "verbose_name": "団体チャット",
                "verbose_name_plural": "団体チャット",
            },
        ),
    ]
