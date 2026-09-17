from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from models.user import User
from models.bet import Bet

from services import proexch_api


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
    # DO NOT CALL PROEXCH HERE
    #
    # Dashboard loads first.
    # JavaScript loads matches asynchronously.
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
            f"USER BETS ERROR: {exc}"
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

    match_id = str(
        match_id
    ).strip()

    print(
        "\n========================================"
    )

    print(
        "CRICKBET - PROEXCH MATCH"
    )

    print(
        "GAME ID:",
        match_id,
    )

    print(
        "========================================"
    )

    # ------------------------------------------------------
    # FIND MATCH
    # ------------------------------------------------------

    try:

        selected_match = (
            proexch_api.get_match(
                match_id
            )
        )

    except Exception as exc:

        print(
            "PROEXCH MATCH ERROR:",
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

    if selected_match is None:

        print(
            "PROEXCH MATCH NOT FOUND:",
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
    # BASIC MATCH DATA
    # ------------------------------------------------------

    game_id = str(
        selected_match.get(
            "gameId",
            match_id,
        )
    )

    market_id = str(
        selected_match.get(
            "marketId",
            "",
        )
    )

    event_id = str(
        selected_match.get(
            "eventId",
            "",
        )
    )

    event_name = (
        selected_match.get(
            "eventName"
        )
        or "Cricket Match"
    )

    event_time = (
        selected_match.get(
            "eventTime"
        )
        or ""
    )

    in_play = bool(
        selected_match.get(
            "inPlay",
            False,
        )
    )

    team1 = (
        selected_match.get(
            "runnerName1"
        )
        or "Team 1"
    )

    team2 = (
        selected_match.get(
            "runnerName2"
        )
        or "Team 2"
    )

    team3 = (
        selected_match.get(
            "runnerName3"
        )
        or "The Draw"
    )

    # ------------------------------------------------------
    # LOAD ODDS
    # ------------------------------------------------------

    odds_data = {}

    odds_error = None

    try:

        if not market_id:

            raise ValueError(
                "ProExch did not provide marketId"
            )

        odds_data = (
            proexch_api.get_odds(
                game_id=game_id,
                market_id=market_id,
            )
        )

    except Exception as exc:

        odds_error = str(exc)

        print(
            "PROEXCH ODDS ERROR:",
            odds_error,
        )

    # ------------------------------------------------------
    # RAW ODDS
    # ------------------------------------------------------

    match_odds_raw = (
        odds_data.get(
            "matchOdds",
            []
        )
    )

    bookmaker_odds_raw = (
        odds_data.get(
            "bookMakerOdds",
            []
        )
    )

    fancy_odds_raw = (
        odds_data.get(
            "fancyOdds",
            []
        )
    )

    other_market_odds = (
        odds_data.get(
            "otherMarketOdds",
            []
        )
    )

    # Safety checks

    if not isinstance(
        match_odds_raw,
        list,
    ):
        match_odds_raw = []

    if not isinstance(
        bookmaker_odds_raw,
        list,
    ):
        bookmaker_odds_raw = []

    if not isinstance(
        fancy_odds_raw,
        list,
    ):
        fancy_odds_raw = []

    if not isinstance(
        other_market_odds,
        list,
    ):
        other_market_odds = []

    # ------------------------------------------------------
    # PARSED ODDS
    # ------------------------------------------------------

    match_odds = (
        proexch_api.parse_match_odds(
            match_odds_raw
        )
    )

    fancy_odds = (
        proexch_api.parse_fancy_odds(
            fancy_odds_raw
        )
    )

    fancy_market_ids = (
        proexch_api.get_fancy_market_ids(
            game_id,
            fancy_odds_raw,
        )
    )

    # ------------------------------------------------------
    # FINAL MATCH OBJECT
    # ------------------------------------------------------

    match = {

        "id": game_id,

        "game_id": game_id,

        "market_id": market_id,

        "event_id": event_id,

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

        "league": "Cricket",

        "match_odds": match_odds,

        "fancy_odds": fancy_odds,

        "match_odds_raw": (
            match_odds_raw
        ),

        "bookmaker_odds": (
            bookmaker_odds_raw
        ),

        "fancy_odds_raw": (
            fancy_odds_raw
        ),

        "other_market_odds": (
            other_market_odds
        ),

        "fancy_market_ids": (
            fancy_market_ids
        ),

        "bookmaker": "",

        "markets": [],
    }

    # ------------------------------------------------------
    # DEBUG
    # ------------------------------------------------------

    print(
        "\n========== PROEXCH MATCH =========="
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
        "In Play:",
        in_play,
    )

    print(
        "Match runners:",
        len(match_odds),
    )

    print(
        "Bookmaker markets:",
        len(bookmaker_odds_raw),
    )

    print(
        "Fancy markets:",
        len(fancy_odds),
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

            "error": odds_error,
        },
    )