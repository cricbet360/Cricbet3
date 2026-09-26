import time
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from database.database import SessionLocal

from models.bet import Bet
from models.bet_selection import BetSelection
from models.user import User
from models.wallet import Wallet
from models.transaction import Transaction

from services import proexch_api


# =========================================================
# CONFIG
# =========================================================

SETTLEMENT_INTERVAL = 15

FINAL_STATUSES = {
    "won",
    "lost",
    "void",
    "cancelled",
}


# =========================================================
# BASIC HELPERS
# =========================================================

def _decimal(
    value: Any,
) -> Decimal:

    try:

        return Decimal(
            str(
                value
                if value is not None
                else 0
            )
        )

    except Exception:

        return Decimal("0")


def _lower(
    value: Any,
) -> str:

    return str(
        value or ""
    ).strip().lower()


def _is_empty(
    value: Any,
) -> bool:

    return value in (
        None,
        "",
        [],
        {},
    )


# =========================================================
# PROEXCH RESULT EXTRACTION
# =========================================================

def _extract_result(
    response: Any,
) -> Any:
    """
    Normalize ProExch betfair-result responses.

    ProExch example:

    {
        "statusCode": 200,
        "data": {
            "data": [
                {
                    "id": "1.262910236",
                    "result": "88732107"
                }
            ]
        }
    }

    Our proexch_api wrapper returns:

    {
        "success": True,
        "market_id": "...",
        "type": "...",
        "result": <raw response>,
        "raw": <raw response>
    }

    This function safely unwraps both layers.
    """

    if response is None:

        return None

    # -----------------------------------------------------
    # First unwrap our proexch_api normalized response.
    # -----------------------------------------------------

    if isinstance(
        response,
        dict,
    ):

        wrapped_result = response.get(
            "result"
        )

        if (
            wrapped_result is not None
            and wrapped_result is not response
        ):

            response = wrapped_result

    # -----------------------------------------------------
    # Primitive provider result.
    # -----------------------------------------------------

    if not isinstance(
        response,
        dict,
    ):

        return response

    # -----------------------------------------------------
    # Direct result.
    # -----------------------------------------------------

    direct_result = response.get(
        "result"
    )

    if direct_result is not None:

        return direct_result

    # -----------------------------------------------------
    # ProExch nested structure:
    #
    # data -> data -> list -> item -> result
    # -----------------------------------------------------

    data = response.get(
        "data"
    )

    if isinstance(
        data,
        dict,
    ):

        nested_data = data.get(
            "data"
        )

        if isinstance(
            nested_data,
            list,
        ):

            for item in nested_data:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                item_result = item.get(
                    "result"
                )

                if not _is_empty(
                    item_result
                ):

                    return item_result

            # Explicit null result means no result yet.
            return None

        nested_result = data.get(
            "result"
        )

        if not _is_empty(
            nested_result
        ):

            return nested_result

    # -----------------------------------------------------
    # Direct data list.
    # -----------------------------------------------------

    if isinstance(
        data,
        list,
    ):

        for item in data:

            if not isinstance(
                item,
                dict,
            ):
                continue

            item_result = item.get(
                "result"
            )

            if not _is_empty(
                item_result
            ):

                return item_result

        return None

    return None


def _result_is_final(
    result: Any,
) -> bool:
    """
    True only when an actual final result exists.

    null/empty/pending/open results are never final.
    """

    if result is None:

        return False

    # -----------------------------------------------------
    # Primitive result.
    # -----------------------------------------------------

    if isinstance(
        result,
        (str, int, float),
    ):

        value = _lower(
            result
        )

        if not value:

            return False

        if value in {
            "null",
            "none",
            "pending",
            "open",
            "running",
            "inplay",
            "in_play",
            "live",
            "suspended",
            "waiting",
        }:

            return False

        return True

    # -----------------------------------------------------
    # Dictionary result.
    # -----------------------------------------------------

    if isinstance(
        result,
        dict,
    ):

        # Explicit non-final statuses.
        for key in (
            "status",
            "resultStatus",
            "marketStatus",
            "state",
        ):

            value = _lower(
                result.get(key)
            )

            if value in {
                "pending",
                "open",
                "running",
                "inplay",
                "in_play",
                "live",
                "suspended",
                "waiting",
            }:

                return False

        # Explicit final statuses.
        for key in (
            "status",
            "resultStatus",
            "marketStatus",
            "state",
        ):

            value = _lower(
                result.get(key)
            )

            if value in {
                "closed",
                "settled",
                "settledl",
                "complete",
                "completed",
                "final",
                "finished",
                "result",
                "won",
                "lost",
                "void",
            }:

                return True

        # Actual result/winner field.
        for key in (
            "winner",
            "winningRunner",
            "winningSelection",
            "winnerName",
            "winningRunnerName",
            "selectionId",
            "selection_id",
            "runnerId",
            "runner_id",
            "result",
            "settledResult",
            "finalResult",
        ):

            if not _is_empty(
                result.get(key)
            ):

                return True

        return False

    return False


