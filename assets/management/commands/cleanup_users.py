from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta

class Command(BaseCommand):
    help = 'Deletes inactive users who registered more than 48 hours ago.'

    def handle(self, *args, **options):
        threshold = timezone.now() - timedelta(hours=48)
        old_inactive_users = User.objects.filter(is_active=False, date_joined__lt=threshold)
        count = old_inactive_users.count()
        
        # timestamp formázása (hogy szép legyen a logban)
        now_str = timezone.now().strftime('%Y-%m-%d %H:%M:%S')

        if count > 0:
            old_inactive_users.delete()
            self.stdout.write(self.style.SUCCESS(f'[{now_str}] Successfully deleted {count} expired inactive users.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'[{now_str}] No expired inactive users found.'))