"""Error handlers that can be imported without loading feature views."""
from django.shortcuts import render
from django.views.decorators.csrf import requires_csrf_token

@requires_csrf_token
def csrf_failure(request, reason=""):
    """Render the localized 403 page without exposing rejection details."""
    return render(request, "403.html", status=403)