# =========================================================
# WINNER EXTRACTION
# =========================================================

def _extract_winner(
    result: Any,
) -> str | None:
    """
    Extract winner/selection information.

    For Match Odds, ProExch may return a selection ID,
    runner name, or a nested object.
    """

    if result is None:

        return None

    # -----------------------------------------------------
    # Primitive result.
    #
    # Example:
    # "88732107"
    #
    # This is useful for Match Odds.
    # -----------------------------------------------------

    if isinstance(
        result,
        (str, int, float),
    ):

        value = str(
            result
        ).strip()

        return value or None

    if not isinstance(
        result,
        dict,
    ):

        return None

    for key in (
        "winner",
        "winningRunner",
        "winningSelection",
        "winnerName",
        "winningRunnerName",
        "selectionId",
        "selection_id",
        "runnerId",
        "runner_id",
        "result",
        "settledResult",
        "finalResult",
    ):

        value = result.get(
            key
        )

        if _is_empty(
            value
        ):
            continue

        # Nested winner object.
        if isinstance(
            value,
            dict,
        ):

            for nested_key in (
                "name",
                "runnerName",
                "runner_name",
                "selectionName",
                "selection_name",
                "winner",
                "id",
                "selectionId",
                "selection_id",
                "runnerId",
                "runner_id",
            ):

                nested = value.get(
                    nested_key
                )

                if not _is_empty(
                    nested
                ):

                    return str(
                        nested
                    ).strip()

        # Single-item list.
        elif isinstance(
            value,
            list,
        ):

            if len(value) == 1:

                item = value[0]

                if isinstance(
                    item,
                    dict,
                ):

                    for nested_key in (
                        "name",
                        "runnerName",
                        "selectionName",
                        "id",
                        "selectionId",
                    ):

                        nested = item.get(
                            nested_key
                        )

                        if not _is_empty(
                            nested
                        ):

                            return str(
                                nested
                            ).strip()

                else:

                    return str(
                        item
                    ).strip()

        else:

            return str(
                value
            ).strip()

    return None


# =========================================================
# NUMERIC RESULT
# =========================================================

def _extract_numeric_result(
    result: Any,
) -> Decimal | None:
    """
    Convert a Fancy result into a number.

    Supports:

        151
        "151"
        {"result": "151"}
        {"value": 151}
    """

    if isinstance(
        result,
        (int, float),
    ):

        return _decimal(
            result
        )

    if isinstance(
        result,
        str,
    ):

        cleaned = (
            result
            .strip()
            .replace(
                ",",
                "",
            )
        )

        if not cleaned:

            return None

        try:

            return Decimal(
                cleaned
            )

        except Exception:

            return None

    if not isinstance(
        result,
        dict,
    ):

        return None

    for key in (
        "result",
        "score",
        "runs",
        "value",
        "resultValue",
        "settledResult",
        "finalResult",
        "number",
    ):

        value = result.get(
            key
        )

        if value is None:

            continue

        parsed = _extract_numeric_result(
            value
        )

        if parsed is not None:

            return parsed

    return None


# =========================================================
# FANCY SETTLEMENT
# =========================================================

