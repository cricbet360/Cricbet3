from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services import proexch_api


router = APIRouter(tags=["Cricket"])

templates = Jinja2Templates(
    directory="templates"
)


# =========================================================
# AUTH
# =========================================================

def is_logged_in(request: Request) -> bool:
    return request.session.get("user_id") is not None


def unauthorized():
    return JSONResponse(
        status_code=401,
        content={
            "success": False,
            "error": "Authentication required",
        },
    )


# =========================================================
# HELPERS
# =========================================================

def clean(value: Any) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    return value if value else None


def first_value(
    data: dict,
    *keys: str,
    default=None,
):
    if not isinstance(data, dict):
        return default

    for key in keys:

        if key not in data:
            continue

        value = data.get(key)

        if value is not None:
            return value

    return default


def ensure_list(value) -> list:

    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, dict):

        for key in (
            "data",
            "items",
            "markets",
            "oddDatas",
            "odds",
            "rows",
            "list",
        ):

            nested = value.get(key)

            if isinstance(nested, list):
                return nested

        return [value]

    return []


def to_number(value):

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    try:

        text = str(value).strip()

        if not text:
            return None

        number = float(text)

        if number.is_integer():
            return int(number)

        return number

    except (ValueError, TypeError):

        return None


# =========================================================
# MATCH
# =========================================================

def find_match(
    matches: list[dict],
    game_id: str,
) -> dict | None:

    game_id = str(game_id).strip()

    for match in matches:

        if not isinstance(match, dict):
            continue

        current_game_id = first_value(
            match,
            "gameId",
            "game_id",
            "gameID",
            "gameid",
        )

        if current_game_id is None:
            continue

        if str(current_game_id).strip() == game_id:
            return match

    return None


def get_match_ids(
    match: dict,
):
    event_id = first_value(
        match,
        "eventId",
        "event_id",
        "eventID",
        "eventid",
    )

    market_id = first_value(
        match,
        "marketId",
        "market_id",
        "marketID",
        "marketid",
    )

    return (
        clean(event_id),
        clean(market_id),
    )


def normalize_match(
    match: dict,
) -> dict:

    game_id = first_value(
        match,
        "gameId",
        "game_id",
        "gameID",
        "gameid",
    )

    event_id = first_value(
        match,
        "eventId",
        "event_id",
        "eventID",
        "eventid",
    )

    market_id = first_value(
        match,
        "marketId",
        "market_id",
        "marketID",
        "marketid",
    )

    event_name = first_value(
        match,
        "eventName",
        "event_name",
        "name",
        default="Cricket",
    )

    team1 = first_value(
        match,
        "runnerName1",
        "team1",
        "runner1",
        default="Team 1",
    )

    team2 = first_value(
        match,
        "runnerName2",
        "team2",
        "runner2",
        default="Team 2",
    )

    team3 = first_value(
        match,
        "runnerName3",
        "team3",
        "runner3",
    )

    event_time = first_value(
        match,
        "eventTime",
        "event_time",
        "startTime",
        "start_time",
    )

    in_play = first_value(
        match,
        "inPlay",
        "in_play",
        default=False,
    )

    if isinstance(in_play, str):

        in_play = (
            in_play.strip().lower()
            in (
                "true",
                "1",
                "yes",
                "y",
                "live",
            )
        )

    else:

        in_play = bool(in_play)

    tv = first_value(
        match,
        "tv",
        default=False,
    )

    return {
        "game_id": clean(game_id),
        "event_id": clean(event_id),
        "market_id": clean(market_id),

        "gameId": clean(game_id),
        "eventId": clean(event_id),
        "marketId": clean(market_id),

        "event_name": event_name,
        "eventName": event_name,

        "event_time": event_time,
        "eventTime": event_time,

        "team1": team1,
        "team2": team2,
        "team3": team3,

        "in_play": in_play,
        "inPlay": in_play,

        "tv": tv,

        "raw": match,
    }


# =========================================================
# ODDS NORMALIZATION
# =========================================================

