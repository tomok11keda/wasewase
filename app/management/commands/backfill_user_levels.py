from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from app.level_services import recalculate_user_level


class Command(BaseCommand):
    help = "全ユーザーのレベルスコアを再計算して UserProfile に反映します。"

    def handle(self, *args, **options):
        User = get_user_model()
        updated = 0
        for user in User.objects.iterator():
            recalculate_user_level(user)
            updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated level stats for {updated} user(s)."))
