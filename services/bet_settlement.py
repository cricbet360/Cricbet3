import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session

from database.database import get_db

from models.bet import Bet
from models.bet_selection import BetSelection
from models.transaction import Transaction
from models.user import User
from models.wallet import Wallet

from services import proexch_api


# =========================================================
# CONFIGURATION
# =========================================================

# Confirmed ProExch Fancy/Session result endpoint:
#
# /api/betfair-result?sport=cricket&type=new_fancy&marketId=...
#
# When the Fancy result exactly equals the selected line,
# we currently VOID the bet and return the original stake.
#
# Example:
#
# line   = 151
# result = 151
# result => VOID
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

def _detect_market_type(
    selection: BetSelection,
) -> str:
    """
    Detect the market type using the current BetSelection
    schema.

    Priority:
        1. stored market_type
        2. market_name
        3. current Fancy market-id / numeric-line fallback
        4. MATCH_ODDS
    """

    stored_market_type = _clean(
        getattr(
            selection,
            "market_type",
            "",
        )
    ).upper()

    # -----------------------------------------------------
    # Stored market type
    # -----------------------------------------------------

    if stored_market_type:
        aliases = {
            "MATCH": "MATCH_ODDS",
            "MATCHODDS": "MATCH_ODDS",
            "MATCH_ODD": "MATCH_ODDS",
            "MATCH ODDS": "MATCH_ODDS",
            "BOOK": "BOOKMAKER",
            "BOOKMAKER ODDS": "BOOKMAKER",
            "BOOKMAKER_ODDS": "BOOKMAKER",
            "FANCY ODDS": "FANCY",
            "FANCY_ODDS": "FANCY",
            "SESSION ODDS": "SESSION",
            "SESSION_ODDS": "SESSION",
        }

        return aliases.get(
            stored_market_type,
            stored_market_type,
        )

    # -----------------------------------------------------
    # Market name detection
    # -----------------------------------------------------

    market_name = _clean(
        getattr(
            selection,
            "market_name",
            "",
        )
    ).upper()

    if "SESSION" in market_name:
        return "SESSION"

    if "FANCY" in market_name:
        return "FANCY"

    if "BOOKMAKER" in market_name:
        return "BOOKMAKER"

    if "MATCH ODDS" in market_name:
        return "MATCH_ODDS"

    # -----------------------------------------------------
    # Fancy fallback
    # -----------------------------------------------------

    runner_name = _clean(
        getattr(
            selection,
            "runner_name",
            "",
        )
    )

    market_id = _clean(
        getattr(
            selection,
            "market_id",
            "",
        )
    )

    # Current ProExch Fancy IDs commonly look like:
    #
    # 36074941_55
    #
    # with a numeric runner/line such as:
    #
    # 151
    # 151.5
    #
    if "_" in market_id:
        if _extract_line(runner_name) is not None:
            return "FANCY"

    return "MATCH_ODDS"


# =========================================================
# EXTRACT PROVIDER RESULT ROWS
# =========================================================

def _extract_result_rows(
    payload: Any,
) -> list[dict[str, Any]]:
    """
    Handles the confirmed ProExch structure:

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

    Also handles the wrapper returned by
    proexch_api.get_proexch_betfair_result().
    """

    if not isinstance(payload, dict):
        return []

    current = payload

    # -----------------------------------------------------
    # Our service wrapper
    # -----------------------------------------------------

    if isinstance(
        current.get("result"),
        dict,
    ):
        current = current["result"]

    # -----------------------------------------------------
    # Provider data wrapper
    # -----------------------------------------------------

    data = current.get("data")

    if isinstance(data, dict):

        nested = data.get("data")

        if isinstance(
            nested,
            list,
        ):
            return [
                item
                for item in nested
                if isinstance(item, dict)
            ]

        if isinstance(
            nested,
            dict,
        ):
            return [nested]

        # Single result directly inside data
        if (
            "result" in data
            or "id" in data
            or "winner" in data
            or "winnerId" in data
        ):
            return [data]

    # -----------------------------------------------------
    # Data is already a list
    # -----------------------------------------------------

    if isinstance(
        data,
        list,
    ):
        return [
            item
            for item in data
            if isinstance(item, dict)
        ]

    # -----------------------------------------------------
    # Direct result object
    # -----------------------------------------------------

    if (
        "result" in current
        or "id" in current
        or "winner" in current
        or "winnerId" in current
    ):
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
        getattr(
            selection,
            "market_id",
            "",
        )
    )

    if not market_id:
        return None

    response = (
        proexch_api.get_proexch_betfair_result(
            market_id=market_id,
            result_type=result_type,
        )
    )

    if (
        not response
        or not response.get("success")
    ):
        return None

    rows = _extract_result_rows(
        response
    )

    if not rows:
        return None

    for row in rows:

        row_id = _clean(
            row.get("id")
        )

        # -------------------------------------------------
        # Exact market protection
        # -------------------------------------------------

        if (
            row_id
            and row_id != market_id
        ):
            continue

        # -------------------------------------------------
        # Normal result field
        # -------------------------------------------------

        result = row.get("result")

        # -------------------------------------------------
        # Additional possible provider fields
        # -------------------------------------------------

        if result is None:
            result = row.get(
                "winner"
            )

        if result is None:
            result = row.get(
                "winnerName"
            )

        if result is None:
            result = row.get(
                "winnerId"
            )

        if result is None:
            result = row.get(
                "selectionId"
            )

        if result is None:
            result = row.get(
                "selection_id"
            )

        if result is None:
            continue

        result_text = _clean(
            result
        )

        if not result_text:
            continue

        # -------------------------------------------------
        # Not settled yet
        # -------------------------------------------------

        if result_text.upper() in {
            "-",
            "PENDING",
            "OPEN",
            "SUSPENDED",
            "UNAVAILABLE",
            "NULL",
            "NONE",
            "WAITING",
            "PROCESSING",
        }:
            return None

        return result_text

    return None


