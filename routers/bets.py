
from decimal import Decimal, InvalidOperation
from typing import Any

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

    # -----------------------------------------------------
    # FANCY / SESSION
    #
    # Example:
    #
    # YES:
    #   target_score = 40
    #   payout_rate = 100
    #
    # NO:
    #   target_score = 43
    #   payout_rate = 90
    # -----------------------------------------------------

    target_score: float | None = None

    payout_rate: float | None = None

    score: float | None = None

    size: float | None = None


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
# DECIMAL HELPER
# =========================================================

def _decimal(
    value: Any,
    default: str = "0",
) -> Decimal:

    if value is None:
        return Decimal(default)

    try:

        return Decimal(
            str(value)
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):

        return Decimal(default)


# =========================================================
# NORMALIZE MARKET TYPE
# =========================================================

def _normalize_market_type(
    value: str | None,
) -> str:

    market_type = str(
        value or "MATCH_ODDS"
    ).strip().upper()

    aliases = {

        "MATCH":
            "MATCH_ODDS",

        "MATCHODDS":
            "MATCH_ODDS",

        "MATCH_ODD":
            "MATCH_ODDS",

        "MATCH ODDS":
            "MATCH_ODDS",

        "BOOK":
            "BOOKMAKER",

        "BOOKMAKER_ODDS":
            "BOOKMAKER",

        "BOOKMAKER ODDS":
            "BOOKMAKER",

        "FANCY_ODDS":
            "FANCY",

        "FANCY ODDS":
            "FANCY",

        "SESSION_ODDS":
            "SESSION",

        "SESSION ODDS":
            "SESSION",
    }

    return aliases.get(
        market_type,
        market_type,
    )


# =========================================================
# NORMALIZE SIDE
#
# Fancy:
#   YES -> BACK
#   NO  -> LAY
#
# Normal:
#   BACK -> BACK
#   LAY  -> LAY
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
# DISPLAY SIDE
# =========================================================

def _display_side(
    market_type: str,
    side: str,
) -> str:

    if (
        market_type
        in {
            "FANCY",
            "SESSION",
        }
    ):

        if side == "BACK":
            return "YES"

        if side == "LAY":
            return "NO"

    return side


# =========================================================
# FANCY PAYOUT MULTIPLIER
#
# payout_rate = 100
# total multiplier = 2.00
#
# payout_rate = 90
# total multiplier = 1.90
# =========================================================

def _fancy_multiplier(
    payout_rate: Decimal,
) -> Decimal:

    return (
        Decimal("1.00")
        +
        (
            payout_rate /
            Decimal("100.00")
        )
    )


# =========================================================
# POTENTIAL RETURN
# =========================================================

def _potential_return(
    stake: Decimal,
    total_odds: Decimal,
) -> Decimal:

    return (
        stake *
        total_odds
    ).quantize(
        Decimal("0.01")
    )


# =========================================================
# LOGIN / PLACE BET
# =========================================================

