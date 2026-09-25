import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session

from database.database import get_db
from models.bet import Bet
from models.bet_selection import BetSelection
from models.transaction import Transaction
from models.user import User

from services import proexch_api


# =========================================================
# CONFIGURATION
# =========================================================

# ProExch result endpoint currently confirmed for Fancy/Session:
# /api/betfair-result?sport=cricket&type=new_fancy&marketId=...
#
# For an exact Fancy result, the provider-specific rule was not
# included in the response you supplied. We therefore use VOID
# for an exact line match rather than guessing a win or loss.
#
# Example:
#   line = 151
#   result = 151
#   => VOID / stake returned
#
FANCY_EQUAL_ACTION = "void"


# =========================================================
# BASIC HELPERS
# =========================================================

def _clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    try:
        text = str(value).strip()

        if not text:
            return None

        return float(text)

    except (TypeError, ValueError):
        return None


def _to_decimal(value: Any) -> Optional[Decimal]:
    try:
        if value is None:
            return None

        return Decimal(str(value))

    except (InvalidOperation, TypeError, ValueError):
        return None


# =========================================================
# MARKET TYPE
# =========================================================

def _detect_market_type(selection: BetSelection) -> str:
    """
    Works with your CURRENT BetSelection model.

    It does not require a market_type database column.

    If you later add market_type, it will use that first.
    """

    stored_market_type = _clean(
        getattr(selection, "market_type", "")
    ).upper()

    if stored_market_type:
        return stored_market_type

    market_name = _clean(
        getattr(selection, "market_name", "")
    ).upper()

    if "SESSION" in market_name:
        return "SESSION"

    if "FANCY" in market_name:
        return "FANCY"

    if "BOOKMAKER" in market_name:
        return "BOOKMAKER"

    if "MATCH ODDS" in market_name:
        return "MATCH_ODDS"

    # Current Fancy rows are numeric, for example:
    # selection/runner name = "151"
    #
    # Their market ID has the form:
    # 36074941_55
    #
    # That is a useful fallback for your current schema.
    runner_name = _clean(
        getattr(selection, "runner_name", "")
    )

    market_id = _clean(
        getattr(selection, "market_id", "")
    )

    if "_" in market_id:
        if _extract_line(runner_name) is not None:
            return "FANCY"

    return "MATCH_ODDS"


# =========================================================
# EXTRACT PROVIDER RESULT ROWS
# =========================================================

def _extract_result_rows(payload: Any) -> list[dict[str, Any]]:
    """
    Handles the confirmed ProExch response:

    {
        "statusCode": 200,
        "data": {
            "data": [
                {
                    "id": "36074941_55",
                    "result": "151"
                }
            ]
        }
    }
    """

    if not isinstance(payload, dict):
        return []

    current = payload

    # Our proexch_api wrapper returns:
    #
    # {
    #     "success": True,
    #     "result": raw_provider_response,
    #     ...
    # }
    #
    if isinstance(current.get("result"), dict):
        current = current["result"]

    # First provider layer
    data = current.get("data")

    if isinstance(data, dict):
        nested = data.get("data")

        if isinstance(nested, list):
            return [
                item
                for item in nested
                if isinstance(item, dict)
            ]

        if isinstance(nested, dict):
            return [nested]

        # Some provider responses may put a single
        # result object directly under data.
        if "result" in data or "id" in data:
            return [data]

    if isinstance(data, list):
        return [
            item
            for item in data
            if isinstance(item, dict)
        ]

    # Fallback
    if "result" in current or "id" in current:
        return [current]

    return []


# =========================================================
# GET PROVIDER RESULT VALUE
# =========================================================

