"""
Change (or create) an admin login without putting the password in any file.

Run from the project folder on the server:

    cd /opt/cricbet
    sudo -u cricbet venv/bin/python deploy/set_admin_password.py

You will be asked for the admin username and a new password (typed
hidden, so it does not appear on screen or in shell history).
"""

import getpass
import os
import sys

# Make the project importable when run as `python deploy/set_admin_password.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.password import hash_password
from database.database import Base, SessionLocal, engine
from models.admin import Admin


def main() -> None:

    Base.metadata.create_all(bind=engine)

    username = input("Admin username: ").strip()

    if not username:
        sys.exit("Username is required.")

    password = getpass.getpass("New password (min 10 characters): ")

    if len(password) < 10:
        sys.exit("Password must be at least 10 characters.")

    if password != getpass.getpass("Repeat new password: "):
        sys.exit("Passwords do not match. Nothing was changed.")

    db = SessionLocal()

    try:

        admin = (
            db.query(Admin)
            .filter(Admin.username == username)
            .first()
        )

        if admin:
            admin.password = hash_password(password)
            admin.status = "Active"
            action = "updated"

        else:
            answer = input(
                f"No admin named '{username}'. Create it? [y/N]: "
            ).strip().lower()

            if answer != "y":
                sys.exit("Nothing was changed.")

            db.add(
                Admin(
                    username=username,
                    password=hash_password(password),
                    status="Active",
                )
            )
            action = "created"

        db.commit()
        print(f"Admin '{username}' {action}.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
