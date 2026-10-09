import re
import time
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

# If Fancy result exactly equals the selected line,
# return the original stake.
FANCY_EQUAL_ACTION = "void"

# Settlement worker polling interval.
SETTLEMENT_INTERVAL = 5.0

# Maximum pending bets checked in one cycle.
SETTLEMENT_BATCH_SIZE = 100


# =========================================================
# BASIC HELPERS
# =========================================================

def _clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None

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

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return None


# =========================================================
# MARKET TYPE
# =========================================================

def _detect_market_type(
    selection: BetSelection,
) -> str:

    stored = _clean(
        getattr(
            selection,
            "market_type",
            "",
        )
    ).upper()

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

    if stored:
        return aliases.get(
            stored,
            stored,
        )

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

    market_id = _clean(
        getattr(
            selection,
            "market_id",
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

    if (
        "_" in market_id
        and _extract_line(
            runner_name
        ) is not None
    ):
        return "FANCY"

    return "MATCH_ODDS"


# =========================================================
# PROVIDER RESPONSE PARSING
# =========================================================

def _extract_result_rows(
    payload: Any,
) -> list[dict[str, Any]]:

    if not isinstance(
        payload,
        dict,
    ):
        return []

    current = payload

    # Our ProExch service wraps the raw response
    # inside "result".
    if isinstance(
        current.get("result"),
        dict,
    ):
        current = current["result"]

    data = current.get(
        "data"
    )

    # -----------------------------------------------------
    # Standard ProExch response:
    #
    # {
    #   "data": {
    #       "data": [...]
    #   }
    # }
    # -----------------------------------------------------

    if isinstance(
        data,
        dict,
    ):

        nested = data.get(
            "data"
        )

        if isinstance(
            nested,
            list,
        ):
            return [
                item
                for item in nested
                if isinstance(
                    item,
                    dict,
                )
            ]

        if isinstance(
            nested,
            dict,
        ):
            return [
                nested
            ]

        if any(
            key in data
            for key in (
                "id",
                "result",
                "winner",
                "winnerId",
            )
        ):
            return [
                data
            ]

    # -----------------------------------------------------
    # Data itself is a list
    # -----------------------------------------------------

    if isinstance(
        data,
        list,
    ):
        return [
            item
            for item in data
            if isinstance(
                item,
                dict,
            )
        ]

    # -----------------------------------------------------
    # Direct result object
    # -----------------------------------------------------

    if any(
        key in current
        for key in (
            "id",
            "result",
            "winner",
            "winnerId",
        )
    ):
        return [
            current
        ]

    return []


# =========================================================
# GET PROVIDER RESULT
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

        print(
            "[SETTLEMENT] Missing market ID:",
            "selection=",
            getattr(
                selection,
                "id",
                "?",
            ),
            "type=",
            result_type,
        )

        return None

    # -----------------------------------------------------
    # REQUEST PROEXCH RESULT
    # -----------------------------------------------------

    try:

        response = (
            proexch_api
            .get_proexch_betfair_result(
                market_id=market_id,
                result_type=result_type,
            )
        )

    except Exception as exc:

        print(
            "[SETTLEMENT] Provider request exception:",
            "market=",
            market_id,
            "type=",
            result_type,
            "error=",
            repr(exc),
        )

        return None

    # -----------------------------------------------------
    # PROVIDER FAILURE
    # -----------------------------------------------------

    if (
        not response
        or not response.get(
            "success"
        )
    ):

        print(
            "[SETTLEMENT] Provider result unavailable:",
            "market=",
            market_id,
            "type=",
            result_type,
            "response=",
            response,
        )

        return None

    # -----------------------------------------------------
    # EXTRACT ROWS
    # -----------------------------------------------------

    rows = _extract_result_rows(
        response
    )

    if not rows:

        print(
            "[SETTLEMENT] No result rows:",
            "market=",
            market_id,
            "type=",
            result_type,
        )

        return None

    # -----------------------------------------------------
    # EXACT ID MATCH
    # -----------------------------------------------------

    exact_rows = [
        row
        for row in rows
        if _clean(
            row.get("id")
        ) == market_id
    ]

    # -----------------------------------------------------
    # SINGLE RESULT FALLBACK
    # -----------------------------------------------------
    #
    # The request already targeted the exact market ID.
    #
    # Some ProExch responses can return one result row
    # whose "id" representation differs from market_id.
    #
    # If exactly one row is returned, it is safe to use
    # that row.
    # -----------------------------------------------------

    if exact_rows:

        candidate_rows = exact_rows

    elif len(rows) == 1:

        candidate_rows = rows

    else:

        print(
            "[SETTLEMENT] Could not identify result row:",
            "market=",
            market_id,
            "type=",
            result_type,
            "returned_ids=",
            [
                _clean(
                    row.get("id")
                )
                for row in rows
            ],
        )

        return None

    # -----------------------------------------------------
    # EXTRACT FINAL RESULT
    # -----------------------------------------------------

    pending_values = {
        "",
        "-",
        "PENDING",
        "OPEN",
        "SUSPENDED",
        "UNAVAILABLE",
        "NULL",
        "NONE",
        "WAITING",
        "PROCESSING",
    }

    for row in candidate_rows:

        result = row.get(
            "result"
        )

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

        result_text = _clean(
            result
        )

        # -------------------------------------------------
        # RESULT NOT FINISHED
        # -------------------------------------------------

        if (
            result_text.upper()
            in pending_values
        ):

            print(
                "[SETTLEMENT] Result not final:",
                "market=",
                market_id,
                "type=",
                result_type,
                "result=",
                result_text,
            )

            return None

        # -------------------------------------------------
        # FINAL RESULT
        # -------------------------------------------------

        if result_text:

            print(
                "[SETTLEMENT] FINAL RESULT:",
                "market=",
                market_id,
                "type=",
                result_type,
                "result=",
                result_text,
            )

            return result_text

    print(
        "[SETTLEMENT] Result row has no usable result:",
        market_id,
        result_type,
    )

    return None


# =========================================================
# FANCY LINE
# =========================================================

def _extract_line(
    text: Any,
) -> Optional[float]:

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

    result_value = _to_float(result_text)

    if result_value is None:
        return None

    # Never infer a betting threshold from runner_name.
    # For example, "35 over run BAN" contains an over number,
    # which is not necessarily the selected betting threshold.
    raw_line = getattr(selection, "line", None)
    line = _to_float(raw_line)

    if line is None:
        print(
            "[SETTLEMENT] Refusing Fancy settlement: "
            "explicit betting line is missing.",
            "bet_id=",
            getattr(selection, "bet_id", None),
            "runner=",
            getattr(selection, "runner_name", ""),
            "market_id=",
            getattr(selection, "market_id", ""),
        )
        return None

    side = str(
        getattr(selection, "side", "") or ""
    ).strip().upper()

    if side not in {"BACK", "LAY"}:
        return None

    if result_value > line:
        return "won" if side == "BACK" else "lost"

    if result_value < line:
        return "lost" if side == "BACK" else "won"

    if FANCY_EQUAL_ACTION == "void":
        return "void"

    return None

# =========================================================
# STANDARD RESULT MATCHING
# =========================================================

def _contains_numeric_identifier(
    result_text: str,
    identifier: str,
) -> bool:

    identifier = identifier.strip()

    if not identifier:
        return False

    if not identifier.isdigit():

        return (
            identifier.casefold()
            in result_text.casefold()
        )

    pattern = (
        r"(?<!\d)"
        + re.escape(identifier)
        + r"(?!\d)"
    )

    return (
        re.search(
            pattern,
            result_text,
        )
        is not None
    )


def _standard_result_matches_selection(
    selection: BetSelection,
    provider_result: str,
) -> Optional[str]:

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

    selected_runner_won = False

    # -----------------------------------------------------
    # EXACT SELECTION ID
    # -----------------------------------------------------

    if (
        selection_id
        and result_text == selection_id
    ):

        selected_runner_won = True

    # -----------------------------------------------------
    # EXACT RUNNER NAME
    # -----------------------------------------------------

    elif (
        runner_name
        and result_text.casefold()
        == runner_name.casefold()
    ):

        selected_runner_won = True

    # -----------------------------------------------------
    # SELECTION ID INSIDE RESULT
    # -----------------------------------------------------

    elif (
        selection_id
        and _contains_numeric_identifier(
            result_text,
            selection_id,
        )
    ):

        selected_runner_won = True

    # -----------------------------------------------------
    # RUNNER NAME INSIDE RESULT
    # -----------------------------------------------------

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

        return "lost"

    # -----------------------------------------------------
    # LAY
    # -----------------------------------------------------

    if side == "LAY":

        if selected_runner_won:
            return "lost"

        return "won"

    return None


# =========================================================
# BALANCE SYNC
# =========================================================

def _set_user_balance(
    db: Session,
    user: User,
    new_balance: Decimal,
) -> None:

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

    # -----------------------------------------------------
    # ONLY PENDING
    # -----------------------------------------------------

    if (
        _clean(
            getattr(
                bet,
                "status",
                "",
            )
        ).lower()
        != "pending"
    ):

        return None

    # -----------------------------------------------------
    # GET SELECTION
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

        result_text = _get_result_value(
            selection,
            "new_fancy",
        )

        if result_text is None:
            return None

        settlement = _settle_fancy(
            selection,
            result_text,
        )

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

    else:

        print(
            "[SETTLEMENT] Unsupported market type:",
            market_type,
            "bet=",
            bet.id,
        )

        return None

    if settlement is None:
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

    # =====================================================
    # MONEY
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
    # WON
    # =====================================================

    if settlement == "won":

        # potential_win is the TOTAL return.
        #
        # Example:
        #
        # stake = 100
        # odds = 1.50
        # potential_win = 150
        #
        # The stake was already deducted.
        # Therefore credit the full 150.

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
    # LOST
    # =====================================================

    if settlement == "lost":

        # Stake was already deducted at placement.

        _set_user_balance(
            db,
            user,
            current_balance,
        )

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

        bet.status = "lost"

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
    limit: int = SETTLEMENT_BATCH_SIZE,
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

            # -------------------------------------------------
            # Still waiting for provider result
            # -------------------------------------------------

            if result is None:

                stats["pending"] += 1

                continue

            # -------------------------------------------------
            # Commit this settlement immediately.
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
    limit: int = SETTLEMENT_BATCH_SIZE,
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
# CONTINUOUS WORKER
# =========================================================

def settlement_worker_loop(
    interval_seconds: float = SETTLEMENT_INTERVAL,
) -> None:

    print(
        "[SETTLEMENT] Worker started"
    )

    print(
        "[SETTLEMENT] Poll interval:",
        interval_seconds,
        "seconds",
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