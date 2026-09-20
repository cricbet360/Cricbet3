import hashlib

from datetime import datetime

from fastapi import (
    APIRouter,
    Request,
    Form,
    Depends,
)

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from database.database import get_db

from models.user import User
from models.password_reset_token import PasswordResetToken

from auth.password import (
    hash_password,
)


router = APIRouter(
    tags=["Password Reset"]
)

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# PASSWORD VALIDATION
# ============================================================

def validate_password(
    password: str
):

    if len(password) < 8:

        return (
            False,
            "Password must contain at least 8 characters."
        )


    if not any(
        char.isupper()
        for char in password
    ):

        return (
            False,
            "Password must contain at least one uppercase letter."
        )


    if not any(
        char.islower()
        for char in password
    ):

        return (
            False,
            "Password must contain at least one lowercase letter."
        )


    if not any(
        char.isdigit()
        for char in password
    ):

        return (
            False,
            "Password must contain at least one number."
        )


    if not any(
        not char.isalnum()
        for char in password
    ):

        return (
            False,
            "Password must contain at least one special character."
        )


    return (
        True,
        ""
    )


# ============================================================
# VERIFY RESET TOKEN
# ============================================================

def find_valid_reset_token(
    user_id: int,
    raw_token: str,
    db: Session,
):

    if not raw_token:
        return None


    token_hash = hashlib.sha256(
        raw_token.encode(
            "utf-8"
        )
    ).hexdigest()


    now = datetime.utcnow()


    reset_token = (
        db.query(
            PasswordResetToken
        )
        .filter(
            PasswordResetToken.user_id
            == user_id,

            PasswordResetToken.token_hash
            == token_hash,

            PasswordResetToken.used_at
            .is_(None),

            PasswordResetToken.expires_at
            > now,
        )
        .first()
    )


    return reset_token


# ============================================================
# RESET PASSWORD PAGE
# ============================================================

@router.get(
    "/reset-password/{user_id}/{token}"
)
async def reset_password_page(

    request: Request,

    user_id: int,

    token: str,

    db: Session = Depends(get_db),

):

    reset_token = find_valid_reset_token(
        user_id,
        token,
        db
    )


    if not reset_token:

        return templates.TemplateResponse(
            "reset-password.html",
            {
                "request": request,

                "valid_link": False,

                "message":
                    "This password reset link is invalid, expired, or has already been used.",
            }
        )


    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )


    if not user:

        return templates.TemplateResponse(
            "reset-password.html",
            {
                "request": request,

                "valid_link": False,

                "message":
                    "The user account could not be found.",
            }
        )


    return templates.TemplateResponse(
        "reset-password.html",
        {
            "request": request,

            "valid_link": True,

            "user": user,

            "user_id": user_id,

            "token": token,

            "expires_at":
                reset_token.expires_at,

            "message": None,
        }
    )


# ============================================================
# CHANGE PASSWORD
# ============================================================

@router.post(
    "/reset-password/{user_id}/{token}"
)
async def reset_password(

    request: Request,

    user_id: int,

    token: str,

    password: str = Form(...),

    confirm_password: str = Form(...),

    db: Session = Depends(get_db),

):

    reset_token = find_valid_reset_token(
        user_id,
        token,
        db
    )


    if not reset_token:

        return templates.TemplateResponse(
            "reset-password.html",
            {
                "request": request,

                "valid_link": False,

                "message":
                    "This password reset link is invalid, expired, or has already been used.",
            }
        )


    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )


    if not user:

        return templates.TemplateResponse(
            "reset-password.html",
            {
                "request": request,

                "valid_link": False,

                "message":
                    "The user account could not be found.",
            }
        )


    # ========================================================
    # PASSWORD MATCH
    # ========================================================

    if password != confirm_password:

        return templates.TemplateResponse(
            "reset-password.html",
            {
                "request": request,

                "valid_link": True,

                "user": user,

                "user_id": user_id,

                "token": token,

                "expires_at":
                    reset_token.expires_at,

                "message":
                    "Passwords do not match.",
            }
        )


    # ========================================================
    # PASSWORD VALIDATION
    # ========================================================

    valid, message = validate_password(
        password
    )


    if not valid:

        return templates.TemplateResponse(
            "reset-password.html",
            {
                "request": request,

                "valid_link": True,

                "user": user,

                "user_id": user_id,

                "token": token,

                "expires_at":
                    reset_token.expires_at,

                "message": message,
            }
        )


    # ========================================================
    # RE-CHECK TOKEN BEFORE COMMIT
    #
    # This prevents an already-consumed token from being
    # used again.
    # ========================================================

    now = datetime.utcnow()

    token_hash = hashlib.sha256(
        token.encode(
            "utf-8"
        )
    ).hexdigest()


    locked_token = (
        db.query(
            PasswordResetToken
        )
        .filter(
            PasswordResetToken.id
            == reset_token.id,

            PasswordResetToken.user_id
            == user_id,

            PasswordResetToken.token_hash
            == token_hash,

            PasswordResetToken.used_at
            .is_(None),

            PasswordResetToken.expires_at
            > now,
        )
        .with_for_update()
        .first()
    )


    if not locked_token:

        return templates.TemplateResponse(
            "reset-password.html",
            {
                "request": request,

                "valid_link": False,

                "message":
                    "This password reset link is no longer valid.",
            }
        )


    # ========================================================
    # CHANGE PASSWORD
    # ========================================================

    user.password = hash_password(
        password
    )


    # ========================================================
    # IMMEDIATELY CONSUME TOKEN
    # ========================================================

    locked_token.used_at = now


    # ========================================================
    # INVALIDATE ANY OTHER ACTIVE RESET TOKENS
    #
    # This ensures another previously generated link for the
    # same user cannot be used after the password changes.
    # ========================================================

    other_tokens = (
        db.query(
            PasswordResetToken
        )
        .filter(
            PasswordResetToken.user_id
            == user_id,

            PasswordResetToken.id
            != locked_token.id,

            PasswordResetToken.used_at
            .is_(None),
        )
        .all()
    )


    for other_token in other_tokens:

        other_token.used_at = now


    try:

        db.commit()

    except Exception:

        db.rollback()

        return templates.TemplateResponse(
            "reset-password.html",
            {
                "request": request,

                "valid_link": False,

                "message":
                    "Unable to change the password. Please try again.",
            }
        )


    # ========================================================
    # SUCCESS
    # ========================================================

    return templates.TemplateResponse(
        "reset-password.html",
        {
            "request": request,

            "valid_link": False,

            "success": True,

            "message":
                "Your password has been changed successfully. This reset link has now expired.",
        }
    )