"""
Sign-in security helpers.

Models are imported inside the functions on purpose: models.py imports
describe_user_agent from this module, so a top-level import here would be
circular.
"""

import ipaddress
from datetime import timedelta

from django.conf import settings
from django.db.models import Max, Q
from django.utils import timezone

# Failures from one IP are tolerated up to this many times the per-name limit,
# so a school sharing one network address isn't locked out by one forgetful kid.
IP_LIMIT_MULTIPLIER = 4


def client_ip(request):
    """
    The visitor's IP address.

    Behind Render's proxy the real address is the first entry of
    X-Forwarded-For. Only trust this when you really are behind a proxy
    you control, as on Render.
    """
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def describe_user_agent(user_agent):
    """'Chrome on Windows' from a raw User-Agent string. Good enough for a log."""
    ua = user_agent or ""
    if not ua:
        return "Unknown device"

    if "Edg/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua or "CriOS" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = "Browser"

    if "iPhone" in ua or "iPad" in ua:
        system = "iOS"
    elif "Android" in ua:
        system = "Android"
    elif "Windows" in ua:
        system = "Windows"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        system = "macOS"
    elif "CrOS" in ua:
        system = "ChromeOS"
    elif "Linux" in ua:
        system = "Linux"
    else:
        system = "unknown system"
    return f"{browser} on {system}"


def normalize_identifier(identifier):
    return (identifier or "").strip().lower()[:254]


def lockout_seconds(identifier, ip):
    """
    Seconds left on a lockout, or 0 if the person may try.

    A name is locked after LOGIN_MAX_ATTEMPTS failures inside the window,
    counting only failures since their last successful sign-in. The same rule
    applies to names that don't exist, so the response never reveals whether
    an account is real.
    """
    from .models import LoginEvent, User

    now = timezone.now()
    window = timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    since = now - window
    ident = normalize_identifier(identifier)
    if not ident:
        return 0

    user = User.objects.by_identifier(ident)
    who = Q(identifier=ident)
    if user is not None:
        who |= Q(user=user)

    last_ok = LoginEvent.objects.filter(who, success=True, created_at__gte=since).aggregate(
        latest=Max("created_at")
    )["latest"]
    start = last_ok or since
    failures = LoginEvent.objects.filter(who, success=False, created_at__gt=start)
    count = failures.count()
    if count >= settings.LOGIN_MAX_ATTEMPTS:
        newest = failures.aggregate(latest=Max("created_at"))["latest"]
        remaining = (newest + window - now).total_seconds()
        if remaining > 0:
            return int(remaining) + 1

    if ip:
        ip_failures = LoginEvent.objects.filter(ip_address=ip, success=False, created_at__gte=since)
        if ip_failures.count() >= settings.LOGIN_MAX_ATTEMPTS * IP_LIMIT_MULTIPLIER:
            newest = ip_failures.aggregate(latest=Max("created_at"))["latest"]
            remaining = (newest + window - now).total_seconds()
            if remaining > 0:
                return int(remaining) + 1
    return 0


def record_login(request, identifier, success, user=None):
    """Store one sign-in attempt. Never raises: logging must not break login."""
    from .models import LoginEvent, User

    try:
        ident = normalize_identifier(identifier)
        if user is None and not success:
            user = User.objects.by_identifier(ident)
        LoginEvent.objects.create(
            user=user,
            identifier=ident,
            ip_address=client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT", "") if request else "")[:255],
            success=success,
        )
    except Exception:  # pragma: no cover - defensive
        import logging

        logging.getLogger(__name__).exception("Could not record login event")