def _get_result_value(
    selection: BetSelection,
    result_type: str,
) -> Optional[str]:
    market_id = _clean(
        getattr(selection, "market_id", "")
    )

    if not market_id:
        return None

    response = proexch_api.get_proexch_betfair_result(
        market_id=market_id,
        result_type=result_type,
    )

    if not response or not response.get("success"):
        return None

    rows = _extract_result_rows(response)

    if not rows:
        return None

    for row in rows:

        row_id = _clean(
            row.get("id")
        )

        # Make sure we are using the result for the
        # exact market we are settling.
        if row_id and row_id != market_id:
            continue

        result = row.get("result")

        if result is None:
            continue

        result_text = _clean(result)

        if not result_text:
            continue

        # These mean there is not a final settlement yet.
        if result_text.upper() in {
            "-",
            "PENDING",
            "OPEN",
            "SUSPENDED",
            "UNAVAILABLE",
            "NULL",
            "NONE",
        }:
            return None

        return result_text

    return None


# =========================================================
# EXTRACT FANCY LINE
# =========================================================

def _extract_line(text: Any) -> Optional[float]:
    """
    Examples accepted:

        "151"
        "151.5"
        "Over 151 Runs"
        "Team A 151"

    We prefer the last numeric value in the runner name.
    """

    value = _clean(text)

    if not value:
        return None

    numbers = re.findall(
        r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)",
        value,
    )

    if not numbers:
        return None

    try:
        return float(numbers[-1])

    except (TypeError, ValueError):
        return None


# =========================================================
# FANCY SETTLEMENT
# =========================================================

def _settle_fancy(
    selection: BetSelection,
    result_text: str,
) -> Optional[str]:
    """
    Current UI mapping:

        BACK = YES
        LAY  = NO

    Example:

        line   = 151
        result = 154

        YES/BACK -> WIN
        NO/LAY   -> LOSS

    Example:

        line   = 151
        result = 149

        YES/BACK -> LOSS
        NO/LAY   -> WIN
    """

    result_value = _to_float(
        result_text
    )

    if result_value is None:
        return None

    runner_name = _clean(
        getattr(selection, "runner_name", "")
    )

    line = _extract_line(
        runner_name
    )

    # Fallback to market_name if runner_name does not
    # contain the actual line.
    if line is None:

        line = _extract_line(
            getattr(
                selection,
                "market_name",
                "",
            )
        )

    if line is None:
        print(
            "[SETTLEMENT] Could not determine Fancy line:",
            runner_name,
            getattr(selection, "market_id", ""),
        )

        return None

    side = _clean(
        getattr(selection, "side", "")
    ).upper()

    # -----------------------------------------------------
    # RESULT GREATER THAN LINE
    # -----------------------------------------------------

    if result_value > line:

        if side == "BACK":
            return "won"

        if side == "LAY":
            return "lost"

    # -----------------------------------------------------
    # RESULT LOWER THAN LINE
    # -----------------------------------------------------

    if result_value < line:

        if side == "BACK":
            return "lost"

        if side == "LAY":
            return "won"

    # -----------------------------------------------------
    # EXACT RESULT
    # -----------------------------------------------------

    if result_value == line:

        if FANCY_EQUAL_ACTION == "void":
            return "void"

    return None


# =========================================================
# STANDARD MARKET SETTLEMENT
# =========================================================

def _standard_result_matches_selection(
    selection: BetSelection,
    provider_result: str,
) -> Optional[str]:
    """
    Handles common ProExch-style result forms.

    The result may be:
      - selection ID
      - runner name
      - winner field represented as text

    We do not guess from scoreboards here.
    """

    result_text = _clean(
        provider_result
    )

    if not result_text:
        return None

    selection_id = _clean(
        getattr(selection, "selection_id", "")
    )

    runner_name = _clean(
        getattr(selection, "runner_name", "")
    )

    side = _clean(
        getattr(selection, "side", "")
    ).upper()

    # Exact selection ID
    if (
        selection_id
        and result_text == selection_id
    ):
        return "won"

    # Exact runner name
    if (
        runner_name
        and result_text.lower()
        == runner_name.lower()
    ):
        return "won"

    # If provider gives a result such as:
    #
    # "WINNER: 123"
    #
    # or a JSON-ish string, inspect whether the
    # user's selection ID/name is contained in it.
    lower_result = result_text.lower()

    if (
        selection_id
        and selection_id.lower()
        in lower_result
    ):
        return "won"

    if (
        runner_name
        and runner_name.lower()
        in lower_result
    ):
        return "won"

    # A final provider result was returned but it does
    # not match this runner.
    #
    # For a normal winner market, that means LOSS.
    if side in {"BACK", "LAY"}:
        return "lost"

    return None


