from starlette.requests import Request


def flash(request: Request, message: str, category: str = "info") -> None:
    """Store a one-time message in the session for display on the next page."""
    messages = request.session.get("_flashes", [])
    messages.append({"message": message, "category": category})
    request.session["_flashes"] = messages


def get_flashes(request: Request) -> list[dict]:
    """Read and clear all flash messages from the session."""
    messages = request.session.get("_flashes", [])
    request.session["_flashes"] = []
    return messages
