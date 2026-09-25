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

from services.bet_settlement import settle_pending_bets

router = APIRouter(
    prefix="/bets",
    tags=["Bets"],
)


# =========================================================
# REQUEST MODEL
# =========================================================

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
    payout_percent: float | None = None


# =========================================================
# ERROR HELPER
# =========================================================

def _error(
    message: str,
    status_code: int = 400,
):
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message,
        },
    )


# =========================================================
# MARKET TYPE
# =========================================================

def _normalize_market_type(
    value: str | None,
) -> str:

    market_type = str(
        value or "MATCH_ODDS"
    ).strip().upper()

    aliases = {
        "MATCH": "MATCH_ODDS",
        "MATCHODDS": "MATCH_ODDS",
        "MATCH_ODD": "MATCH_ODDS",
        "MATCH ODDS": "MATCH_ODDS",

        "BOOK": "BOOKMAKER",
        "BOOKMAKER_ODDS": "BOOKMAKER",
        "BOOKMAKER ODDS": "BOOKMAKER",

        "FANCY_ODDS": "FANCY",
        "FANCY ODDS": "FANCY",

        "SESSION_ODDS": "SESSION",
        "SESSION ODDS": "SESSION",
    }

    return aliases.get(
        market_type,
        market_type,
    )


# =========================================================
# SIDE
# =========================================================

def _normalize_side(
    value: str | None,
) -> tuple[str | None, str | None]:

    original = str(
        value or ""
    ).strip().upper()

    if original in {
        "BACK",
        "YES",
    }:
        return "BACK", None

    if original in {
        "LAY",
        "NO",
    }:
        return "LAY", None

    return None, "Invalid bet side."


# =========================================================
# PLACE BET
# =========================================================

