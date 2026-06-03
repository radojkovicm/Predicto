from fastapi import Depends, Request
from sqlalchemy.orm import Session
from typing import Optional

from app.db import get_db
from app.models.models import User


class NeedsLoginException(Exception):
    pass


class NeedsAdminException(Exception):
    pass


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> User:
    if not current_user:
        raise NeedsLoginException()
    return current_user


def require_admin(current_user: User = Depends(require_login)) -> User:
    if not current_user.is_admin:
        raise NeedsAdminException()
    return current_user
