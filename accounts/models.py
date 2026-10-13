import zlib

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from .security import describe_user_agent


class UserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).strip().lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("email_verified", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def by_identifier(self, identifier):
        """Find a user by email or student ID, ignoring case. None if absent."""
        identifier = (identifier or "").strip()
        if not identifier:
            return None
        return self.filter(
            models.Q(email__iexact=identifier) | models.Q(student_id__iexact=identifier)
        ).first()


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("email address", max_length=254, unique=True)
    first_name = models.CharField("first name", max_length=80)
    last_name = models.CharField("last name", max_length=80)
    student_id = models.CharField(
        "student ID", max_length=20, unique=True, blank=True, editable=False
    )

    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    program = models.CharField(max_length=80, blank=True)
    year_of_study = models.PositiveSmallIntegerField(null=True, blank=True)
    bio = models.TextField(blank=True)

    email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(
        "active",
        default=True,
        help_text="Designates whether this user should be treated as active. "
        "Unselect this instead of deleting accounts.",
    )
    is_staff = models.BooleanField(
        "staff status",
        default=False,
        help_text="Designates whether the user can log into this admin site.",
    )
    date_joined = models.DateTimeField("date joined", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = "student"
        verbose_name_plural = "students"

    def __str__(self):
        return self.email

    # -- saving -------------------------------------------------------------

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        if not self.student_id:
            self.student_id = self._generate_student_id()
        super().save(*args, **kwargs)

    def _generate_student_id(self):
        import secrets

        year = timezone.now().year
        for _ in range(50):
            candidate = f"STU-{year}-{secrets.randbelow(90000) + 10000}"
            if not type(self).objects.filter(student_id=candidate).exists():
                return candidate
        raise RuntimeError("Could not generate a unique student ID.")

    # -- display helpers ----------------------------------------------------

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def full_name(self):
        return self.get_full_name() or self.email

    @property
    def initials(self):
        letters = (self.first_name[:1] + self.last_name[:1]).upper()
        return letters or self.email[:1].upper()

    @property
    def avatar_hue(self):
        """A stable colour per student, derived from their ID."""
        return zlib.crc32((self.student_id or self.email).encode()) % 360

    @property
    def is_demo_account(self):
        return bool(settings.DEMO_MODE and self.email == settings.DEMO_ACCOUNT_EMAIL.lower())

    @property
    def profile_completeness(self):
        checks = [
            bool(self.first_name and self.last_name),
            self.email_verified,
            bool(self.phone),
            self.date_of_birth is not None,
            bool(self.program),
            self.year_of_study is not None,
            bool(self.bio),
        ]
        return int(round(100 * sum(checks) / len(checks)))


class LoginEvent(models.Model):
    """Every sign-in attempt: powers the lockout and the Security page."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="login_events",
    )
    identifier = models.CharField(max_length=254, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        outcome = "ok" if self.success else "failed"
        return f"{self.identifier} {outcome} at {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def device(self):
        return describe_user_agent(self.user_agent)