@router.post("/place")
async def place_bet(
    request: Request,
    payload: PlaceBetRequest,
    db: Session = Depends(get_db),
):

    # =====================================================
    # LOGIN
    # =====================================================

    user_id = request.session.get("user_id")

    if not user_id:
        return _error(
            "Please login first.",
            401,
        )

    # =====================================================
    # USER
    # =====================================================

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )
    except Exception as exc:

        db.rollback()

        return _error(
            f"Database error while loading user: {exc}",
            500,
        )

    if not user:

        request.session.clear()

        return _error(
            "Please login again.",
            401,
        )

    # =====================================================
    # USER STATUS
    # =====================================================

    if str(
        user.status or ""
    ).strip().lower() != "active":

        return _error(
            "Your account is not active.",
            403,
        )

    # =====================================================
    # STRINGS
    # =====================================================

    game_id = str(
        payload.game_id or ""
    ).strip()

    event_id = str(
        payload.event_id or ""
    ).strip()

    market_id = str(
        payload.market_id or ""
    ).strip()

    market_type = _normalize_market_type(
        payload.market_type
    )

    market_name = str(
        payload.market_name or ""
    ).strip()

    selection_id = str(
        payload.selection_id or ""
    ).strip()

    selection_name = str(
        payload.selection_name or ""
    ).strip()

    if not game_id:
        return _error(
            "Missing game ID."
        )

    if not market_id:
        return _error(
            "Missing market ID."
        )

    if not selection_id:
        return _error(
            "Missing selection ID."
        )

    if not selection_name:
        return _error(
            "Missing selection name."
        )

    if not event_id:
        event_id = game_id

    # =====================================================
    # MARKET TYPE
    # =====================================================

    allowed_market_types = {
        "MATCH_ODDS",
        "BOOKMAKER",
        "FANCY",
        "SESSION",
    }

    if market_type not in allowed_market_types:

        return _error(
            f"Invalid market type: {market_type}"
        )

    # =====================================================
    # SIDE
    # =====================================================

    side, side_error = _normalize_side(
        payload.side
    )

    if side_error:
        return _error(
            side_error
        )

    # =====================================================
    # STAKE
    # =====================================================

    try:

        stake = Decimal(
            str(payload.stake)
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):

        return _error(
            "Invalid stake."
        )

    if stake <= Decimal("0.00"):

        return _error(
            "Stake must be greater than ₹0."
        )

    # =====================================================
    # ODDS
    # =====================================================

    try:

        odds = Decimal(
            str(payload.odds)
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):

        return _error(
            "Invalid odds."
        )

    if odds <= Decimal("1.00"):

        return _error(
            "Invalid odds."
        )

    # =====================================================
    # BALANCE
    # =====================================================

    try:

        current_balance = Decimal(
            str(
                user.balance
                if user.balance is not None
                else 0
            )
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):

        return _error(
            "Unable to read account balance.",
            500,
        )

    if stake > current_balance:

        return _error(
            "Insufficient balance. "
            f"Available balance: ₹{current_balance:.2f}"
        )

    # =====================================================
    # FANCY / SESSION PAYOUT
    # =====================================================

    payout_percent = None

    if market_type in {
        "FANCY",
        "SESSION",
    }:

        try:

            payout_percent = Decimal(
                str(
                    payload.payout_percent
                    if payload.payout_percent is not None
                    else 0
                )
            )

        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):

            return _error(
                "Invalid Fancy payout percentage."
            )

        if payout_percent <= Decimal("0.00"):

            return _error(
                "Invalid Fancy payout percentage."
            )

        payout_multiplier = (
            Decimal("1.00")
            +
            (
                payout_percent
                /
                Decimal("100.00")
            )
        )

        potential_win = (
            stake
            *
            payout_multiplier
        ).quantize(
            Decimal("0.01")
        )

    else:

        payout_percent = None

        potential_win = (
            stake
            *
            odds
        ).quantize(
            Decimal("0.01")
        )

    # =====================================================
    # NEW BALANCE
    # =====================================================

    new_balance = (
        current_balance
        -
        stake
    ).quantize(
        Decimal("0.01")
    )

    # =====================================================
    # DATABASE TRANSACTION
    # =====================================================

    try:

        # -------------------------------------------------
        # BET
        # -------------------------------------------------

        bet = Bet(
            user_id=user.id,
            stake=float(stake),
            total_odds=float(odds),
            potential_win=float(
                potential_win
            ),
            status="pending",
        )

        db.add(bet)

        # Generate bet.id
        db.flush()

        # -------------------------------------------------
        # MARKET NAME
        # -------------------------------------------------

        if market_name:

            stored_market_name = (
                f"{market_type} | "
                f"{market_name}"
            )

        else:

            display_names = {
                "MATCH_ODDS": "Match Odds",
                "BOOKMAKER": "Bookmaker",
                "FANCY": "Fancy",
                "SESSION": "Session",
            }

            stored_market_name = (
                f"{market_type} | "
                f"{display_names.get(
                    market_type,
                    market_type
                )}"
            )

        # -------------------------------------------------
        # BET SELECTION
        # -------------------------------------------------

        bet_selection = BetSelection(
            bet_id=bet.id,

            market_id=market_id,

            event_id=event_id,

            market_type=market_type,

            selection_id=selection_id,

            runner_name=selection_name,

            side=side,

            price=float(odds),

           
            

            market_name=market_name,

            event_name=None,
        )

        db.add(bet_selection)

        # -------------------------------------------------
        # UPDATE USER BALANCE
        # -------------------------------------------------

        user.balance = float(
            new_balance
        )

        # -------------------------------------------------
        # UPDATE WALLET
        # -------------------------------------------------

        wallet = (
            db.query(Wallet)
            .filter(
                Wallet.user_id == user.id
            )
            .first()
        )

        if wallet is not None:

            wallet.balance = new_balance

        # -------------------------------------------------
        # TRANSACTION
        # -------------------------------------------------

        transaction = Transaction(
            user_id=user.id,

            amount=-float(stake),

            transaction_type="Bet",

            status="Completed",

            reference_type="Bet",

            reference_id=bet.id,

            description=(
                f"{market_type} | "
                f"{side} "
                f"{selection_name} "
                f"@ {odds} | "
                f"stake ₹{stake:.2f}"
            ),
        )

        db.add(transaction)

        # -------------------------------------------------
        # COMMIT
        # -------------------------------------------------

        db.commit()

        db.refresh(bet)

        db.refresh(user)

        return {
            "success": True,

            "message": "Bet placed successfully.",

            "bet_id": bet.id,

            "status": bet.status,

            "game_id": game_id,

            "event_id": event_id,

            "market_id": market_id,

            "market_type": market_type,

            "market_name": market_name,

            "selection_id": selection_id,

            "selection_name": selection_name,

            "side": side,

            "display_side": (
                "YES"
                if (
                    market_type
                    in {"FANCY", "SESSION"}
                    and side == "BACK"
                )
                else (
                    "NO"
                    if (
                        market_type
                        in {"FANCY", "SESSION"}
                        and side == "LAY"
                    )
                    else side
                )
            ),

            "stake": float(stake),

            "odds": float(odds),

            "payout_percent": (
                float(payout_percent)
                if payout_percent is not None
                else None
            ),

            "potential_win": float(
                potential_win
            ),

            "balance": float(
                new_balance
            ),
        }

    except Exception as exc:

        db.rollback()

        print(
            "[BET PLACE ERROR]",
            repr(exc),
        )

        return _error(
            f"Could not place bet: {exc}",
            500,
        )


