
import hashlib
import os
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from database.database import get_db

from models.admin import Admin
from models.user import User
from models.password_reset_tokens import PasswordResetToken

from models.deposit_request import DepositRequest
from models.withdrawal_request import WithdrawalRequest
from models.transaction import Transaction


router = APIRouter(
    prefix="/admin",
    tags=["Admin Users"]
)

templates = Jinja2Templates(directory="templates")


# =========================================================
# CONFIG
# =========================================================

RESET_TOKEN_EXPIRE_MINUTES = 30

PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    ""
).strip().rstrip("/")


# =========================================================
# ADMIN AUTH
# =========================================================

def get_logged_in_admin(
    request: Request,
    db: Session
):
    admin_id = request.session.get("admin_id")

    if not admin_id:
        return None

    admin = (
        db.query(Admin)
        .filter(Admin.id == admin_id)
        .first()
    )

    if not admin:
        request.session.pop("admin_id", None)
        return None

    return admin


# =========================================================
# SAFE VALUE HELPERS
# =========================================================

def safe_value(obj, *names, default=None):
    """
    Safely read a value from a SQLAlchemy model.

    This makes the page tolerant of slightly different
    DepositRequest / WithdrawalRequest field names.
    """

    if obj is None:
        return default

    for name in names:
        try:
            value = getattr(obj, name, None)

            if value is not None:
                return value

        except Exception:
            pass

    return default


