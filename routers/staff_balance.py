from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Request,
    Form
)

from fastapi.responses import (
    HTMLResponse,
    RedirectResponse
)

from database.database import SessionLocal
from models.user import User

try:
    from models import AccountTransaction
except ImportError:
    AccountTransaction = None


router = APIRouter(
    prefix="/staff",
    tags=["staff balance"]
)


# =========================================================
# STAFF LOGIN CHECK
# =========================================================

def is_staff(request: Request):

    # Change this if your existing staff session key
    # is different.

    return (
        request.session.get(
            "staff_logged_in"
        ) is True
    )


def db_session():

    return SessionLocal()


# =========================================================
# STAFF BALANCE PAGE
# =========================================================

@router.get(
    "/balance",
    response_class=HTMLResponse
)
async def staff_balance_page(
    request: Request
):

    if not is_staff(request):

        return RedirectResponse(
            "/login",
            status_code=303
        )

    db = db_session()

    try:

        return request.app.state.templates.TemplateResponse(
            request=request,
            name="staff/balance.html",
            context={}
        )

    finally:
        db.close()


# =========================================================
# SEARCH USER
# =========================================================

@router.get("/balance/search")
async def search_user(
    request: Request,
    username: str = ""
):

    if not is_staff(request):

        return {
            "success": False,
            "message": "Unauthorized"
        }

    username = username.strip()

    if not username:

        return {
            "success": False,
            "message": "Enter username"
        }

    db = db_session()

    try:

        user = (
            db.query(User)
            .filter(
                User.username == username
            )
            .first()
        )

        if not user:

            return {
                "success": False,
                "message": "User not found"
            }

        return {
            "success": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "balance": float(
                    user.balance or 0
                )
            }
        }

    finally:
        db.close()


# =========================================================
# UPDATE BALANCE
# =========================================================

@router.post("/balance/update")
async def update_balance(
    request: Request,
    username: str = Form(...),
    amount: str = Form(...),
    action: str = Form(...),
    reason: str = Form("")
):

    if not is_staff(request):

        return {
            "success": False,
            "message": "Unauthorized"
        }

    username = username.strip()
    action = action.strip().upper()
    reason = reason.strip()

    if action not in (
        "CREDIT",
        "DEBIT"
    ):

        return {
            "success": False,
            "message": "Invalid balance action"
        }

    try:

        value = Decimal(
            amount
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        ValueError
    ):

        return {
            "success": False,
            "message": "Invalid amount"
        }

    if value <= 0:

        return {
            "success": False,
            "message": "Amount must be greater than zero"
        }

    db = db_session()

    try:

        user = (
            db.query(User)
            .filter(
                User.username == username
            )
            .first()
        )

        if not user:

            return {
                "success": False,
                "message": "User not found"
            }

        before = Decimal(
            str(
                user.balance or 0
            )
        )

        if action == "CREDIT":

            after = before + value

        else:

            after = before - value

            if after < 0:

                return {
                    "success": False,
                    "message": (
                        "Insufficient balance"
                    )
                }

        # -------------------------------------------------
        # UPDATE USER BALANCE
        # -------------------------------------------------

        user.balance = after

        # -------------------------------------------------
        # ACCOUNT STATEMENT
        # -------------------------------------------------

        if AccountTransaction is not None:

            transaction = AccountTransaction(
                user_id=user.id,
                type=action,
                amount=value,
                balance_before=before,
                balance_after=after,
                reason=reason or (
                    "Manual balance adjustment"
                ),
                created_at=datetime.now(
                    timezone.utc
                )
            )

            db.add(transaction)

        db.commit()

        return {
            "success": True,
            "username": user.username,
            "balance": float(after),
            "message": (
                "Balance updated successfully"
            )
        }

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()