import logging

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)

VERIFY_SALT = "accounts.verify-email"


def make_verification_token(user):
    # The email is inside the token, so changing your email voids old links.
    return signing.dumps({"uid": user.pk, "email": user.email}, salt=VERIFY_SALT)


def read_verification_token(token):
    """Returns the payload dict, or raises signing.BadSignature."""
    max_age = settings.EMAIL_VERIFY_MAX_AGE_DAYS * 24 * 60 * 60
    return signing.loads(token, salt=VERIFY_SALT, max_age=max_age)


def send_verification_email(request, user):
    """Send the verification link. Returns True on success, never raises."""
    url = request.build_absolute_uri(reverse("verify_email", args=[make_verification_token(user)]))
    body = render_to_string(
        "emails/verify_email.txt",
        {"user": user, "url": url, "days": settings.EMAIL_VERIFY_MAX_AGE_DAYS},
    )
    try:
        send_mail(
            f"Confirm your email for {settings.SITE_NAME}",
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Could not send verification email to %s", user.email)
        return False