def money(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def request_amount(obj):
    return money(
        safe_value(
            obj,
            "amount",
            "requested_amount",
            "deposit_amount",
            "withdrawal_amount",
            "value",
            default=0
        )
    )


def request_status(obj):
    return str(
        safe_value(
            obj,
            "status",
            "state",
            default="Unknown"
        )
        or "Unknown"
    )


def request_date(obj):
    value = safe_value(
        obj,
        "created_at",
        "requested_at",
        "date",
        "created",
        default=None
    )

    return value


# =========================================================
# MANAGE USERS
# =========================================================

@router.get("/users")
async def manage_users(
    request: Request,
    q: str = "",
    selected_user_id: int | None = None,
    db: Session = Depends(get_db)
):
    admin = get_logged_in_admin(request, db)

    if not admin:
        return RedirectResponse(
            "/admin/login",
            status_code=303
        )

    q = (q or "").strip()

    users_query = db.query(User)

    if q:
        search = f"%{q}%"

        users_query = users_query.filter(
            or_(
                User.username.ilike(search),
                User.phone.ilike(search)
            )
        )

    users = (
        users_query
        .order_by(User.id.desc())
        .limit(100)
        .all()
    )

    selected_user = None

    if selected_user_id:
        selected_user = (
            db.query(User)
            .filter(User.id == selected_user_id)
            .first()
        )

    return render_manage_users(
        request=request,
        db=db,
        admin=admin,
        users=users,
        q=q,
        selected_user=selected_user
    )


# =========================================================
# USER DETAILS
# =========================================================

@router.get("/users/{user_id}")
async def admin_user_details(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    admin = get_logged_in_admin(request, db)

    if not admin:
        return RedirectResponse(
            "/admin/login",
            status_code=303
        )

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not user:
        return RedirectResponse(
            "/admin/users",
            status_code=303
        )

    return render_manage_users(
        request=request,
        db=db,
        admin=admin,
        users=[user],
        q="",
        selected_user=user
    )


# =========================================================
# RENDER USER PAGE
# =========================================================

def render_manage_users(
    request: Request,
    db: Session,
    admin,
    users,
    q="",
    selected_user=None,
    reset_link=None,
    reset_expires_at=None,
    message=None,
    message_type="success"
):
    user_details = None

    if selected_user:

        # -------------------------------------------------
        # DEPOSITS
        # -------------------------------------------------

        deposits = []

        try:
            deposits = (
                db.query(DepositRequest)
                .filter(
                    DepositRequest.user_id == selected_user.id
                )
                .order_by(
                    DepositRequest.created_at.desc()
                )
                .all()
            )
        except Exception:
            deposits = []

        # -------------------------------------------------
        # WITHDRAWALS
        # -------------------------------------------------

        withdrawals = []

        try:
            withdrawals = (
                db.query(WithdrawalRequest)
                .filter(
                    WithdrawalRequest.user_id == selected_user.id
                )
                .order_by(
                    WithdrawalRequest.created_at.desc()
                )
                .all()
            )
        except Exception:
            withdrawals = []

        # -------------------------------------------------
        # TRANSACTIONS
        # -------------------------------------------------

        transactions = []

        try:
            transactions = (
                db.query(Transaction)
                .filter(
                    Transaction.user_id == selected_user.id
                )
                .order_by(
                    Transaction.created_at.desc()
                )
                .limit(100)
                .all()
            )
        except Exception:
            transactions = []

        # -------------------------------------------------
        # CALCULATE DEPOSIT / WITHDRAW TOTALS
        # -------------------------------------------------

        total_deposits = sum(
            request_amount(item)
            for item in deposits
        )

        total_withdrawals = sum(
            request_amount(item)
            for item in withdrawals
        )

        # -------------------------------------------------
        # STATUS TOTALS
        # -------------------------------------------------

        completed_deposits = sum(
            request_amount(item)
            for item in deposits
            if request_status(item).lower()
            in (
                "completed",
                "approved",
                "success",
                "successful",
                "done"
            )
        )

        completed_withdrawals = sum(
            request_amount(item)
            for item in withdrawals
            if request_status(item).lower()
            in (
                "completed",
                "approved",
                "success",
                "successful",
                "done"
            )
        )

        user_details = {
            "deposits": deposits,
            "withdrawals": withdrawals,
            "transactions": transactions,
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "completed_deposits": completed_deposits,
            "completed_withdrawals": completed_withdrawals,
        }

    return templates.TemplateResponse(
        "admin/manage-users.html",
        {
            "request": request,
            "admin": admin,
            "users": users,
            "q": q,
            "selected_user": selected_user,
            "user_details": user_details,
            "reset_link": reset_link,
            "reset_expires_at": reset_expires_at,
            "message": message,
            "message_type": message_type,
        }
    )


# =========================================================
# GENERATE PASSWORD RESET LINK
# =========================================================

@router.post(
    "/users/{user_id}/generate-reset-link"
)
async def generate_reset_link(
    user_id: int,
    request: Request,
    q: str = Form(""),
    db: Session = Depends(get_db)
):
    admin = get_logged_in_admin(request, db)

    if not admin:
        return RedirectResponse(
            "/admin/login",
            status_code=303
        )

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not user:
        return RedirectResponse(
            "/admin/users",
            status_code=303
        )

    now = datetime.utcnow()

    # -----------------------------------------------------
    # INVALIDATE ALL OLD RESET LINKS
    # -----------------------------------------------------

    old_tokens = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None)
        )
        .all()
    )

    for old_token in old_tokens:
        old_token.used_at = now

    # -----------------------------------------------------
    # CREATE NEW RANDOM TOKEN
    # -----------------------------------------------------

    raw_token = secrets.token_urlsafe(48)

    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    expires_at = (
        now +
        timedelta(
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

    db.add(reset_token)
    db.commit()

    # -----------------------------------------------------
    # BUILD RESET URL
    # -----------------------------------------------------

    if PUBLIC_BASE_URL:
        base_url = PUBLIC_BASE_URL
    else:
        base_url = str(
            request.base_url
        ).rstrip("/")

    reset_link = (
        f"{base_url}"
        f"/reset-password/"
        f"{user.id}/"
        f"{raw_token}"
    )

    # -----------------------------------------------------
    # RELOAD USER
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    return render_manage_users(
        request=request,
        db=db,
        admin=admin,
        users=[user],
        q=q,
        selected_user=user,
        reset_link=reset_link,
        reset_expires_at=expires_at,
        message=(
            "Password reset link generated successfully."
        ),
        message_type="success"
    )
