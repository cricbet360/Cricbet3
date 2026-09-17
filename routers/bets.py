from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from models.user import User
from models.wallet import Wallet
from models.bet import Bet
from models.bet_selection import BetSelection
from models.transaction import Transaction


router = APIRouter(
    prefix="/bets",
    tags=["Bets"],
)


class PlaceBetRequest(BaseModel):
    game_id: str
    event_id: str | None = None
    market_id: str
    market_type: str | None = None
    market_name: str | None = None
    selection_id: str
    selection_name: str
    side: str
    odds: float
    stake: float


def _error(message: str, status_code: int = 400):
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message,
        },
    )


@router.post("/place")
async def place_bet(
    request: Request,
    payload: PlaceBetRequest,
    db: Session = Depends(get_db),
):
    # ------------------------------------------------------
    # LOGIN
    # ------------------------------------------------------
    user_id = request.session.get("user_id")

    if not user_id:
        return _error("Please login first.", 401)

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not user:
        request.session.clear()
        return _error("Please login again.", 401)

    # ------------------------------------------------------
    # USER STATUS
    # ------------------------------------------------------
    if str(user.status or "").lower() != "active":
        return _error("Your account is not active.", 403)

    # ------------------------------------------------------
    # VALIDATE BET DATA
    # ------------------------------------------------------
    try:
        stake = Decimal(str(payload.stake)).quantize(
            Decimal("0.01")
        )
        odds = Decimal(str(payload.odds))
    except (InvalidOperation, ValueError, TypeError):
        return _error("Invalid stake or odds.")

    if stake <= Decimal("0.00"):
        return _error("Stake must be greater than ₹0.")

    if odds <= Decimal("1.00"):
        return _error("Invalid odds.")

    side = str(payload.side or "").strip().upper()

    if side not in {"BACK", "LAY"}:
        return _error("Invalid bet type.")

    if not str(payload.game_id).strip():
        return _error("Missing game ID.")

    if not str(payload.market_id).strip():
        return _error("Missing market ID.")

    if not str(payload.selection_id).strip():
        return _error("Missing selection ID.")

    if not str(payload.selection_name).strip():
        return _error("Missing selection name.")

    # ------------------------------------------------------
    # BALANCE
    #
    # User.balance is the project's source balance.
    # Wallet.balance is synchronized when a wallet exists.
    # ------------------------------------------------------
    current_balance = Decimal(
        str(user.balance if user.balance is not None else 0)
    ).quantize(Decimal("0.01"))

    if stake > current_balance:
        return _error(
            f"Insufficient balance. Available balance: ₹{current_balance:.2f}"
        )

    # ------------------------------------------------------
    # CALCULATE POTENTIAL WIN
    # ------------------------------------------------------
    potential_win = (
        stake * odds
    ).quantize(Decimal("0.01"))

    # ------------------------------------------------------
    # CREATE BET
    # ------------------------------------------------------
    bet = Bet(
        user_id=user.id,
        stake=float(stake),
        total_odds=float(odds),
        potential_win=float(potential_win),
        status="pending",
    )

    db.add(bet)
    db.flush()

    selection = BetSelection(
        bet_id=bet.id,
        market_id=str(payload.market_id).strip(),
        event_id=(
            str(payload.event_id).strip()
            if payload.event_id
            else str(payload.game_id).strip()
        ),
        selection_id=str(payload.selection_id).strip(),
        runner_name=str(payload.selection_name).strip(),
        side=side,
        price=float(odds),
        market_name=(
            str(payload.market_name).strip()
            if payload.market_name
            else str(payload.market_type or "Match Odds")
        ),
        event_name=None,
    )

    db.add(selection)

    # ------------------------------------------------------
    # DEDUCT STAKE
    # ------------------------------------------------------
    new_balance = (
        current_balance - stake
    ).quantize(Decimal("0.01"))

    user.balance = float(new_balance)

    # Keep the wallet table synchronized if it exists.
    wallet = (
        db.query(Wallet)
        .filter(Wallet.user_id == user.id)
        .first()
    )

    if wallet is not None:
        wallet.balance = new_balance

    # ------------------------------------------------------
    # TRANSACTION
    # ------------------------------------------------------
    transaction = Transaction(
        user_id=user.id,
        amount=-stake,
        transaction_type="Bet",
        status="Completed",
        reference_type="Bet",
        reference_id=bet.id,
        description=(
            f"{side} {payload.selection_name} "
            f"@ {odds} | stake ₹{stake:.2f}"
        ),
    )

    db.add(transaction)

    try:
        db.commit()
        db.refresh(bet)
        db.refresh(user)

    except Exception as exc:
        db.rollback()
        return _error(
            f"Could not place bet: {exc}",
            500,
        )

    return {
        "success": True,
        "message": "Bet placed successfully.",
        "bet_id": bet.id,
        "status": bet.status,
        "stake": float(stake),
        "odds": float(odds),
        "potential_win": float(potential_win),
        "balance": float(new_balance),
    }


@router.get("/my-bets")
async def my_bets(
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")

    if not user_id:
        return _error("Please login first.", 401)

    bets = (
        db.query(Bet)
        .filter(Bet.user_id == user_id)
        .order_by(Bet.created_at.desc())
        .all()
    )

    return {
        "success": True,
        "bets": [
            {
                "id": bet.id,
                "stake": float(bet.stake),
                "total_odds": float(bet.total_odds),
                "potential_win": float(bet.potential_win),
                "status": bet.status,
                "created_at": (
                    bet.created_at.isoformat()
                    if bet.created_at
                    else None
                ),
                "selections": [
                    {
                        "market_id": selection.market_id,
                        "event_id": selection.event_id,
                        "selection_id": selection.selection_id,
                        "runner_name": selection.runner_name,
                        "side": selection.side,
                        "price": float(selection.price),
                        "market_name": selection.market_name,
                        "event_name": selection.event_name,
                    }
                    for selection in bet.selections
                ],
            }
            for bet in bets
        ],
    }
