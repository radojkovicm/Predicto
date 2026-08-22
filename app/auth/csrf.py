import secrets

from fastapi import HTTPException, Request
from starlette.status import HTTP_403_FORBIDDEN

_MUTATING_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def csrf_token(request: Request) -> str:
    """Get (or create) this session's CSRF token. Registered as a Jinja global so
    templates can call {{ csrf_token(request) }} to embed it in a <meta> tag —
    main.js then attaches it to every form on submit.
    """
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


async def verify_csrf(request: Request) -> None:
    """Router-level dependency — rejects any state-changing request whose form
    doesn't carry a csrf_token matching this session's token.
    """
    if request.method not in _MUTATING_METHODS:
        return

    form = await request.form()
    submitted = form.get("csrf_token")
    expected = request.session.get("csrf_token")

    if not expected or not submitted or not secrets.compare_digest(str(submitted), str(expected)):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Your session expired or the form was tampered with. Please refresh the page and try again.",
        )
