from django.conf import settings


def site(request):
    """Values every template needs: site name and the demo-mode banner."""
    context = {"SITE_NAME": settings.SITE_NAME, "DEMO_MODE": settings.DEMO_MODE}
    if settings.DEMO_MODE:
        context["DEMO_EMAIL"] = settings.DEMO_ACCOUNT_EMAIL
        context["DEMO_PASSWORD"] = settings.DEMO_ACCOUNT_PASSWORD
    return context