@router.post("/place")
async def place_bet(
    request: Request,
    payload: PlaceBetRequest,
    db: Session = Depends(get_db),
):

    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )

    if not user_id:

        return _error(
            "Please login first.",
            401,
        )


    # -----------------------------------------------------
    # USER
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        request.session.clear()

        return _error(
            "Please login again.",
            401,
        )


    # -----------------------------------------------------
    # USER STATUS
    # -----------------------------------------------------

    if str(
        user.status or ""
    ).strip().lower() != "active":

        return _error(
            "Your account is not active.",
            403,
        )


    # -----------------------------------------------------
    # BASIC STRINGS
    # -----------------------------------------------------

    game_id = str(
        payload.game_id or ""
    ).strip()

    event_id = str(
        payload.event_id or ""
    ).strip()

    market_id = str(
        payload.market_id or ""
    ).strip()

    selection_id = str(
        payload.selection_id or ""
    ).strip()

    selection_name = str(
        payload.selection_name or ""
    ).strip()

    market_name = str(
        payload.market_name or ""
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


    # -----------------------------------------------------
    # MARKET TYPE
    # -----------------------------------------------------

    market_type = _normalize_market_type(
        payload.market_type
    )

    allowed_market_types = {

        "MATCH_ODDS",

        "BOOKMAKER",

        "FANCY",

        "SESSION",
    }


    if market_type not in allowed_market_types:

        return _error(
            "Invalid market type."
        )


    # -----------------------------------------------------
    # SIDE
    # -----------------------------------------------------

    side, side_error = _normalize_side(
        payload.side
    )

    if side_error:

        return _error(
            side_error
        )


    # -----------------------------------------------------
    # STAKE
    # -----------------------------------------------------

    stake = _decimal(
        payload.stake
    ).quantize(
        Decimal("0.01")
    )


    if stake <= Decimal("0.00"):

        return _error(
            "Stake must be greater than ₹0."
        )


    # -----------------------------------------------------
    # NORMAL VS FANCY
    # -----------------------------------------------------

    is_fancy = (
        market_type
        in {
            "FANCY",
            "SESSION",
        }
    )


    # =====================================================
    # FANCY / SESSION
    # =====================================================

    if is_fancy:

        target_score_raw = (
            payload.target_score
        )

        if target_score_raw is None:

            target_score_raw = (
                payload.score
            )


        if target_score_raw is None:

            return _error(
                "Missing Fancy target score."
            )


        payout_rate_raw = (
            payload.payout_rate
        )


        if payout_rate_raw is None:

            # Compatibility with your current
            # match.html which sends rate through
            # the odds field.
            payout_rate_raw = (
                payload.odds
            )


        target_score = _decimal(
            target_score_raw
        )

        payout_rate = _decimal(
            payout_rate_raw
        )


        if target_score < Decimal("0"):

            return _error(
                "Invalid Fancy target score."
            )


        if payout_rate <= Decimal("0"):

            return _error(
                "Invalid Fancy payout rate."
            )


        multiplier = _fancy_multiplier(
            payout_rate
        )


        potential_win = (
            _potential_return(
                stake,
                multiplier
            )
        )


        # -------------------------------------------------
        # IMPORTANT STORAGE DESIGN
        #
        # BetSelection.price stores the Fancy
        # TARGET SCORE.
        #
        # Bet.total_odds stores the COMPLETE
        # PAYOUT MULTIPLIER.
        #
        # Example:
        #
        # YES 40 / 100
        #
        # selection.price = 40
        # bet.total_odds = 2.00
        #
        # NO 43 / 90
        #
        # selection.price = 43
        # bet.total_odds = 1.90
        # -------------------------------------------------

        stored_selection_price = (
            target_score
        )

        stored_total_odds = (
            multiplier
        )


    # =====================================================
    # NORMAL MATCH / BOOKMAKER
    # =====================================================

    else:

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


        potential_win = (
            _potential_return(
                stake,
                odds
            )
        )


        stored_selection_price = (
            odds
        )

        stored_total_odds = (
            odds
        )


    # -----------------------------------------------------
    # BALANCE
    # -----------------------------------------------------

    current_balance = _decimal(
        user.balance,
        "0"
    ).quantize(
        Decimal("0.01")
    )


    if stake > current_balance:

        return _error(
            "Insufficient balance. "
            f"Available balance: "
            f"₹{current_balance:.2f}"
        )


    # -----------------------------------------------------
    # BET
    # -----------------------------------------------------

    bet = Bet(

        user_id=user.id,

        stake=float(
            stake
        ),

        total_odds=float(
            stored_total_odds
        ),

        potential_win=float(
            potential_win
        ),

        status="pending",
    )

    db.add(bet)

    db.flush()


    # -----------------------------------------------------
    # STORE MARKET TYPE IN MARKET NAME
    # -----------------------------------------------------

    if market_name:

        stored_market_name = (
            f"{market_type} | "
            f"{market_name}"
        )

    else:

        display_names = {

            "MATCH_ODDS":
                "Match Odds",

            "BOOKMAKER":
                "Bookmaker",

            "FANCY":
                "Fancy",

            "SESSION":
                "Session",
        }

        stored_market_name = (
            f"{market_type} | "
            f"{display_names.get(
                market_type,
                market_type
            )}"
        )


    # -----------------------------------------------------
    # BET SELECTION
    # -----------------------------------------------------

    selection = BetSelection(

        bet_id=bet.id,

        market_id=market_id,

        event_id=event_id,

        selection_id=selection_id,

        runner_name=selection_name,

        side=side,

        price=float(
            stored_selection_price
        ),

        market_name=stored_market_name,

        event_name=None,
    )

    db.add(selection)


    # -----------------------------------------------------
    # DEDUCT STAKE
    # -----------------------------------------------------

    new_balance = (
        current_balance -
        stake
    ).quantize(
        Decimal("0.01")
    )

    user.balance = float(
        new_balance
    )


    # -----------------------------------------------------
    # SYNC WALLET
    # -----------------------------------------------------

    wallet = (
        db.query(Wallet)
        .filter(
            Wallet.user_id == user.id
        )
        .first()
    )


    if wallet is not None:

        wallet.balance = float(
            new_balance
        )


    # -----------------------------------------------------
    # TRANSACTION
    # -----------------------------------------------------

    if is_fancy:

        transaction_description = (

            f"{market_type} | "
            f"{_display_side(market_type, side)} "
            f"{selection_name} | "
            f"target {target_score} | "
            f"rate {payout_rate}% | "
            f"stake ₹{stake:.2f}"
        )

    else:

        transaction_description = (

            f"{market_type} | "
            f"{side} "
            f"{selection_name} "
            f"@ {stored_total_odds} | "
            f"stake ₹{stake:.2f}"
        )


    transaction = Transaction(

        user_id=user.id,

        amount=-float(
            stake
        ),

        transaction_type="Bet",

        status="Completed",

        reference_type="Bet",

        reference_id=bet.id,

        description=transaction_description,
    )

    db.add(transaction)


    # -----------------------------------------------------
    # COMMIT
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    response = {

        "success":
            True,

        "message":
            "Bet placed successfully.",

        "bet_id":
            bet.id,

        "status":
            bet.status,

        "market_type":
            market_type,

        "market_name":
            market_name,

        "selection_id":
            selection_id,

        "selection_name":
            selection_name,

        "side":
            side,

        "display_side":
            _display_side(
                market_type,
                side
            ),

        "stake":
            float(
                stake
            ),

        "odds":
            float(
                stored_total_odds
            ),

        "potential_win":
            float(
                potential_win
            ),

        "balance":
            float(
                new_balance
            ),
    }


    if is_fancy:

        response.update({

            "target_score":
                float(
                    target_score
                ),

            "payout_rate":
                float(
                    payout_rate
                ),

            "potential_return":
                float(
                    potential_win
                ),
        })


    return response