def _fancy_selection_wins(
    selection: BetSelection,
    result: Any,
) -> bool | None:
    """
    Returns:

        True  = won
        False = lost
        None  = cannot safely determine

    Fancy rules:

        BACK/YES:
            final result >= line -> WIN

        LAY/NO:
            final result < line -> WIN
    """

    if result is None:

        return None

    # -----------------------------------------------------
    # Explicit YES / NO / winner handling.
    # -----------------------------------------------------

    winner = _extract_winner(
        result
    )

    if winner:

        winner_normalized = _lower(
            winner
        )

        selection_id = _lower(
            selection.selection_id
        )

        runner_name = _lower(
            selection.runner_name
        )

        # Direct selection / runner match.
        if (
            winner_normalized == selection_id
            or winner_normalized == runner_name
        ):

            return True

        # YES / BACK.
        if winner_normalized in {
            "yes",
            "y",
            "back",
        }:

            return (
                _lower(
                    selection.side
                )
                == "back"
            )

        # NO / LAY.
        if winner_normalized in {
            "no",
            "n",
            "lay",
        }:

            return (
                _lower(
                    selection.side
                )
                == "lay"
            )

        # If it looks like a numeric result, continue below.
        try:

            Decimal(
                winner_normalized
            )

        except Exception:

            pass

        else:

            # Numeric result is handled below.
            pass

    # -----------------------------------------------------
    # Numeric Fancy result.
    # -----------------------------------------------------

    final_value = _extract_numeric_result(
        result
    )

    if final_value is None:

        return None

    line = _decimal(
        selection.price
    )

    side = _lower(
        selection.side
    )

    if side == "back":

        return (
            final_value
            >= line
        )

    if side == "lay":

        return (
            final_value
            < line
        )

    return None


# =========================================================
# MATCH ODDS SETTLEMENT
# =========================================================

def _match_odds_selection_wins(
    selection: BetSelection,
    result: Any,
) -> bool | None:
    """
    Determine Match Odds winner.

    ProExch result is expected to identify the winning
    selection by selection ID or runner name.

    Example:

        result = "88732107"

    and:

        selection.selection_id = "88732107"

    BACK:
        selected runner won -> True
        selected runner lost -> False

    LAY:
        selected runner lost -> True
        selected runner won -> False

    If the provider result cannot be matched safely,
    return None rather than incorrectly settling the bet.
    """

    winner = _extract_winner(
        result
    )

    if winner is None:

        return None

    winner_normalized = _lower(
        winner
    )

    selection_id = _lower(
        selection.selection_id
    )

    runner_name = _lower(
        selection.runner_name
    )

    # -----------------------------------------------------
    # Exact winner match.
    # -----------------------------------------------------

    selected_winner = False

    if (
        selection_id
        and winner_normalized == selection_id
    ):

        selected_winner = True

    elif (
        runner_name
        and winner_normalized == runner_name
    ):

        selected_winner = True

    else:

        # -------------------------------------------------
        # If the result is numeric but doesn't equal the
        # selection ID, do not guess.
        # -------------------------------------------------

        return None

    side = _lower(
        selection.side
    )

    if side == "back":

        return selected_winner

    if side == "lay":

        return not selected_winner

    return None


# =========================================================
# DETECT MARKET TYPE
# =========================================================

def _get_market_category(
    selection: BetSelection,
) -> str:
    """
    Return:

        fancy
        match_odds
        bookmaker
        unsupported
    """

    market_name = _lower(
        getattr(
            selection,
            "market_name",
            "",
        )
    )

    market_type = _lower(
        getattr(
            selection,
            "market_type",
            "",
        )
    )

    # -----------------------------------------------------
    # Fancy.
    # -----------------------------------------------------

    if (
        "fancy" in market_name
        or "session" in market_name
        or "fancy" in market_type
        or "session" in market_type
        or market_type in {
            "new_fancy",
        }
    ):

        return "fancy"

    # -----------------------------------------------------
    # Match Odds.
    # -----------------------------------------------------

    if (
        market_type in {
            "match_odds",
            "match odds",
            "match-odds",
        }
        or market_name in {
            "match odds",
            "match_odds",
            "match-odds",
        }
        or "match odds" in market_name
    ):

        return "match_odds"

    # -----------------------------------------------------
    # Bookmaker.
    #
    # Keep it separate rather than guessing a provider
    # result format.
    # -----------------------------------------------------

    if (
        "bookmaker" in market_name
        or "bookmaker" in market_type
        or market_type in {
            "book_maker",
            "bookmaker",
            "bookmaker_odds",
        }
    ):

        return "bookmaker"

    return "unsupported"


