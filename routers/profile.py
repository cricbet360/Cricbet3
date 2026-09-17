from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from models.user import User
from models.bet import Bet
from models.transaction import Transaction

router = APIRouter()

templates = Jinja2Templates(directory="templates")


def get_logged_in_user(request: Request, db: Session):
    user_id = request.session.get("user_id")

    if not user_id:
        return None

    return db.query(User).filter(User.id == user_id).first()


# ============================================================
# PROFILE
# ============================================================

@router.get("/profile")
async def profile(
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_logged_in_user(request, db)

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Please login first."
            }
        )

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": user,
        }
    )


# ============================================================
# MY BETS
# ============================================================

@router.get("/my-bets")
async def my_bets_page(
    request: Request,
    db: Session = Depends(get_db)
):
    user_id = request.session.get("user_id")

    if not user_id:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Please login first."
            }
        )

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "User not found."
            }
        )

    bets = (
        db.query(Bet)
        .filter(Bet.user_id == user.id)
        .order_by(Bet.created_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        "my-bets.html",
        {
            "request": request,
            "user": user,
            "bets": bets
        }
    )


# ============================================================
# PROFIT & LOSS
# ============================================================

@router.get("/profit-loss")
async def profit_loss(
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_logged_in_user(request, db)

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Please login first."
            }
        )

    bets = (
        db.query(Bet)
        .filter(Bet.user_id == user.id)
        .order_by(Bet.created_at.desc())
        .all()
    )

    total_staked = 0.0
    total_won = 0.0
    total_lost = 0.0
    profit_loss_value = 0.0

    for bet in bets:

        stake = float(bet.stake or 0)

        total_staked += stake

        status = (bet.status or "").lower()

        if status == "won":
            winnings = float(bet.potential_win or 0)

            total_won += winnings

            # Profit = winnings - stake
            profit_loss_value += winnings - stake

        elif status == "lost":
            total_lost += stake

            # Lost stake
            profit_loss_value -= stake

        elif status in ["cancelled", "void", "refunded"]:
            # No profit/loss
            pass

        # Pending bets do not affect realised P&L yet.

    return templates.TemplateResponse(
        "profit-loss.html",
        {
            "request": request,
            "user": user,
            "bets": bets,

            # IMPORTANT:
            # Your HTML expects exactly this variable.
            "profit_loss": profit_loss_value,

            "total_staked": total_staked,
            "total_won": total_won,
            "total_lost": total_lost,
        }
    )


# ============================================================
# ACCOUNT STATEMENT
# ============================================================

@router.get("/account-statement")
async def account_statement(
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_logged_in_user(request, db)

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Please login first."
            }
        )

    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        "account-statement.html",
        {
            "request": request,
            "user": user,
            "transactions": transactions,
        }
    )


# ============================================================
# GAME RULES
# ============================================================

@router.get("/game-rules")
async def game_rules(request: Request):

    return templates.TemplateResponse(
        "game-rules.html",
        {
            "request": request
        }
    )


# ============================================================
# DEPOSIT
# ============================================================

@router.get("/deposit")
async def deposit(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Please login first."
            }
        )

    return templates.TemplateResponse(
        "deposit.html",
        {
            "request": request
        }
    )


# ============================================================
# WITHDRAW
# ============================================================

@router.get("/withdraw")
async def withdraw(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Please login first."
            }
        )

    return templates.TemplateResponse(
        "withdraw.html",
        {
            "request": request
        }
    )