# =========================================================
# SETTLE ONE BET
# =========================================================

def settle_one_bet(
    db: Session,
    bet: Bet,
) -> Optional[str]:
    """
    Returns:
        won
        lost
        void
        None = still pending / unable to settle
    """

    # Only pending bets may be settled.
    if _clean(
        bet.status
    ).lower() != "pending":
        return None

    selections = list(
        getattr(
            bet,
            "selections",
            [],
        )
        or []
    )

    if not selections:
        print(
            "[SETTLEMENT] Bet has no selection:",
            bet.id,
        )
        return None

    selection = selections[0]

    market_type = _detect_market_type(
        selection
    )

    # =====================================================
    # FANCY / SESSION
    # =====================================================

    if market_type in {
        "FANCY",
        "SESSION",
    }:

        provider_type = "new_fancy"

        result_text = _get_result_value(
            selection,
            provider_type,
        )

        if result_text is None:
            return None

        settlement = _settle_fancy(
            selection,
            result_text,
        )

        if settlement is None:
            return None

    # =====================================================
    # MATCH ODDS
    # =====================================================

    elif market_type == "MATCH_ODDS":

        result_text = _get_result_value(
            selection,
            "match_odds",
        )

        if result_text is None:
            return None

        settlement = (
            _standard_result_matches_selection(
                selection,
                result_text,
            )
        )

        if settlement is None:
            return None

    # =====================================================
    # BOOKMAKER
    # =====================================================

    elif market_type == "BOOKMAKER":

        result_text = _get_result_value(
            selection,
            "bookmaker",
        )

        if result_text is None:
            return None

        settlement = (
            _standard_result_matches_selection(
                selection,
                result_text,
            )
        )

        if settlement is None:
            return None

    else:

        print(
            "[SETTLEMENT] Unsupported market type:",
            market_type,
            "bet=",
            bet.id,
        )

        return None

    # =====================================================
    # IDEMPOTENCY
    # =====================================================

    existing_settlement = (
        db.query(Transaction)
        .filter(
            Transaction.reference_type
            == "bet_settlement",

            Transaction.reference_id
            == bet.id,
        )
        .first()
    )

    # If a settlement transaction already exists,
    # never pay this bet again.
    if existing_settlement:

        bet.status = settlement

        return settlement

    # =====================================================
    # LOAD USER
    # =====================================================

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
            bet.user_id,
        )

        return None

    stake = _to_decimal(
        bet.stake
    ) or Decimal("0")

    potential_win = _to_decimal(
        bet.potential_win
    ) or Decimal("0")

    current_balance = _to_decimal(
        user.balance
    ) or Decimal("0")

    # =====================================================
    # WIN
    # =====================================================

    if settlement == "won":

        # potential_win is the TOTAL return that was
        # calculated when the bet was placed.
        #
        # Example:
        # stake = 100
        # potential_win = 126
        #
        # 126 is credited, not 26.
        credit = potential_win

        new_balance = (
            current_balance
            + credit
        )

        user.balance = float(
            new_balance
        )

        transaction = Transaction(
            user_id=user.id,

            amount=float(
                credit
            ),

            transaction_type="Bet Win",

            status="Completed",

            reference_type="bet_settlement",

            reference_id=bet.id,

            description=(
                f"Bet #{bet.id} won. "
                f"Winning return credited."
            ),
        )

        db.add(transaction)

        bet.status = "won"

        print(
            "[SETTLEMENT] WON:",
            "bet=", bet.id,
            "user=", user.id,
            "credit=", float(credit),
            "balance=", float(new_balance),
        )

        return "won"

    # =====================================================
    # LOSS
    # =====================================================

    if settlement == "lost":

        # Stake was already deducted at placement.
        # Nothing is credited on loss.
        bet.status = "lost"

        transaction = Transaction(
            user_id=user.id,

            amount=0.0,

            transaction_type="Bet Loss",

            status="Completed",

            reference_type="bet_settlement",

            reference_id=bet.id,

            description=(
                f"Bet #{bet.id} lost."
            ),
        )

        db.add(transaction)

        print(
            "[SETTLEMENT] LOST:",
            "bet=", bet.id,
            "user=", user.id,
        )

        return "lost"

    # =====================================================
    # VOID
    # =====================================================

    if settlement == "void":

        # Return the original stake.
        new_balance = (
            current_balance
            + stake
        )

        user.balance = float(
            new_balance
        )

        transaction = Transaction(
            user_id=user.id,

            amount=float(
                stake
            ),

            transaction_type="Bet Void Refund",

            status="Completed",

            reference_type="bet_settlement",

            reference_id=bet.id,

            description=(
                f"Bet #{bet.id} voided. "
                f"Original stake returned."
            ),
        )

        db.add(transaction)

        bet.status = "void"

        print(
            "[SETTLEMENT] VOID:",
            "bet=", bet.id,
            "user=", user.id,
            "refund=", float(stake),
            "balance=", float(new_balance),
        )

        return "void"

    return None


