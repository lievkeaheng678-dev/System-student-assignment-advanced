import logging
from datetime import date

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from . import security

logger = logging.getLogger(__name__)
User = get_user_model()

PROGRAMS = [
    "Business Administration",
    "Computer Science",
    "Education",
    "Engineering",
    "Health Sciences",
    "Law",
    "Social Sciences",
    "Visual Arts",
    "Other",
]
PROGRAM_CHOICES = [("", "Choose your program")] + [(p, p) for p in PROGRAMS]
YEAR_CHOICES = [("", "Choose your year")] + [(str(n), f"Year {n}") for n in range(1, 7)]

phone_validator = RegexValidator(
    r"^[0-9+\-\s()]{6,20}$",
    "Enter a phone number using digits, spaces, + - and brackets.",
)


class StyledFormMixin:
    """Adds the CSS classes the stylesheet expects to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            css = "check" if isinstance(widget, forms.CheckboxInput) else "input"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterForm(StyledFormMixin, forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "data-strength": "1"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    program = forms.ChoiceField(choices=PROGRAM_CHOICES, required=False)
    year_of_study = forms.TypedChoiceField(
        label="Year of study",
        choices=YEAR_CHOICES,
        coerce=int,
        empty_value=None,
        required=False,
    )
    accept_terms = forms.BooleanField(
        label="I agree to the terms of use and privacy policy",
        error_messages={"required": "Please accept the terms to create your account."},
    )
    # Honeypot: real people never see this field, bots fill it in.
    website = forms.CharField(required=False, label="Leave this empty")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "program", "year_of_study")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].help_text = password_validation.password_validators_help_text_html()
        self.fields["first_name"].widget.attrs.update(
            {"autocomplete": "given-name", "data-preview": "first", "autofocus": True}
        )
        self.fields["last_name"].widget.attrs.update(
            {"autocomplete": "family-name", "data-preview": "last"}
        )
        self.fields["email"].widget.attrs.update({"autocomplete": "email"})
        self.fields["program"].widget.attrs["data-preview"] = "program"
        self.fields["year_of_study"].widget.attrs["data-preview"] = "year"
        self.fields["website"].widget.attrs.update({"tabindex": "-1", "autocomplete": "off"})

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise ValidationError("Invalid submission.")
        return ""

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists. Try signing in.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("The two passwords don't match.")
        return password2

    def _post_clean(self):
        super()._post_clean()
        # Runs after the instance is filled in, so the "too similar to your
        # name or email" check has something to compare against.
        password = self.cleaned_data.get("password2")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except ValidationError as error:
                self.add_error("password2", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


# ---------------------------------------------------------------------------
# Sign in
# ---------------------------------------------------------------------------

class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.CharField(
        label="Email or student ID",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    remember_me = forms.BooleanField(required=False, label="Keep me signed in on this device")

    error_messages = {
        "invalid_login": "That email, student ID or password isn't right. Check them and try again.",
        "inactive": "This account has been deactivated. Contact the school office.",
    }

    def clean(self):
        identifier = self.cleaned_data.get("username")
        if identifier:
            wait = security.lockout_seconds(identifier, security.client_ip(self.request))
            if wait:
                minutes = max(1, round(wait / 60))
                raise ValidationError(
                    f"Too many failed attempts. Try again in {minutes} "
                    f"minute{'s' if minutes != 1 else ''}, or reset your password.",
                    code="locked",
                )
        try:
            return super().clean()
        except ValidationError as error:
            if getattr(error, "code", None) == "invalid_login":
                security.record_login(self.request, identifier, success=False)
            raise

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
            raise ValidationError(
                "Please confirm your email first. We sent a link when you registered.",
                code="unverified",
            )


# ---------------------------------------------------------------------------
# Profile and account
# ---------------------------------------------------------------------------

class ProfileForm(StyledFormMixin, forms.ModelForm):
    phone = forms.CharField(required=False, max_length=20, validators=[phone_validator])
    program = forms.ChoiceField(choices=PROGRAM_CHOICES, required=False)
    year_of_study = forms.TypedChoiceField(
        label="Year of study",
        choices=YEAR_CHOICES,
        coerce=int,
        empty_value=None,
        required=False,
    )
    bio = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="A line or two about you. Up to 500 characters.",
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone",
            "date_of_birth",
            "program",
            "year_of_study",
            "bio",
        )
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep a program an admin typed in, even if it isn't in our list.
        current = getattr(self.instance, "program", "")
        if current and current not in PROGRAMS:
            self.fields["program"].choices = list(PROGRAM_CHOICES) + [(current, current)]
        self.fields["email"].help_text = "Changing your email means you'll need to confirm it again."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        clash = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError("Another account already uses this email.")
        return email

    def clean_date_of_birth(self):
        value = self.cleaned_data.get("date_of_birth")
        if value and (value > date.today() or value.year < 1900):
            raise ValidationError("Enter a real date of birth.")
        return value


class DeleteAccountForm(StyledFormMixin, forms.Form):
    password = forms.CharField(
        label="Your password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    confirm = forms.BooleanField(label="I understand this permanently deletes my account")

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise ValidationError("That password isn't right.")
        return password


# ---------------------------------------------------------------------------
# Built-in password forms, styled to match
# ---------------------------------------------------------------------------

class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.pop("autofocus", None)
        self.fields["new_password1"].widget.attrs["data-strength"] = "1"


class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    def send_mail(self, *args, **kwargs):
        # A mail-server hiccup should not turn into an error page, and it
        # must not reveal whether the address belongs to an account.
        try:
            super().send_mail(*args, **kwargs)
        except Exception:
            logger.exception("Password reset email failed")


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs["data-strength"] = "1"
