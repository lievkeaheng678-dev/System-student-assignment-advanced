import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.contrib.sessions.models import Session
from django.core import signing
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import emails, security
from .forms import (
    DeleteAccountForm,
    LoginForm,
    ProfileForm,
    RegisterForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)

User = get_user_model()

DEMO_LOCKED_MESSAGE = (
    "This is the shared demo account, so that change is switched off. "
    "Create your own account to try it."
)


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "home.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        emails.send_verification_email(request, user)

        if settings.REQUIRE_EMAIL_VERIFICATION:
            return render(request, "accounts/verify_sent.html", {"email": user.email})

        login(request, user)
        security.record_login(request, user.email, success=True, user=user)
        messages.success(
            request,
            f"Welcome, {user.first_name}! Your student ID is {user.student_id}. "
            "Keep it handy: you can sign in with it.",
        )
        return redirect("dashboard")

    return render(request, "accounts/register.html", {"form": form})


class PortalLoginView(LoginView):
    form_class = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)  # signs the user in
        user = form.get_user()
        security.record_login(self.request, form.cleaned_data["username"], success=True, user=user)
        if form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(settings.REMEMBER_ME_AGE)
        else:
            self.request.session.set_expiry(0)  # ends when the browser closes
        return response


class PortalPasswordResetView(PasswordResetView):
    form_class = StyledPasswordResetForm
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    # Emails are rendered without a request, so context processors don't run.
    extra_email_context = {"SITE_NAME": settings.SITE_NAME}


class PortalPasswordResetConfirmView(PasswordResetConfirmView):
    form_class = StyledSetPasswordForm
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

def verify_email(request, token):
    try:
        payload = emails.read_verification_token(token)
        user = User.objects.get(pk=payload["uid"], email=payload["email"])
    except (signing.BadSignature, User.DoesNotExist, KeyError):
        messages.error(
            request,
            "That confirmation link has expired or isn't valid. Sign in and ask for a new one.",
        )
        return redirect("dashboard" if request.user.is_authenticated else "login")

    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    messages.success(request, "Email confirmed. Thank you!")
    return redirect("dashboard" if request.user.is_authenticated else "login")


@login_required
@require_POST
def resend_verification(request):
    user = request.user
    if user.email_verified:
        messages.info(request, "Your email is already confirmed.")
        return redirect("dashboard")

    last = request.session.get("last_verification_sent", 0)
    if time.time() - last < 60:
        messages.warning(request, "We just sent one. Give it a minute, then try again.")
        return redirect("dashboard")

    request.session["last_verification_sent"] = time.time()
    if emails.send_verification_email(request, user):
        messages.success(request, f"Confirmation link sent to {user.email}.")
    else:
        messages.error(request, "We couldn't send the email right now. Please try again later.")
    return redirect("dashboard")


# ---------------------------------------------------------------------------
# Signed-in pages
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    user = request.user
    checklist = [
        {"done": user.email_verified, "label": "Confirm your email", "kind": "verify"},
        {"done": bool(user.program and user.year_of_study), "label": "Add your program and year", "kind": "profile"},
        {"done": bool(user.phone), "label": "Add a phone number", "kind": "profile"},
        {"done": user.date_of_birth is not None, "label": "Add your date of birth", "kind": "profile"},
        {"done": bool(user.bio), "label": "Write a short bio", "kind": "profile"},
    ]
    context = {
        "checklist": checklist,
        "open_tasks": sum(1 for item in checklist if not item["done"]),
        "recent_logins": user.login_events.filter(success=True)[:5],
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
def profile(request):
    # Edit a fresh copy so a half-valid form never changes request.user.
    user = User.objects.get(pk=request.user.pk)
    original_email = user.email
    is_demo = user.is_demo_account

    form = ProfileForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        new_email = form.cleaned_data["email"]
        email_changed = new_email != original_email

        if email_changed and is_demo:
            messages.error(request, DEMO_LOCKED_MESSAGE)
            return redirect("profile")

        obj = form.save(commit=False)
        if email_changed:
            obj.email_verified = False
        obj.save()

        if email_changed:
            emails.send_verification_email(request, obj)
            messages.success(request, "Profile saved. We sent a confirmation link to your new email.")
        else:
            messages.success(request, "Profile saved.")
        return redirect("profile")

    return render(request, "accounts/profile.html", {"form": form})


@login_required
def security_page(request):
    events = request.user.login_events.all()[:15]
    return render(request, "accounts/security.html", {"events": events})


@login_required
@require_POST
def signout_others(request):
    current_key = request.session.session_key
    removed = 0
    sessions = Session.objects.filter(expire_date__gt=timezone.now()).exclude(session_key=current_key)
    for session in sessions:
        if session.get_decoded().get("_auth_user_id") == str(request.user.pk):
            session.delete()
            removed += 1
    if removed:
        messages.success(request, f"Signed out {removed} other device{'s' if removed != 1 else ''}.")
    else:
        messages.info(request, "You're not signed in anywhere else.")
    return redirect("security")


class PortalPasswordChangeView(PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("security")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_demo_account:
            messages.error(request, DEMO_LOCKED_MESSAGE)
            return redirect("security")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Password changed. Other devices stay signed in unless you sign them out.")
        return super().form_valid(form)


@login_required
def delete_account(request):
    user = request.user
    if user.is_demo_account:
        messages.error(request, DEMO_LOCKED_MESSAGE)
        return redirect("security")
    if user.is_staff:
        messages.error(request, "Staff accounts can only be removed from the admin site.")
        return redirect("security")

    form = DeleteAccountForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        logout(request)
        user.delete()
        messages.success(request, "Your account has been deleted.")
        return redirect("home")
    return render(request, "accounts/delete_account.html", {"form": form})