# =========================================================
# MY BETS
# =========================================================

@router.get("/my-bets")
async def my_bets(
    request: Request,
    db: Session = Depends(get_db),
):

    user_id = request.session.get(
        "user_id"
    )

    if not user_id:

        return _error(
            "Please login first.",
            401,
        )

    try:

        bets = (
            db.query(Bet)
            .filter(
                Bet.user_id == user_id
            )
            .order_by(
                Bet.created_at.desc()
            )
            .all()
        )

        result = []

        for bet in bets:

            selections = []

            for selection in bet.selections:

                stored_market = (
                    selection.market_name
                    or ""
                )

                market_type = ""

                display_market_name = (
                    stored_market
                )

                if "|" in stored_market:

                    parts = (
                        stored_market
                        .split("|", 1)
                    )

                    market_type = (
                        parts[0]
                        .strip()
                        .upper()
                    )

                    display_market_name = (
                        parts[1].strip()
                    )

                selections.append(
                    {
                        "market_id":
                            selection.market_id,

                        "event_id":
                            selection.event_id,

                        "selection_id":
                            selection.selection_id,

                        "runner_name":
                            selection.runner_name,

                        "side":
                            selection.side,

                        "display_side": (
                            "YES"
                            if (
                                market_type
                                in {
                                    "FANCY",
                                    "SESSION",
                                }
                                and selection.side
                                == "BACK"
                            )
                            else (
                                "NO"
                                if (
                                    market_type
                                    in {
                                        "FANCY",
                                        "SESSION",
                                    }
                                    and selection.side
                                    == "LAY"
                                )
                                else selection.side
                            )
                        ),

                        "price":
                            float(
                                selection.price
                            ),

                        "market_name":
                            display_market_name,

                        "market_type":
                            market_type,

                        "event_name":
                            selection.event_name,
                    }
                )

            result.append(
                {
                    "id":
                        bet.id,

                    "stake":
                        float(
                            bet.stake
                        ),

                    "total_odds":
                        float(
                            bet.total_odds
                        ),

                    "potential_win":
                        float(
                            bet.potential_win
                        ),

                    "status":
                        bet.status,

                    "created_at": (
                        bet.created_at.isoformat()
                        if bet.created_at
                        else None
                    ),

                    "selections":
                        selections,
                }
            )

        return {
            "success": True,
            "bets": result,
        }

    except Exception as exc:

        print(
            "[MY BETS ERROR]",
            repr(exc),
        )

        return _error(
            f"Could not load bets: {exc}",
            500,
        )

@router.post("/settle-pending")
def settle_pending(
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")

    if not user_id:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "detail": "Login required",
            },
        )

    try:
        stats = settle_pending_bets(
            db,
            limit=100,
        )

        return {
            "success": True,
            "message": "Settlement cycle completed.",
            "stats": stats,
        }

    except Exception as exc:
        db.rollback()

        print(
            "[BET SETTLEMENT ROUTER]",
            repr(exc),
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "detail": str(exc),
            },
        )