# =========================================================
# SETTLE ONE BET
# =========================================================

def settle_bet(
    db: Session,
    bet: Bet,
) -> bool:
    """
    Attempt to settle one pending bet.

    Returns:

        True  = bet state changed
        False = still pending / not processed
    """

    # -----------------------------------------------------
    # Never process final bets.
    # -----------------------------------------------------

    if _lower(
        bet.status
    ) in FINAL_STATUSES:

        return False

    selections = list(
        bet.selections
    )

    if not selections:

        print(
            "[SETTLEMENT] Bet has no selection:",
            bet.id,
        )

        return False

    # Current betting flow uses one selection per bet.
    selection = selections[0]

    market_category = _get_market_category(
        selection
    )

    # -----------------------------------------------------
    # Unsupported market.
    # -----------------------------------------------------

    if market_category == "unsupported":

        print(
            "[SETTLEMENT] Unsupported market type:",
            bet.id,
            getattr(
                selection,
                "market_name",
                "",
            ),
            getattr(
                selection,
                "market_type",
                "",
            ),
        )

        return False

    # -----------------------------------------------------
    # Select ProExch result type.
    # -----------------------------------------------------

    if market_category == "fancy":

        result_type = "new_fancy"

    elif market_category == "match_odds":

        result_type = "match_odds"

    elif market_category == "bookmaker":

        # We deliberately don't guess the provider result
        # parameter for bookmaker markets.
        print(
            "[SETTLEMENT] Bookmaker settlement not mapped:",
            bet.id,
            selection.market_id,
        )

        return False

    else:

        return False

    # -----------------------------------------------------
    # Get provider result.
    # -----------------------------------------------------

    response = (
        proexch_api
        .get_proexch_betfair_result(
            market_id=selection.market_id,
            result_type=result_type,
        )
    )

    if not isinstance(
        response,
        dict,
    ):

        return False

    if not response.get(
        "success"
    ):

        print(
            "[SETTLEMENT] Provider request failed:",
            bet.id,
            selection.market_id,
            response.get(
                "message"
            ),
        )

        return False

    # -----------------------------------------------------
    # Extract actual result.
    # -----------------------------------------------------

    result = _extract_result(
        response
    )

    # -----------------------------------------------------
    # ProExch has no result yet.
    #
    # IMPORTANT:
    # Empty odds are NOT treated as a loss.
    # result=null stays pending.
    # -----------------------------------------------------

    if not _result_is_final(
        result
    ):

        return False

    # -----------------------------------------------------
    # VOID handling.
    # -----------------------------------------------------

    normalized_result = _lower(
        result
    )

    if normalized_result in {
        "void",
        "cancelled",
        "canceled",
        "abandoned",
        "no result",
        "no_result",
        "nr",
        "n/r",
    }:

        # Refund stake once.
        existing_void_transaction = (
            db.query(Transaction)
            .filter(
                Transaction.reference_type == "Bet",
                Transaction.reference_id == bet.id,
                Transaction.transaction_type == "Bet Void",
                Transaction.status == "Completed",
            )
            .first()
        )

        if existing_void_transaction:

            if _lower(
                bet.status
            ) != "void":

                bet.status = "void"

                db.commit()

            return True

        stake = _decimal(
            bet.stake
        ).quantize(
            Decimal("0.01")
        )

        user = (
            db.query(User)
            .filter(
                User.id == bet.user_id
            )
            .first()
        )

        if not user:

            return False

        current_balance = _decimal(
            user.balance
        )

        new_balance = (
            current_balance
            + stake
        ).quantize(
            Decimal("0.01")
        )

        user.balance = float(
            new_balance
        )

        wallet = (
            db.query(Wallet)
            .filter(
                Wallet.user_id == user.id
            )
            .first()
        )

        if wallet:

            wallet.balance = float(
                new_balance
            )

        transaction = Transaction(
            user_id=user.id,
            amount=stake,
            transaction_type="Bet Void",
            status="Completed",
            reference_type="Bet",
            reference_id=bet.id,
            description=(
                f"Bet #{bet.id} void | "
                f"Stake refunded ₹{stake:.2f}"
            ),
        )

        db.add(
            transaction
        )

        bet.status = "void"

        db.commit()

        print(
            "[SETTLEMENT] VOID:",
            bet.id,
            "refund=",
            stake,
        )

        return True

    # -----------------------------------------------------
    # Determine WIN / LOSS.
    # -----------------------------------------------------

    if market_category == "fancy":

        won = _fancy_selection_wins(
            selection,
            result,
        )

    elif market_category == "match_odds":

        won = _match_odds_selection_wins(
            selection,
            result,
        )

    else:

        won = None

    # -----------------------------------------------------
    # Cannot safely determine winner.
    # Keep pending.
    # -----------------------------------------------------

    if won is None:

        print(
            "[SETTLEMENT] Could not determine result:",
            bet.id,
            "market=",
            selection.market_id,
            "type=",
            result_type,
            "selection_id=",
            selection.selection_id,
            "runner=",
            selection.runner_name,
            "result=",
            result,
        )

        return False

    # -----------------------------------------------------
    # Load user.
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.id == bet.user_id
        )
        .first()
    )

    if not user:

        print(
            "[SETTLEMENT] User not found:",
            bet.id,
            bet.user_id,
        )

        return False

    # =====================================================
    # WIN
    # =====================================================

    if won:

        # -------------------------------------------------
        # Prevent duplicate win transaction.
        # -------------------------------------------------

        existing_transaction = (
            db.query(Transaction)
            .filter(
                Transaction.reference_type == "Bet",
                Transaction.reference_id == bet.id,
                Transaction.transaction_type == "Bet Win",
                Transaction.status == "Completed",
            )
            .first()
        )

        if existing_transaction:

            if _lower(
                bet.status
            ) != "won":

                bet.status = "won"

                db.commit()

            print(
                "[SETTLEMENT] Existing win transaction:",
                bet.id,
            )

            return True

        # -------------------------------------------------
        # potential_win is the total return.
        #
        # Example:
        # stake = 100
        # odds = 2.14
        # return = 214
        # -------------------------------------------------

        payout = _decimal(
            bet.potential_win
        ).quantize(
            Decimal("0.01")
        )

        current_balance = _decimal(
            user.balance
        )

        new_balance = (
            current_balance
            + payout
        ).quantize(
            Decimal("0.01")
        )

        user.balance = float(
            new_balance
        )

        wallet = (
            db.query(Wallet)
            .filter(
                Wallet.user_id == user.id
            )
            .first()
        )

        if wallet:

            wallet.balance = float(
                new_balance
            )

        transaction = Transaction(
            user_id=user.id,
            amount=payout,
            transaction_type="Bet Win",
            status="Completed",
            reference_type="Bet",
            reference_id=bet.id,
            description=(
                f"Bet #{bet.id} won | "
                f"Return ₹{payout:.2f}"
            ),
        )

        db.add(
            transaction
        )

        bet.status = "won"

        db.commit()

        print(
            "[SETTLEMENT] WON:",
            bet.id,
            "market=",
            selection.market_id,
            "result=",
            result,
            "payout=",
            payout,
        )

        return True

    # =====================================================
    # LOSS
    # =====================================================

    bet.status = "lost"

    db.commit()

    print(
        "[SETTLEMENT] LOST:",
        bet.id,
        "market=",
        selection.market_id,
        "result=",
        result,
    )

    return True


# =========================================================
# SETTLE ALL PENDING BETS
# =========================================================

def settle_pending_bets():
    db = SessionLocal()

    try:

        bets = (
            db.query(Bet)
            .filter(
                Bet.status == "pending"
            )
            .order_by(
                Bet.created_at.asc()
            )
            .all()
        )

        for bet in bets:

            try:

                settle_bet(
                    db,
                    bet,
                )

            except Exception as exc:

                db.rollback()

                print(
                    "[SETTLEMENT] Bet error:",
                    bet.id,
                    repr(exc),
                )

    finally:

        db.close()


# =========================================================
# BACKGROUND LOOP
# =========================================================

def settlement_loop():

    print(
        "[SETTLEMENT] Worker started."
    )

    while True:

        try:

            settle_pending_bets()

        except Exception as exc:

            print(
                "[SETTLEMENT] Worker error:",
                repr(exc),
            )

        time.sleep(
            SETTLEMENT_INTERVAL
        )