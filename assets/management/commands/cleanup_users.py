from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta

class Command(BaseCommand):
    help = 'Deletes inactive users who registered more than 48 hours ago.'

    def handle(self, *args, **options):
        # Calculate the threshold (current time - 48 hours)
        threshold = timezone.now() - timedelta(hours=48)

        # Find users who are inactive AND joined before the threshold
        old_inactive_users = User.objects.filter(is_active=False, date_joined__lt=threshold)
        
        count = old_inactive_users.count()
        
        if count > 0:
            old_inactive_users.delete()
            self.stdout.write(self.style.SUCCESS(f'Successfully deleted {count} expired inactive users.'))
        else:
            self.stdout.write(self.style.SUCCESS('No expired inactive users found.'))