def normalize_odds(raw_odds: dict) -> dict:
    """
    Uses the exact structure returned by ProExch:

    data
      ├── matchOdds
      ├── bookMakerOdds
      ├── fancyOdds
      └── otherMarketOdds
    """

    if not isinstance(raw_odds, dict):
        raw_odds = {}

    data = raw_odds.get("data")

    if isinstance(data, dict):
        raw = data
    else:
        raw = raw_odds

    match_odds = (
        proexch_api.parse_match_odds(
            raw.get("matchOdds", [])
        )
    )

    bookmaker_odds = (
        proexch_api.parse_bookmaker_odds(
            raw.get("bookMakerOdds", [])
        )
    )

    fancy_odds = (
        proexch_api.parse_fancy_odds(
            raw.get("fancyOdds", [])
        )
    )

    other_market_odds = raw.get(
        "otherMarketOdds",
        [],
    )

    if not isinstance(
        other_market_odds,
        list,
    ):
        other_market_odds = []

    return {
        "match_odds": match_odds,
        "bookmaker_odds": bookmaker_odds,
        "fancy_odds": fancy_odds,
        "other_market_odds": other_market_odds,
        "raw": raw,
    }


# =========================================================
# BUILD MATCH PAGE
# =========================================================

def build_match_page_data(
    match: dict,
    odds: dict,
) -> dict:

    normalized = normalize_match(
        match
    )

    normalized["status"] = (
        "LIVE"
        if normalized["in_play"]
        else "UPCOMING"
    )

    normalized["league"] = (
        normalized["event_name"]
        or "Cricket"
    )

    normalized["start_time"] = (
        normalized["event_time"]
    )

    normalized["bookmaker"] = "ProExch"

    normalized["match_odds"] = (
        odds.get("match_odds", [])
    )

    normalized["bookmaker_odds"] = (
        odds.get("bookmaker_odds", [])
    )

    normalized["fancy_odds"] = (
        odds.get("fancy_odds", [])
    )

    normalized["other_market_odds"] = (
        odds.get(
            "other_market_odds",
            [],
        )
    )

    markets = []

    for market in normalized["match_odds"]:

        markets.append({
            "id": market.get("id"),
            "name": market.get(
                "name",
                "Match Odds",
            ),
            "status": market.get(
                "status",
                "",
            ),
            "type": "match_odds",
            "runners": market.get(
                "runners",
                [],
            ),
            "outcomes": market.get(
                "outcomes",
                market.get(
                    "runners",
                    [],
                ),
            ),
        })

    for market in normalized["bookmaker_odds"]:

        markets.append({
            "id": market.get("id"),
            "name": market.get(
                "name",
                "Bookmaker",
            ),
            "status": market.get(
                "status",
                "",
            ),
            "type": "bookmaker",
            "runners": market.get(
                "runners",
                [],
            ),
            "outcomes": market.get(
                "outcomes",
                market.get(
                    "runners",
                    [],
                ),
            ),
        })

    for market in normalized["fancy_odds"]:

        markets.append({
            "id": market.get("id"),
            "name": market.get(
                "name",
                "Fancy / Session",
            ),
            "status": market.get(
                "status",
                "",
            ),
            "type": "fancy",
            "runners": market.get(
                "runners",
                [],
            ),
            "outcomes": market.get(
                "outcomes",
                market.get(
                    "runners",
                    [],
                ),
            ),
        })

    normalized["markets"] = markets

    normalized["match_odds_count"] = sum(
        len(m.get("runners", []))
        for m in normalized["match_odds"]
    )

    normalized["bookmaker_count"] = sum(
        len(m.get("runners", []))
        for m in normalized["bookmaker_odds"]
    )

    normalized["fancy_count"] = sum(
        len(m.get("runners", []))
        for m in normalized["fancy_odds"]
    )

    return normalized


# =========================================================
# RESOLVE MATCH
# =========================================================

def resolve_match(
    game_id: str,
):
    matches = proexch_api.get_matches()

    if not isinstance(matches, list):
        matches = []

    match = find_match(
        matches,
        game_id,
    )

    if not match:
        return None, None, None

    event_id, market_id = (
        get_match_ids(match)
    )

    return (
        match,
        event_id,
        market_id,
    )


# =========================================================
# MATCHES API
# =========================================================

