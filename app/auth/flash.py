from starlette.requests import Request


def flash(request: Request, message: str, category: str = "info") -> None:
    """Store a one-time message in the session for display on the next page."""
    messages = request.session.get("_flashes", [])
    messages.append({"message": message, "category": category})
    request.session["_flashes"] = messages


def get_flashes(request: Request) -> list[dict]:
    """Read and clear all flash messages from the session.

    Only writes to the session when there's actually something to clear —
    writing an empty list on every single page view (there was one on EVERY
    request before this) forces SessionMiddleware to re-sign and resend the
    session cookie on every response, which under concurrent requests (e.g.
    two admin tabs open at once) can race and overwrite a page's just-issued
    CSRF token with a different one before the form on that page is submitted.
    """
    messages = request.session.get("_flashes", [])
    if messages:
        request.session["_flashes"] = []
    return messages
