from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from models.user import User
from models.bet import Bet

from services import proexch_api


# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter()

templates = Jinja2Templates(
    directory="templates"
)


# ==========================================================
# FORMAT USER BET
# ==========================================================

def format_user_bet(
    bet: Bet,
) -> dict:

    created_at = (
        bet.created_at.strftime(
            "%d %b %Y, %I:%M %p"
        )
        if bet.created_at
        else "-"
    )

    return {
        "id": bet.id,

        "stake": float(
            bet.stake or 0
        ),

        "total_odds": float(
            bet.total_odds or 0
        ),

        "potential_win": float(
            bet.potential_win or 0
        ),

        "status": str(
            bet.status or "pending"
        ).lower(),

        "created_at": created_at,
    }


# ==========================================================
# DASHBOARD
# ==========================================================

@router.get("/dashboard")
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
):

    user_id = request.session.get(
        "user_id"
    )

    if not user_id:

        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        request.session.clear()

        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    # ------------------------------------------------------
    # Dashboard must NOT call ProExch.
    #
    # dashboard.js loads cricket matches asynchronously.
    # ------------------------------------------------------

    try:

        user_bets = (
            db.query(Bet)
            .filter(
                Bet.user_id == user.id
            )
            .order_by(
                Bet.created_at.desc()
            )
            .limit(20)
            .all()
        )

    except Exception as exc:

        print(
            f"[DASHBOARD] user bets error: {exc}"
        )

        user_bets = []

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "matches": [],
            "bets": [
                format_user_bet(bet)
                for bet in user_bets
            ],
        },
    )


# ==========================================================
# MATCH PAGE
# ==========================================================

