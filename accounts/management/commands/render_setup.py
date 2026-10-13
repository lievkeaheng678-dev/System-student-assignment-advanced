from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Everything Render's build step needs, in one command: collect static files, "
        "apply migrations, create the admin, and seed the demo student."
    )

    def handle(self, *args, **options):
        self.stdout.write("== collectstatic")
        call_command("collectstatic", interactive=False, verbosity=1)

        # Safety net: if the models ever drift from the committed migrations,
        # write the missing migration instead of failing the deploy.
        try:
            call_command("makemigrations", check=True, dry_run=True, verbosity=0)
        except SystemExit:
            self.stdout.write(self.style.WARNING(
                "== models changed without a migration; generating one now. "
                "Run `python manage.py makemigrations` locally and commit it."
            ))
            call_command("makemigrations", interactive=False, verbosity=1)

        self.stdout.write("== migrate")
        call_command("migrate", interactive=False, verbosity=1)

        self.stdout.write("== admin account")
        call_command("ensure_superuser")

        if settings.SEED_DEMO:
            self.stdout.write("== demo student")
            call_command("seed_demo")

        self.stdout.write(self.style.SUCCESS("render_setup finished."))