# =========================================================
# FANCY RESULT HELPERS
# =========================================================

def _selection_market_type(
    selection: BetSelection,
) -> str:

    stored_market = str(
        selection.market_name or ""
    )


    if "|" in stored_market:

        return (
            stored_market
            .split("|", 1)[0]
            .strip()
            .upper()
        )


    return stored_market.strip().upper()


# =========================================================
# SETTLE ONE FANCY BET
#
# YES:
#   final_score >= target_score
#
# NO:
#   final_score < target_score
#
# This follows the rule you gave.
# =========================================================

def settle_one_fancy_bet(
    bet: Bet,
    selection: BetSelection,
    final_score: Decimal,
    db: Session,
) -> dict:

    market_type = _selection_market_type(
        selection
    )


    if market_type not in {
        "FANCY",
        "SESSION",
    }:

        return {
            "success": False,
            "message": "Not a Fancy/Session bet.",
        }


    side = str(
        selection.side or ""
    ).strip().upper()


    target_score = _decimal(
        selection.price
    )


    total_odds = _decimal(
        bet.total_odds
    )


    stake = _decimal(
        bet.stake
    )


    if target_score < Decimal("0"):

        return {
            "success": False,
            "message": "Invalid stored target score.",
        }


    if total_odds <= Decimal("1.00"):

        return {
            "success": False,
            "message": "Invalid stored payout multiplier.",
        }


    if bet.status != "pending":

        return {
            "success":
                True,

            "already_settled":
                True,

            "bet_id":
                bet.id,

            "status":
                bet.status,
        }


    final_score = _decimal(
        final_score
    )


    # -----------------------------------------------------
    # WIN LOGIC
    # -----------------------------------------------------

    if side == "BACK":
        # YES
        won = (
            final_score >=
            target_score
        )

    elif side == "LAY":
        # NO
        won = (
            final_score <
            target_score
        )

    else:

        return {
            "success": False,
            "message": "Invalid stored Fancy side.",
        }


    # -----------------------------------------------------
    # LOSS
    # -----------------------------------------------------

    if not won:

        bet.status = "lost"

        try:

            transaction = Transaction(

                user_id=bet.user_id,

                amount=0,

                transaction_type="Bet Loss",

                status="Completed",

                reference_type="Bet",

                reference_id=bet.id,

                description=(

                    f"{market_type} | "
                    f"{_display_side(market_type, side)} | "
                    f"target {target_score} | "
                    f"final score {final_score} | "
                    f"LOSS"
                ),
            )

            db.add(transaction)

            db.commit()

        except Exception:

            db.rollback()

            raise


        return {

            "success":
                True,

            "bet_id":
                bet.id,

            "status":
                "lost",

            "result":
                "LOSS",

            "final_score":
                float(
                    final_score
                ),

            "target_score":
                float(
                    target_score
                ),

            "credited":
                0.0,
        }


    # -----------------------------------------------------
    # WIN
    #
    # Credit the COMPLETE return:
    #
    # stake × multiplier
    #
    # Example:
    #
    # ₹100 × 2.00 = ₹200
    #
    # ₹100 × 1.90 = ₹190
    # -----------------------------------------------------

    payout = (
        stake *
        total_odds
    ).quantize(
        Decimal("0.01")
    )


    # -----------------------------------------------------
    # CURRENT BALANCE
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.id ==
            bet.user_id
        )
        .first()
    )


    if not user:

        return {
            "success": False,
            "message": "Bet user not found.",
        }


    current_balance = _decimal(
        user.balance
    ).quantize(
        Decimal("0.01")
    )


    # -----------------------------------------------------
    # CREDIT WALLET
    # -----------------------------------------------------

    new_balance = (
        current_balance +
        payout
    ).quantize(
        Decimal("0.01")
    )


    user.balance = float(
        new_balance
    )


    wallet = (
        db.query(Wallet)
        .filter(
            Wallet.user_id ==
            user.id
        )
        .first()
    )


    if wallet is not None:

        wallet.balance = float(
            new_balance
        )


    # -----------------------------------------------------
    # BET STATUS
    # -----------------------------------------------------

    bet.status = "won"


    # -----------------------------------------------------
    # WIN TRANSACTION
    # -----------------------------------------------------

    transaction = Transaction(

        user_id=user.id,

        amount=float(
            payout
        ),

        transaction_type="Bet Win",

        status="Completed",

        reference_type="Bet",

        reference_id=bet.id,

        description=(

            f"{market_type} | "
            f"{_display_side(market_type, side)} | "
            f"target {target_score} | "
            f"final score {final_score} | "
            f"WIN | "
            f"payout ₹{payout:.2f}"
        ),
    )

    db.add(transaction)


    # -----------------------------------------------------
    # COMMIT
    # -----------------------------------------------------

    try:

        db.commit()

        db.refresh(bet)

        db.refresh(user)

    except Exception as exc:

        db.rollback()

        raise RuntimeError(
            f"Could not settle bet: {exc}"
        ) from exc


    return {

        "success":
            True,

        "bet_id":
            bet.id,

        "status":
            "won",

        "result":
            "WIN",

        "final_score":
            float(
                final_score
            ),

        "target_score":
            float(
                target_score
            ),

        "stake":
            float(
                stake
            ),

        "multiplier":
            float(
                total_odds
            ),

        "credited":
            float(
                payout
            ),

        "balance":
            float(
                new_balance
            ),
    }


