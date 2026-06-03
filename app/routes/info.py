from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.auth.deps import require_login
from app.auth.flash import get_flashes
from app.models.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/info")
async def info(
    request: Request,
    current_user: User = Depends(require_login),
):
    return templates.TemplateResponse(
        "info.html",
        {
            "request": request,
            "current_user": current_user,
            "flashes": get_flashes(request),
        },
    )
