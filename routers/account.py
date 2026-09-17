from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database.database import SessionLocal
from models.user import User


try:
    from models import AccountTransaction
except ImportError:
    AccountTransaction = None


router = APIRouter(
    prefix="/account",
    tags=["account"]
)


def get_db():
    return SessionLocal()


def current_user(request, db):

    user_id = request.session.get("user_id")

    if not user_id:
        return None

    return db.query(User).filter(
        User.id == user_id
    ).first()


# =========================================================
# ACCOUNT STATEMENT
# =========================================================

@router.get("/statement")
async def account_statement(request: Request):

    db = get_db()

    try:

        user = current_user(request, db)

        if not user:
            return JSONResponse(
                {
                    "success": False,
                    "message": "Not logged in"
                },
                status_code=401
            )

        if AccountTransaction is None:

            return {
                "success": True,
                "transactions": []
            }

        rows = (
            db.query(AccountTransaction)
            .filter(
                AccountTransaction.user_id == user.id
            )
            .order_by(
                AccountTransaction.created_at.desc()
            )
            .limit(500)
            .all()
        )

        transactions = []

        for row in rows:

            transactions.append({
                "id": row.id,
                "type": getattr(row, "type", ""),
                "amount": float(
                    getattr(row, "amount", 0) or 0
                ),
                "balance_before": float(
                    getattr(
                        row,
                        "balance_before",
                        0
                    ) or 0
                ),
                "balance_after": float(
                    getattr(
                        row,
                        "balance_after",
                        0
                    ) or 0
                ),
                "reason": getattr(
                    row,
                    "reason",
                    ""
                ),
                "created_at": (
                    row.created_at.isoformat()
                    if getattr(
                        row,
                        "created_at",
                        None
                    )
                    else None
                )
            })

        return {
            "success": True,
            "balance": float(
                user.balance or 0
            ),
            "transactions": transactions
        }

    finally:
        db.close()


# =========================================================
# PROFIT / LOSS
# =========================================================

@router.get("/profit-loss")
async def profit_loss(request: Request):

    db = get_db()

    try:

        user = current_user(request, db)

        if not user:
            return JSONResponse(
                {
                    "success": False,
                    "message": "Not logged in"
                },
                status_code=401
            )

        # This intentionally uses your existing bet records
        # if the model is available.

        try:
            from models import Bet
        except ImportError:
            Bet = None

        total_staked = Decimal("0")
        total_won = Decimal("0")
        total_lost = Decimal("0")

        if Bet is not None:

            bets = (
                db.query(Bet)
                .filter(
                    Bet.user_id == user.id
                )
                .all()
            )

            for bet in bets:

                stake = Decimal(
                    str(
                        getattr(
                            bet,
                            "stake",
                            0
                        ) or 0
                    )
                )

                status = str(
                    getattr(
                        bet,
                        "status",
                        ""
                    ) or ""
                ).lower()

                total_staked += stake

                if status in (
                    "won",
                    "win",
                    "settled_won"
                ):

                    potential = Decimal(
                        str(
                            getattr(
                                bet,
                                "potential_win",
                                stake
                            ) or stake
                        )
                    )

                    total_won += (
                        potential - stake
                    )

                elif status in (
                    "lost",
                    "loss",
                    "settled_lost"
                ):

                    total_lost += stake

        profit = total_won - total_lost

        return {
            "success": True,
            "total_staked": float(
                total_staked
            ),
            "total_won": float(
                total_won
            ),
            "total_lost": float(
                total_lost
            ),
            "profit_loss": float(
                profit
            )
        }

    finally:
        db.close()