# =========================================================
# MANUAL / INTERNAL FANCY SETTLEMENT ENDPOINT
#
# This endpoint is useful for your settlement worker/admin
# until you connect automatic final-score polling.
#
# POST:
#
# /bets/settle-fancy/{bet_id}?final_score=42
# =========================================================

@router.post("/settle-fancy/{bet_id}")
async def settle_fancy_bet_endpoint(
    bet_id: int,
    final_score: float,
    request: Request,
    db: Session = Depends(get_db),
):

    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )

    employee_id = request.session.get(
        "employee_id"
    )

    admin_id = request.session.get(
        "admin_id"
    )


    if not (
        user_id or
        employee_id or
        admin_id
    ):

        return _error(
            "Login required.",
            401,
        )


    # -----------------------------------------------------
    # BET
    # -----------------------------------------------------

    bet = (
        db.query(Bet)
        .filter(
            Bet.id == bet_id
        )
        .first()
    )


    if not bet:

        return _error(
            "Bet not found.",
            404,
        )


    selection = (
        db.query(BetSelection)
        .filter(
            BetSelection.bet_id ==
            bet.id
        )
        .first()
    )


    if not selection:

        return _error(
            "Bet selection not found.",
            404,
        )


    market_type = _selection_market_type(
        selection
    )


    if market_type not in {
        "FANCY",
        "SESSION",
    }:

        return _error(
            "This bet is not a Fancy/Session bet."
        )


    try:

        score = _decimal(
            final_score
        )

        result = settle_one_fancy_bet(
            bet,
            selection,
            score,
            db,
        )

        return result

    except Exception as exc:

        db.rollback()

        return _error(
            f"Settlement failed: {exc}",
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


    bets = (
        db.query(Bet)
        .filter(
            Bet.user_id ==
            user_id
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


            is_fancy = (
                market_type
                in {
                    "FANCY",
                    "SESSION",
                }
            )


            selection_data = {

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

                "display_side":
                    _display_side(
                        market_type,
                        selection.side
                    ),

                "market_name":
                    display_market_name,

                "market_type":
                    market_type,

                "event_name":
                    selection.event_name,
            }


            if is_fancy:

                # selection.price stores
                # Fancy target score.

                target_score = _decimal(
                    selection.price
                )


                # bet.total_odds stores
                # full multiplier.
                #
                # 2.00 => 100%
                # 1.90 => 90%

                multiplier = _decimal(
                    bet.total_odds
                )


                payout_rate = (
                    (
                        multiplier -
                        Decimal("1.00")
                    )
                    *
                    Decimal("100.00")
                )


                selection_data.update({

                    "target_score":
                        float(
                            target_score
                        ),

                    "payout_rate":
                        float(
                            payout_rate
                        ),

                    "price":
                        float(
                            target_score
                        ),

                    "odds":
                        float(
                            multiplier
                        ),
                })


            else:

                selection_data.update({

                    "price":
                        float(
                            selection.price
                        ),

                    "odds":
                        float(
                            selection.price
                        ),
                })


            selections.append(
                selection_data
            )


        result.append({

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
        })


    return {

        "success":
            True,

        "bets":
            result,
    }

