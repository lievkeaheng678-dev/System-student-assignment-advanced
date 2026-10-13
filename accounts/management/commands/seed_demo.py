from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create (or reset) the shared demo student used on public demo sites."

    def handle(self, *args, **options):
        User = get_user_model()
        email = settings.DEMO_ACCOUNT_EMAIL.strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User(email=email)
        user.first_name = "Alex"
        user.last_name = "Demo"
        user.program = "Computer Science"
        user.year_of_study = 2
        user.bio = "This is the shared demo account. Create your own to try every feature."
        user.email_verified = True
        user.is_active = True
        user.set_password(settings.DEMO_ACCOUNT_PASSWORD)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"seed_demo: demo student ready ({email})."))
