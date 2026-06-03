#!/usr/bin/env python
"""CLI to create the first admin user (or promote an existing user)."""
import sys, os, getpass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models.models import User
from app.auth.password import hash_password


def main():
    username = input("Admin username: ").strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    password = getpass.getpass("Password (min 6 chars): ")
    if len(password) < 6:
        print("Password too short.")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            existing.password_hash = hash_password(password)
            existing.is_admin = True
            existing.failed_login_attempts = 0
            existing.locked_until = None
            db.commit()
            print(f"User '{username}' updated to admin.")
        else:
            db.add(User(username=username, password_hash=hash_password(password), is_admin=True))
            db.commit()
            print(f"Admin user '{username}' created.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
