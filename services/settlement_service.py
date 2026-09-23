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
# HELPERS
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


def _extract_result(
    response: Any,
) -> Any:
    """
    Extract the provider result while preserving
    the original response if its structure is unknown.
    """

    if not isinstance(
        response,
        dict,
    ):
        return response

    result = response.get(
        "result"
    )

    if result is not None:

        return result

    data = response.get(
        "data"
    )

    if isinstance(
        data,
        dict,
    ):

        nested = data.get(
            "result"
        )

        if nested is not None:

            return nested

    return data or response


def _result_is_final(
    result: Any,
) -> bool:

    if not isinstance(
        result,
        dict,
    ):
        return False

    # Common final/status fields.
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
            "result",
            "won",
            "lost",
        }:

            return True

    # Provider may return a result directly.
    for key in (
        "winner",
        "winningRunner",
        "winningSelection",
        "result",
        "settledResult",
        "finalResult",
    ):

        if result.get(key) not in (
            None,
            "",
            [],
            {},
        ):

            return True

    return False


def _extract_winner(
    result: Any,
) -> str | None:

    if not isinstance(
        result,
        dict,
    ):
        return None

    # Common winner fields.
    for key in (
        "winner",
        "winningRunner",
        "winningSelection",
        "winnerName",
        "winningRunnerName",
        "result",
        "settledResult",
        "finalResult",
    ):

        value = result.get(key)

        if value not in (
            None,
            "",
            [],
            {},
        ):

            if isinstance(
                value,
                dict,
            ):

                for nested_key in (
                    "name",
                    "runnerName",
                    "selectionName",
                    "winner",
                    "id",
                    "selectionId",
                ):

                    nested = value.get(
                        nested_key
                    )

                    if nested not in (
                        None,
                        "",
                    ):

                        return str(
                            nested
                        ).strip()

            elif isinstance(
                value,
                list,
            ):

                if len(value) == 1:

                    return str(
                        value[0]
                    ).strip()

            else:

                return str(
                    value
                ).strip()

    return None


def _extract_numeric_result(
    result: Any,
) -> Decimal | None:

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

        value = result.get(key)

        try:

            if isinstance(
                value,
                (int, float),
            ):

                return _decimal(
                    value
                )

            if isinstance(
                value,
                str,
            ):

                cleaned = (
                    value
                    .strip()
                    .replace(
                        ",",
                        "",
                    )
                )

                if cleaned:

                    return Decimal(
                        cleaned
                    )

        except Exception:

            continue

    return None


def _fancy_selection_wins(
    selection: BetSelection,
    result: Any,
) -> bool | None:
    """
    Returns:

        True  = bet won
        False = bet lost
        None  = cannot safely determine yet
    """

    if not isinstance(
        result,
        (dict, list, str, int, float),
    ):

        return None

    # -----------------------------------------------------
    # First try explicit winner/selection result.
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

        if (
            winner_normalized
            == selection_id
            or winner_normalized
            == runner_name
        ):

            return True

        # YES / NO result.
        if winner_normalized in {
            "yes",
            "y",
            "back",
        }:

            return (
                selection.side
                == "BACK"
            )

        if winner_normalized in {
            "no",
            "n",
            "lay",
        }:

            return (
                selection.side
                == "LAY"
            )

    # -----------------------------------------------------
    # Numeric Fancy result.
    #
    # Example:
    #
    # line = 26
    # final result = 30
    #
    # YES/BACK wins when result >= line.
    # NO/LAY wins when result < line.
    # -----------------------------------------------------

    final_value = (
        _extract_numeric_result(
            result
        )
    )

    if final_value is not None:

        line = _decimal(
            selection.price
        )

        if (
            selection.side
            == "BACK"
        ):

            return (
                final_value
                >= line
            )

        if (
            selection.side
            == "LAY"
        ):

            return (
                final_value
                < line
            )

    return None


# =========================================================
# SETTLE ONE BET
# =========================================================

def settle_bet(
    db: Session,
    bet: Bet,
) -> bool:

    if _lower(
        bet.status
    ) in FINAL_STATUSES:

        return False

    selections = list(
        bet.selections
    )

    if not selections:

        return False

    # -----------------------------------------------------
    # Current implementation supports one selection per bet.
    # -----------------------------------------------------

    selection = selections[0]

    market_name = _lower(
        selection.market_name
    )

    is_fancy = (
        "fancy" in market_name
        or "session" in market_name
    )

    if not is_fancy:

        # Match odds/bookmaker settlement needs their
        # specific provider result mapping.
        return False

    # -----------------------------------------------------
    # ProExch Betfair result
    # -----------------------------------------------------

    response = (
        proexch_api
        .get_proexch_betfair_result(
            market_id=selection.market_id,
            result_type="new_fancy",
        )
    )

    if not response.get(
        "success"
    ):

        return False

    result = _extract_result(
        response
    )

    if not _result_is_final(
        result
    ):

        return False

    won = _fancy_selection_wins(
        selection,
        result,
    )

    if won is None:

        print(
            "[SETTLEMENT] Could not determine result",
            bet.id,
            selection.market_id,
            result,
        )

        return False

    user = (
        db.query(User)
        .filter(
            User.id == bet.user_id
        )
        .first()
    )

    if not user:

        return False

    # -----------------------------------------------------
    # WIN
    # -----------------------------------------------------

    if won:

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
                Wallet.user_id
                == user.id
            )
            .first()
        )

        if wallet:

            wallet.balance = new_balance

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

        print(
            "[SETTLEMENT] WON",
            bet.id,
            payout,
        )

    # -----------------------------------------------------
    # LOSS
    # -----------------------------------------------------

    else:

        bet.status = "lost"

        print(
            "[SETTLEMENT] LOST",
            bet.id,
        )

    db.commit()

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
                    "[SETTLEMENT] Bet error",
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