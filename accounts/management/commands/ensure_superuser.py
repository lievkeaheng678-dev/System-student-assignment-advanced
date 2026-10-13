import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Create an admin account from DJANGO_SUPERUSER_EMAIL / DJANGO_SUPERUSER_PASSWORD "
        "if it doesn't exist yet. Safe to run on every deploy: it never changes an "
        "existing account. Render's free plan has no shell, so this is how you get an admin."
    )

    def handle(self, *args, **options):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip().lower()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not email or not password:
            self.stdout.write("ensure_superuser: no DJANGO_SUPERUSER_EMAIL/PASSWORD set, skipping.")
            return

        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write(f"ensure_superuser: {email} already exists, leaving it alone.")
            return

        User.objects.create_superuser(
            email=email,
            password=password,
            first_name=os.environ.get("DJANGO_SUPERUSER_FIRST_NAME", "Site"),
            last_name=os.environ.get("DJANGO_SUPERUSER_LAST_NAME", "Admin"),
        )
        self.stdout.write(self.style.SUCCESS(f"ensure_superuser: created admin {email}."))
