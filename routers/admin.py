import hashlib
import os
import secrets

from datetime import datetime, timedelta

from fastapi import (
    APIRouter,
    Request,
    Depends,
    Form,
)

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy import or_
from sqlalchemy.orm import Session

from database.database import get_db

from models.admin import Admin
from models.user import User

from models.password_reset_token import PasswordResetToken

from auth.password import verify_password


router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# PASSWORD RESET CONFIGURATION
# ============================================================

RESET_TOKEN_EXPIRE_MINUTES = 30

PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    ""
).strip().rstrip("/")


# ============================================================
# ADMIN AUTH HELPER
# ============================================================

def get_logged_in_admin(
    request: Request,
    db: Session,
):

    admin_id = request.session.get(
        "admin_id"
    )

    if not admin_id:
        return None

    admin = (
        db.query(Admin)
        .filter(
            Admin.id == admin_id
        )
        .first()
    )

    return admin


# ============================================================
# ADMIN LOGIN PAGE
# ============================================================

@router.get("/login")
async def admin_login_page(
    request: Request
):

    return templates.TemplateResponse(
        "admin/login.html",
        {
            "request": request
        }
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@router.post("/login")
async def admin_login(

    request: Request,

    username: str = Form(...),

    password: str = Form(...),

    db: Session = Depends(get_db),

):

    username = username.strip()

    admin = (
        db.query(Admin)
        .filter(
            Admin.username == username
        )
        .first()
    )

    if not admin:

        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request,
                "message":
                    "Invalid username or password"
            }
        )


    if not verify_password(
        password,
        admin.password
    ):

        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request,
                "message":
                    "Invalid username or password"
            }
        )


    request.session[
        "admin_id"
    ] = admin.id


    return RedirectResponse(
        "/admin/dashboard",
        status_code=303
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@router.get("/dashboard")
async def admin_dashboard(

    request: Request,

    db: Session = Depends(get_db),

):

    admin = get_logged_in_admin(
        request,
        db
    )

    if not admin:

        return RedirectResponse(
            "/admin/login",
            status_code=303
        )


    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "admin": admin
        }
    )


# ============================================================
# MANAGE USERS
# ============================================================

@router.get("/users")
async def manage_users(

    request: Request,

    q: str = "",

    db: Session = Depends(get_db),

):

    admin = get_logged_in_admin(
        request,
        db
    )

    if not admin:

        return RedirectResponse(
            "/admin/login",
            status_code=303
        )


    q = q.strip()

    users = []


    # ========================================================
    # SEARCH USERNAME OR PHONE
    # ========================================================

    if q:

        search_pattern = (
            f"%{q}%"
        )

        users = (
            db.query(User)
            .filter(
                or_(
                    User.username.ilike(
                        search_pattern
                    ),
                    User.phone.ilike(
                        search_pattern
                    ),
                )
            )
            .order_by(
                User.id.desc()
            )
            .limit(100)
            .all()
        )


    return templates.TemplateResponse(
        "admin/manage-users.html",
        {
            "request": request,
            "admin": admin,
            "users": users,
            "query": q,
            "reset_link": None,
            "reset_user": None,
            "reset_expiry": None,
            "message": None,
        }
    )


# ============================================================
# GENERATE PASSWORD RESET LINK
# ============================================================

@router.post(
    "/users/{user_id}/generate-reset-link"
)
async def generate_reset_link(

    request: Request,

    user_id: int,

    q: str = Form(""),

    db: Session = Depends(get_db),

):

    admin = get_logged_in_admin(
        request,
        db
    )

    if not admin:

        return RedirectResponse(
            "/admin/login",
            status_code=303
        )


    q = q.strip()


    # ========================================================
    # FIND USER
    # ========================================================

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )


    if not user:

        return templates.TemplateResponse(
            "admin/manage-users.html",
            {
                "request": request,
                "admin": admin,
                "users": [],
                "query": q,
                "reset_link": None,
                "reset_user": None,
                "reset_expiry": None,
                "message":
                    "User was not found.",
            }
        )


    # ========================================================
    # INVALIDATE ALL PREVIOUS UNUSED LINKS
    # ========================================================

    now = datetime.utcnow()

    previous_tokens = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id
            == user.id,
            PasswordResetToken.used_at
            .is_(None),
        )
        .all()
    )


    for old_token in previous_tokens:

        old_token.used_at = now


    # ========================================================
    # GENERATE RANDOM TOKEN
    # ========================================================

    raw_token = secrets.token_urlsafe(
        48
    )


    token_hash = hashlib.sha256(
        raw_token.encode(
            "utf-8"
        )
    ).hexdigest()


    expires_at = (
        now
        + timedelta(
            minutes=RESET_TOKEN_EXPIRE_MINUTES
        )
    )


    reset_token = PasswordResetToken(

        user_id=user.id,

        token_hash=token_hash,

        expires_at=expires_at,

        used_at=None,

        created_at=now,
    )


    db.add(
        reset_token
    )

    db.commit()


    # ========================================================
    # BUILD RESET URL
    # ========================================================

    if PUBLIC_BASE_URL:

        base_url = (
            PUBLIC_BASE_URL
        )

    else:

        base_url = (
            str(
                request.base_url
            )
            .rstrip("/")
        )


    reset_link = (
        f"{base_url}"
        f"/reset-password/"
        f"{user.id}/"
        f"{raw_token}"
    )


    # ========================================================
    # SEARCH RESULTS AGAIN
    # ========================================================

    users = []

    if q:

        search_pattern = (
            f"%{q}%"
        )

        users = (
            db.query(User)
            .filter(
                or_(
                    User.username.ilike(
                        search_pattern
                    ),
                    User.phone.ilike(
                        search_pattern
                    ),
                )
            )
            .order_by(
                User.id.desc()
            )
            .limit(100)
            .all()
        )


    # ========================================================
    # RETURN PAGE WITH RESET LINK
    # ========================================================

    return templates.TemplateResponse(
        "admin/manage-users.html",
        {
            "request": request,

            "admin": admin,

            "users": users,

            "query": q,

            "reset_link":
                reset_link,

            "reset_user":
                user,

            "reset_expiry":
                expires_at,

            "message":
                "Password reset link generated successfully."
        }
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@router.get("/logout")
async def admin_logout(
    request: Request
):

    request.session.pop(
        "admin_id",
        None
    )

    return RedirectResponse(
        "/admin/login",
        status_code=303
    )