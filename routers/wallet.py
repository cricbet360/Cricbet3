
from decimal import Decimal

from fastapi import (
    APIRouter,
    Request,
    Depends
)

from fastapi.responses import RedirectResponse

from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from database.database import get_db

from models.user import User
from models.wallet import Wallet


router = APIRouter()

templates = Jinja2Templates(
    directory="templates"
)


@router.get("/wallet")
async def wallet_page(
    request: Request,
    db: Session = Depends(get_db)
):

    # =========================================================
    # CHECK LOGIN
    # =========================================================

    user_id = request.session.get("user_id")

    if not user_id:

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # =========================================================
    # GET USER
    # =========================================================

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )


    if not user:

        request.session.clear()

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # =========================================================
    # GET WALLET
    # =========================================================

    wallet = (
        db.query(Wallet)
        .filter(Wallet.user_id == user.id)
        .first()
    )


    # =========================================================
    # CREATE WALLET
    #
    # IMPORTANT:
    # Use User.balance instead of 0.00
    # =========================================================

    if wallet is None:

        wallet = Wallet(
            user_id=user.id,
            balance=Decimal(
                str(user.balance or 0)
            ),
            exposure=Decimal("0.00")
        )

        db.add(wallet)

        db.commit()

        db.refresh(wallet)


    # =========================================================
    # KEEP WALLET BALANCE IN SYNC
    #
    # Your Profile currently uses User.balance.
    # Therefore Wallet should show the same amount.
    # =========================================================

    user_balance = Decimal(
        str(user.balance or 0)
    )


    if wallet.balance != user_balance:

        wallet.balance = user_balance

        db.commit()

        db.refresh(wallet)


    # =========================================================
    # WALLET PAGE
    # =========================================================

    return templates.TemplateResponse(
        "wallet.html",
        {
            "request": request,
            "user": user,
            "wallet": wallet
        }
    )