@router.get(
    "/api/cricket/matches"
)
async def cricket_matches(
    request: Request,
):

    if not is_logged_in(request):
        return unauthorized()

    try:

        matches = (
            proexch_api.get_matches()
        )

        if not isinstance(
            matches,
            list,
        ):
            matches = []

        result = [
            normalize_match(match)
            for match in matches
            if isinstance(match, dict)
        ]

        return {
            "success": True,
            "matches": result,
            "count": len(result),
        }

    except Exception as exc:

        print(
            "[CRICKET] matches error:",
            repr(exc),
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": (
                    "Unable to load cricket matches"
                ),
            },
        )


# =========================================================
# ODDS API
# =========================================================

@router.get(
    "/api/cricket/odds"
)
async def cricket_odds(
    request: Request,

    gameId: str | None = None,
    marketId: str | None = None,

    game_id: str | None = None,
    market_id: str | None = None,

    eventId: str | None = None,
    event_id: str | None = None,
):

    if not is_logged_in(request):
        return unauthorized()

    game_id = clean(
        gameId or game_id
    )

    market_id = clean(
        marketId or market_id
    )

    # Event ID is accepted for frontend
    # compatibility but NOT sent to ProExch.
    event_id = clean(
        eventId or event_id
    )

    print(
        "[CRICKET] odds request:",
        "game_id=", game_id,
        "event_id=", event_id,
        "market_id=", market_id,
    )

    if not game_id:

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "gameId is required",
            },
        )

    try:

        # -------------------------------------------------
        # Resolve market ID if frontend didn't provide it
        # -------------------------------------------------

        if not market_id:

            matches = (
                proexch_api.get_matches()
            )

            if not isinstance(
                matches,
                list,
            ):
                matches = []

            match = find_match(
                matches,
                game_id,
            )

            if not match:

                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "error": "Match not found",
                    },
                )

            _, discovered_market_id = (
                get_match_ids(match)
            )

            market_id = discovered_market_id

        if not market_id:

            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": (
                        "marketId could not be "
                        "determined from ProExch"
                    ),
                },
            )

        # -------------------------------------------------
        # CALL PROEXCH
        # -------------------------------------------------

        print(
            "[CRICKET] calling ProExch:",
            "gameId=", game_id,
            "marketId=", market_id,
        )

        raw_odds = (
            proexch_api.get_odds(
                game_id=game_id,
                market_id=market_id,
            )
        )

        normalized = normalize_odds(
            raw_odds
        )

        print(
            "[CRICKET] odds received:",
            "match_markets=",
            len(
                normalized["match_odds"]
            ),
            "match_runners=",
            sum(
                len(
                    m.get(
                        "runners",
                        [],
                    )
                )
                for m in normalized[
                    "match_odds"
                ]
            ),
            "bookmaker_markets=",
            len(
                normalized[
                    "bookmaker_odds"
                ]
            ),
            "fancy_markets=",
            len(
                normalized[
                    "fancy_odds"
                ]
            ),
        )

        return {
            "success": True,

            "game_id": game_id,

            "event_id": event_id,

            "market_id": market_id,

            "match_odds": (
                normalized[
                    "match_odds"
                ]
            ),

            "bookmaker_odds": (
                normalized[
                    "bookmaker_odds"
                ]
            ),

            "fancy_odds": (
                normalized[
                    "fancy_odds"
                ]
            ),

            "other_market_odds": (
                normalized[
                    "other_market_odds"
                ]
            ),

            # Compatibility names
            "matchOdds": (
                normalized[
                    "match_odds"
                ]
            ),

            "bookMakerOdds": (
                normalized[
                    "bookmaker_odds"
                ]
            ),

            "fancyOdds": (
                normalized[
                    "fancy_odds"
                ]
            ),

            "odds": normalized["raw"],
        }

    except Exception as exc:

        print(
            "[CRICKET] odds error:",
            repr(exc),
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(exc),
            },
        )


# =========================================================
# MATCH JSON
# =========================================================

