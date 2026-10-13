from django.http import HttpResponse


class HealthCheckMiddleware:
    """
    Answers /healthz/ before anything else runs.

    Render pings this path to decide whether a deploy is healthy. Answering
    early means the check never depends on ALLOWED_HOSTS, the HTTPS redirect
    or the database, so a slow database can't fail a deploy.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz/":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