# =========================================================
# SETTLE PENDING BETS
# =========================================================

def settle_pending_bets(
    db: Session,
    limit: int = 100,
) -> dict[str, int]:

    stats = {
        "checked": 0,
        "won": 0,
        "lost": 0,
        "void": 0,
        "pending": 0,
        "errors": 0,
    }

    pending_bets = (
        db.query(Bet)
        .filter(
            Bet.status == "pending"
        )
        .order_by(
            Bet.created_at.asc()
        )
        .limit(limit)
        .all()
    )

    for bet in pending_bets:

        stats["checked"] += 1

        try:

            result = settle_one_bet(
                db,
                bet,
            )

            if result == "won":
                stats["won"] += 1

            elif result == "lost":
                stats["lost"] += 1

            elif result == "void":
                stats["void"] += 1

            else:
                stats["pending"] += 1

        except Exception as exc:

            stats["errors"] += 1

            db.rollback()

            print(
                "[SETTLEMENT] Bet error:",
                bet.id,
                repr(exc),
            )

    try:

        db.commit()

    except Exception as exc:

        db.rollback()

        print(
            "[SETTLEMENT] Commit error:",
            repr(exc),
        )

        stats["errors"] += 1

    return stats


# =========================================================
# ONE WORKER CYCLE
# =========================================================

def run_settlement_cycle(
    limit: int = 100,
) -> dict[str, int]:

    generator = get_db()

    db = next(generator)

    try:

        return settle_pending_bets(
            db,
            limit=limit,
        )

    finally:

        try:
            next(generator)
        except StopIteration:
            pass


# =========================================================
# SIMPLE CONTINUOUS WORKER
# =========================================================

def settlement_worker_loop(
    interval_seconds: float = 5.0,
) -> None:

    import time

    print(
        "[SETTLEMENT] Worker started"
    )

    while True:

        try:

            stats = run_settlement_cycle()

            total_settled = (
                stats["won"]
                + stats["lost"]
                + stats["void"]
            )

            if (
                stats["checked"] > 0
                or stats["errors"] > 0
            ):

                print(
                    "[SETTLEMENT]",
                    stats,
                    "settled=",
                    total_settled,
                )

        except Exception as exc:

            print(
                "[SETTLEMENT] Worker error:",
                repr(exc),
            )

        time.sleep(
            interval_seconds
        )