from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config.config import settings
from app.auth.deps import NeedsLoginException, NeedsAdminException
from app.routes import auth, info, integration, matches, predictions, profile, ranking
from app.routes import settings as settings_routes
from app.routes import admin as admin_routes

app = FastAPI(
    title="WC 2026 Predicto",
    # Hide API docs in production
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    # Remove server version header
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# Session cookie — HttpOnly + SameSite=Lax; Secure only in production
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    https_only=not settings.DEBUG,
    same_site="lax",
    session_cookie="predicto_session",
    max_age=60 * 60 * 24 * 7,  # 7 days
)

# IP-level rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routes
app.include_router(auth.router)
app.include_router(matches.router)
app.include_router(predictions.router)
app.include_router(ranking.router)
app.include_router(profile.router)
app.include_router(info.router)
app.include_router(settings_routes.router)
app.include_router(admin_routes.router, prefix="/admin")
app.include_router(integration.router, prefix="/api")


# Redirect unauthenticated users to login
@app.exception_handler(NeedsLoginException)
async def needs_login_handler(request: Request, exc: NeedsLoginException):
    return RedirectResponse(url="/login", status_code=302)


@app.exception_handler(NeedsAdminException)
async def needs_admin_handler(request: Request, exc: NeedsAdminException):
    return RedirectResponse(url="/", status_code=302)