@router.get("/match/{match_id}")
async def match_page(
    request: Request,
    match_id: str,
    db: Session = Depends(get_db),
):

    # ------------------------------------------------------
    # AUTH
    # ------------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )

    if not user_id:

        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        request.session.clear()

        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    # ------------------------------------------------------
    # CLEAN GAME ID
    # ------------------------------------------------------

    match_id = str(
        match_id
    ).strip()

    if not match_id:

        return templates.TemplateResponse(
            request=request,
            name="match.html",
            context={
                "user": user,
                "match": None,
                "error": "Invalid match ID.",
            },
        )

    print(
        "\n========================================"
    )

    print(
        "[CRICKBET] OPEN MATCH PAGE"
    )

    print(
        "Game ID:",
        match_id,
    )

    print(
        "========================================"
    )

    # ------------------------------------------------------
    # FIND MATCH
    #
    # IMPORTANT:
    # The service function is find_match(),
    # NOT get_match().
    # ------------------------------------------------------

    try:

        selected_match = (
            proexch_api.find_match(
                match_id
            )
        )

    except Exception as exc:

        print(
            "[CRICKET] PROEXCH MATCH ERROR:",
            exc,
        )

        return templates.TemplateResponse(
            request=request,
            name="match.html",
            context={
                "user": user,
                "match": None,
                "error": (
                    f"Unable to load match: {exc}"
                ),
            },
        )

    # ------------------------------------------------------
    # MATCH NOT FOUND
    # ------------------------------------------------------

    if not selected_match:

        print(
            "[CRICKET] MATCH NOT FOUND:",
            match_id,
        )

        return templates.TemplateResponse(
            request=request,
            name="match.html",
            context={
                "user": user,
                "match": None,
                "error": (
                    "This match is no longer available."
                ),
            },
        )

    # ------------------------------------------------------
    # SELECTED MATCH IS ALREADY NORMALIZED BY
    # proexch_api.get_matches()
    #
    # Therefore use snake_case fields.
    # ------------------------------------------------------

    game_id = str(
        selected_match.get(
            "game_id"
        )
        or match_id
    )

    market_id = str(
        selected_match.get(
            "market_id"
        )
        or ""
    )

    event_id = str(
        selected_match.get(
            "event_id"
        )
        or game_id
    )

    event_name = (
        selected_match.get(
            "event_name"
        )
        or "Cricket Match"
    )

    event_time = (
        selected_match.get(
            "event_time"
        )
        or ""
    )

    in_play = bool(
        selected_match.get(
            "in_play",
            False,
        )
    )

    team1 = (
        selected_match.get(
            "team1"
        )
        or "Team 1"
    )

    team2 = (
        selected_match.get(
            "team2"
        )
        or "Team 2"
    )

    team3 = (
        selected_match.get(
            "team3"
        )
        or ""
    )

    # ------------------------------------------------------
    # SCORE ID OF THIS SPECIFIC MATCH
    #
    # The scoreboard must come from the match that was
    # tapped ("VIEW MATCH"). get_matches() already resolves
    # score_id (falls back to game_id), so pass it to the page.
    # ------------------------------------------------------

    score_id = str(
        selected_match.get(
            "score_id"
        )
        or game_id
    )

    # ------------------------------------------------------
    # ODDS
    #
    # Do NOT call ProExch odds while rendering the HTML page.
    # The browser loads odds through /api/cricket/odds immediately
    # after the page is displayed. Calling the provider here caused
    # the match page to wait for a second odds request before HTML
    # could be returned.
    # ------------------------------------------------------

    match_odds = []
    bookmaker_odds = []
    fancy_odds = []
    other_market_odds = []
    counts = {}
    fancy_market_ids = []
    raw_odds = {}
    odds_error = None

    # ------------------------------------------------------
    # FINAL MATCH OBJECT
    # ------------------------------------------------------

    match = {

        "id": game_id,

        "game_id": game_id,

        "market_id": market_id,

        "event_id": event_id,

        "score_id": score_id,

        "event_name": event_name,

        "team1": team1,

        "team2": team2,

        "team3": team3,

        "status": (
            "LIVE"
            if in_play
            else "UPCOMING"
        ),

        "in_play": in_play,

        "start_time": event_time,

        "event_time": event_time,

        "league": "Cricket",

        # --------------------------------------------------
        # NORMALIZED ODDS
        # --------------------------------------------------

        "match_odds": match_odds,

        "bookmaker_odds": bookmaker_odds,

        "fancy_odds": fancy_odds,

        "other_market_odds": (
            other_market_odds
        ),

        "fancy_market_ids": (
            fancy_market_ids
        ),

        "counts": counts,

        # --------------------------------------------------
        # RAW DATA
        # --------------------------------------------------

        "raw_match": (
            selected_match.get(
                "raw",
                {}
            )
        ),

        "raw_odds": raw_odds,

        # --------------------------------------------------
        # COMPATIBILITY FIELDS
        # --------------------------------------------------

        "match_odds_raw": (
            raw_odds.get(
                "matchOdds",
                []
            )
            if isinstance(
                raw_odds,
                dict
            )
            else []
        ),

        "bookmaker_odds_raw": (
            raw_odds.get(
                "bookMakerOdds",
                []
            )
            if isinstance(
                raw_odds,
                dict
            )
            else []
        ),

        "fancy_odds_raw": (
            raw_odds.get(
                "fancyOdds",
                []
            )
            if isinstance(
                raw_odds,
                dict
            )
            else []
        ),

        "bookmaker": "",

        "markets": [],
    }

    # ------------------------------------------------------
    # DEBUG
    # ------------------------------------------------------

    print(
        "\n========== CRICKBET MATCH =========="
    )

    print(
        "Event:",
        event_name,
    )

    print(
        "Game ID:",
        game_id,
    )

    print(
        "Market ID:",
        market_id,
    )

    print(
        "Event ID:",
        event_id,
    )

    print(
        "Score ID:",
        score_id,
    )

    print(
        "In Play:",
        in_play,
    )

    print(
        "Match markets:",
        len(match_odds),
    )

    print(
        "Bookmaker markets:",
        len(bookmaker_odds),
    )

    print(
        "Fancy markets:",
        len(fancy_odds),
    )

    print(
        "Fancy market IDs:",
        fancy_market_ids,
    )

    print(
        "Other markets:",
        len(other_market_odds),
    )

    print(
        "===================================\n"
    )

    # ------------------------------------------------------
    # RENDER
    # ------------------------------------------------------

    return templates.TemplateResponse(
        request=request,
        name="match.html",
        context={
            "user": user,
            "match": match,
            "game_id": game_id,
            "error": odds_error,
        },
    )