@router.get(
    "/api/cricket/match/{game_id}"
)
async def cricket_match(
    request: Request,
    game_id: str,
):

    if not is_logged_in(request):
        return unauthorized()

    game_id = clean(game_id)

    if not game_id:

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Invalid game ID",
            },
        )

    try:

        match, event_id, market_id = (
            resolve_match(game_id)
        )

        if not match:

            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "Match not found",
                },
            )

        raw_odds = (
            proexch_api.get_odds(
                game_id=game_id,
                market_id=market_id,
            )
        )

        normalized_odds = (
            normalize_odds(raw_odds)
        )

        page_match = (
            build_match_page_data(
                match,
                normalized_odds,
            )
        )

        return {
            "success": True,

            "game_id": game_id,
            "event_id": event_id,
            "market_id": market_id,

            "match": page_match,

            "match_odds": (
                normalized_odds[
                    "match_odds"
                ]
            ),

            "bookmaker_odds": (
                normalized_odds[
                    "bookmaker_odds"
                ]
            ),

            "fancy_odds": (
                normalized_odds[
                    "fancy_odds"
                ]
            ),

            "other_market_odds": (
                normalized_odds[
                    "other_market_odds"
                ]
            ),

            "odds": normalized_odds[
                "raw"
            ],
        }

    except Exception as exc:

        print(
            "[CRICKET] match error:",
            repr(exc),
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(exc),
            },
        )


# =========================================================
# MATCH PAGE
# =========================================================

@router.get(
    "/match/{game_id}"
)
async def match_page(
    request: Request,
    game_id: str,
):

    if not is_logged_in(request):

        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    game_id = clean(game_id)

    if not game_id:

        return templates.TemplateResponse(
            "match.html",
            {
                "request": request,
                "match": None,
                "error": "Invalid match ID.",
            },
        )

    try:

        print(
            "[CRICKET] opening match:",
            game_id,
        )

        match, event_id, market_id = (
            resolve_match(game_id)
        )

        print(
            "[CRICKET] resolved:",
            "game_id=", game_id,
            "event_id=", event_id,
            "market_id=", market_id,
        )

        if not match:

            return templates.TemplateResponse(
                "match.html",
                {
                    "request": request,
                    "match": None,
                    "error": (
                        "The requested cricket "
                        "match could not be found."
                    ),
                },
            )

        print(
            "[CRICKET] requesting initial odds:",
            game_id,
            market_id,
        )

        raw_odds = (
            proexch_api.get_odds(
                game_id=game_id,
                market_id=market_id,
            )
        )

        normalized_odds = (
            normalize_odds(raw_odds)
        )

        print(
            "[CRICKET] initial odds:",
            "match_markets=",
            len(
                normalized_odds[
                    "match_odds"
                ]
            ),
            "match_runners=",
            sum(
                len(
                    m.get(
                        "runners",
                        [],
                    )
                )
                for m in normalized_odds[
                    "match_odds"
                ]
            ),
            "bookmaker_markets=",
            len(
                normalized_odds[
                    "bookmaker_odds"
                ]
            ),
            "fancy_markets=",
            len(
                normalized_odds[
                    "fancy_odds"
                ]
            ),
        )

        page_match = (
            build_match_page_data(
                match,
                normalized_odds,
            )
        )

        return templates.TemplateResponse(
            "match.html",
            {
                "request": request,

                "match": page_match,

                "game_id": game_id,

                "event_id": event_id,

                "market_id": market_id,

                "odds": normalized_odds,

                "match_odds": (
                    normalized_odds[
                        "match_odds"
                    ]
                ),

                "bookmaker_odds": (
                    normalized_odds[
                        "bookmaker_odds"
                    ]
                ),

                "fancy_odds": (
                    normalized_odds[
                        "fancy_odds"
                    ]
                ),

                "other_market_odds": (
                    normalized_odds[
                        "other_market_odds"
                    ]
                ),

                "odds_error": None,

                "error": None,
            },
        )

    except Exception as exc:

        print(
            "[CRICKET] match page error:",
            repr(exc),
        )

        return templates.TemplateResponse(
            "match.html",
            {
                "request": request,

                "match": None,

                "game_id": game_id,

                "error": (
                    "Unable to load this "
                    "cricket match: "
                    + str(exc)
                ),

                "odds_error": str(exc),
            },
        )