# =========================================================
# EXTRACT FANCY LINE
# =========================================================

def _extract_line(
    text: Any,
) -> Optional[float]:
    """
    Accepted examples:

        151
        151.5
        Over 151 Runs
        Under 151.5 Runs
        Team A 151

    The last numeric value is used.
    """

    value = _clean(
        text
    )

    if not value:
        return None

    numbers = re.findall(
        r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)",
        value,
    )

    if not numbers:
        return None

    try:
        return float(
            numbers[-1]
        )

    except (
        TypeError,
        ValueError,
    ):
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

        BACK/YES -> WIN
        LAY/NO   -> LOSS

    Example:

        line   = 151
        result = 149

        BACK/YES -> LOSS
        LAY/NO   -> WIN
    """

    result_value = _to_float(
        result_text
    )

    if result_value is None:
        return None

    runner_name = _clean(
        getattr(
            selection,
            "runner_name",
            "",
        )
    )

    line = _extract_line(
        runner_name
    )

    # -----------------------------------------------------
    # Fallback market name
    # -----------------------------------------------------

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
            getattr(
                selection,
                "market_id",
                "",
            ),
        )

        return None

    side = _clean(
        getattr(
            selection,
            "side",
            "",
        )
    ).upper()

    # -----------------------------------------------------
    # Result greater than line
    # -----------------------------------------------------

    if result_value > line:

        if side == "BACK":
            return "won"

        if side == "LAY":
            return "lost"

    # -----------------------------------------------------
    # Result lower than line
    # -----------------------------------------------------

    if result_value < line:

        if side == "BACK":
            return "lost"

        if side == "LAY":
            return "won"

    # -----------------------------------------------------
    # Exact line
    # -----------------------------------------------------

    if result_value == line:

        if FANCY_EQUAL_ACTION == "void":
            return "void"

    return None


# =========================================================
# RESULT MATCH HELPER
# =========================================================

def _contains_numeric_identifier(
    result_text: str,
    identifier: str,
) -> bool:
    """
    Avoids false substring matches such as:

        selection_id = 12
        result       = 312

    """

    identifier = identifier.strip()

    if not identifier:
        return False

    if not identifier.isdigit():
        return (
            identifier.lower()
            in result_text.lower()
        )

    pattern = (
        r"(?<!\d)"
        + re.escape(identifier)
        + r"(?!\d)"
    )

    return re.search(
        pattern,
        result_text,
    ) is not None


# =========================================================
# STANDARD MARKET SETTLEMENT
# =========================================================

def _standard_result_matches_selection(
    selection: BetSelection,
    provider_result: str,
) -> Optional[str]:
    """
    Handles standard Match Odds / Bookmaker results.

    Provider result can commonly be:

        selection ID
        runner name
        winner ID embedded in text
        winner name embedded in text

    IMPORTANT:

        BACK:
            selected runner wins  -> WIN
            selected runner loses -> LOSS

        LAY:
            selected runner wins  -> LOSS
            selected runner loses -> WIN
    """

    result_text = _clean(
        provider_result
    )

    if not result_text:
        return None

    selection_id = _clean(
        getattr(
            selection,
            "selection_id",
            "",
        )
    )

    runner_name = _clean(
        getattr(
            selection,
            "runner_name",
            "",
        )
    )

    side = _clean(
        getattr(
            selection,
            "side",
            "",
        )
    ).upper()

    # -----------------------------------------------------
    # Determine whether user's selected runner won
    # -----------------------------------------------------

    selected_runner_won = False

    # Exact selection ID
    if (
        selection_id
        and result_text == selection_id
    ):
        selected_runner_won = True

    # Exact runner name
    elif (
        runner_name
        and result_text.casefold()
        == runner_name.casefold()
    ):
        selected_runner_won = True

    # Selection ID embedded in provider result
    elif (
        selection_id
        and _contains_numeric_identifier(
            result_text,
            selection_id,
        )
    ):
        selected_runner_won = True

    # Runner name embedded in provider result
    elif (
        runner_name
        and runner_name.casefold()
        in result_text.casefold()
    ):
        selected_runner_won = True

    # -----------------------------------------------------
    # BACK
    # -----------------------------------------------------

    if side == "BACK":

        if selected_runner_won:
            return "won"

        # A final provider winner that does not match
        # the selected runner means the BACK bet lost.
        return "lost"

    # -----------------------------------------------------
    # LAY
    # -----------------------------------------------------

    if side == "LAY":

        if selected_runner_won:
            return "lost"

        # Selected runner did not win.
        return "won"

    return None


# =========================================================
# SYNC BALANCE
# =========================================================

def _set_user_balance(
    db: Session,
    user: User,
    new_balance: Decimal,
) -> None:
    """
    User.balance is the balance used by the current bet
    placement flow.

    Wallet.balance is kept synchronized so the two models
    do not diverge.
    """

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

        wallet.balance = new_balance


# =========================================================
# SETTLE ONE BET
# =========================================================

def settle_one_bet(
    db: Session,
    bet: Bet,
) -> Optional[str]:
    """
    Returns:

        "won"
        "lost"
        "void"
        None

    None means:
        still pending
        provider result unavailable
        unsupported market
        incomplete data
    """

    # -----------------------------------------------------
    # Only pending bets
    # -----------------------------------------------------

    if _clean(
        bet.status
    ).lower() != "pending":
        return None

    # -----------------------------------------------------
    # Get selections
    # -----------------------------------------------------

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

    # Current place-bet flow creates one selection.
    selection = selections[0]

    # -----------------------------------------------------
    # Detect market
    # -----------------------------------------------------

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
    # IDEMPOTENCY CHECK
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

    if existing_settlement:

        # A settlement transaction already exists.
        # Never create another payout/refund.
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

    # =====================================================
    # MONEY VALUES
    # =====================================================

    stake = (
        _to_decimal(
            bet.stake
        )
        or Decimal("0.00")
    )

    potential_win = (
        _to_decimal(
            bet.potential_win
        )
        or Decimal("0.00")
    )

    current_balance = (
        _to_decimal(
            user.balance
        )
        or Decimal("0.00")
    )

    # =====================================================
    # WIN
    # =====================================================

    if settlement == "won":

        # potential_win represents TOTAL return.
        #
        # Example:
        #
        # stake         = 100
        # odds          = 1.50
        # potential_win = 150
        #
        # Stake was already deducted at placement.
        # Therefore we credit the full 150.

        credit = potential_win

        new_balance = (
            current_balance
            + credit
        )

        _set_user_balance(
            db,
            user,
            new_balance,
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

        db.add(
            transaction
        )

        bet.status = "won"

        print(
            "[SETTLEMENT] WON:",
            "bet=",
            bet.id,
            "user=",
            user.id,
            "credit=",
            float(credit),
            "balance=",
            float(new_balance),
        )

        return "won"

    # =====================================================
    # LOSS
    # =====================================================

    if settlement == "lost":

        # Stake was already deducted when the bet
        # was placed.

        # No money is added on a losing bet.

        # We still synchronize Wallet.balance with
        # User.balance so old discrepancies are repaired.

        _set_user_balance(
            db,
            user,
            current_balance,
        )

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

        db.add(
            transaction
        )

        print(
            "[SETTLEMENT] LOST:",
            "bet=",
            bet.id,
            "user=",
            user.id,
        )

        return "lost"

    # =====================================================
    # VOID
    # =====================================================

    if settlement == "void":

        # Return original stake.

        new_balance = (
            current_balance
            + stake
        )

        _set_user_balance(
            db,
            user,
            new_balance,
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

        db.add(
            transaction
        )

        bet.status = "void"

        print(
            "[SETTLEMENT] VOID:",
            "bet=",
            bet.id,
            "user=",
            user.id,
            "refund=",
            float(stake),
            "balance=",
            float(new_balance),
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
    """
    Settles pending bets one by one.

    IMPORTANT:
    Each successfully settled bet is committed separately.

    This prevents:

        Bet #1 -> successful settlement
        Bet #2 -> exception
        rollback()
        => Bet #1 payout accidentally disappears

    """

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

            # -------------------------------------------------
            # Nothing final yet
            # -------------------------------------------------

            if result is None:

                stats["pending"] += 1

                # No changes need committing.
                continue

            # -------------------------------------------------
            # Commit THIS settlement immediately
            # -------------------------------------------------

            db.commit()

            if result == "won":
                stats["won"] += 1

            elif result == "lost":
                stats["lost"] += 1

            elif result == "void":
                stats["void"] += 1

        except Exception as exc:

            stats["errors"] += 1

            # Roll back ONLY this failed transaction.
            # Earlier successfully committed settlements
            # remain safe.

            try:
                db.rollback()
            except Exception:
                pass

            print(
                "[SETTLEMENT] Bet error:",
                getattr(
                    bet,
                    "id",
                    "?",
                ),
                repr(exc),
            )

    return stats


# =========================================================
# ONE WORKER CYCLE
# =========================================================

def run_settlement_cycle(
    limit: int = 100,
) -> dict[str, int]:

    generator = get_db()

    db = next(
        generator
    )

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

            stats = (
                run_settlement_cycle()
            )

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