from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services import proexch_api


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    tags=["Cricket"],
)

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# AUTH
# ============================================================

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


# ============================================================
# GENERIC HELPERS
# ============================================================

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

        if key in data:

            value = data.get(key)

            if value is not None:
                return value

    return default


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


def ensure_list(value) -> list:

    """
    ProExch can return a section as:

        []
        {}
        [ {}, {} ]

    Normalize all of them to a list.
    """

    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, dict):

        # Sometimes an object contains its own list.
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

        # Otherwise the dictionary itself is one object.
        return [value]

    return []


def unwrap_response(data: Any) -> Any:
    """
    Safely unwrap common ProExch response wrappers.

    Examples supported:

        {
            "matchOdds": [...]
        }

        {
            "data": {
                "matchOdds": [...]
            }
        }

        {
            "statusCode": 200,
            "data": {
                "data": {
                    "matchOdds": [...]
                }
            }
        }
    """

    current = data

    for _ in range(6):

        if not isinstance(current, dict):
            break

        # If the current object already contains actual odds
        # sections, stop here.
        if any(
            key in current
            for key in (
                "matchOdds",
                "bookMakerOdds",
                "bookmakerOdds",
                "fancyOdds",
                "otherMarketOdds",
            )
        ):
            break

        nested = None

        for key in (
            "data",
            "result",
            "response",
            "body",
        ):

            value = current.get(key)

            if isinstance(value, (dict, list)):
                nested = value
                break

        if nested is None:
            break

        current = nested

    return current


# ============================================================
# FIND MATCH
# ============================================================

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


# ============================================================
# GET PROEXCH IDS
# ============================================================

def get_match_ids(
    match: dict,
) -> tuple[str | None, str | None]:

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


# ============================================================
# NORMALIZE MATCH
# ============================================================

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

    # Handle string versions such as "true", "false", "1", "0".
    if isinstance(in_play, str):

        in_play = in_play.strip().lower() in (
            "true",
            "1",
            "yes",
            "y",
            "live",
        )

    else:

        in_play = bool(in_play)

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

        "tv": first_value(
            match,
            "tv",
            default=False,
        ),

        "raw": match,
    }


# ============================================================
# EXTRACT ODD DATAS
# ============================================================

def get_odd_datas(
    market: dict,
) -> list[dict]:

    if not isinstance(market, dict):
        return []

    value = first_value(
        market,
        "oddDatas",
        "oddData",
        "oddsData",
        "runners",
        "selections",
        "outcomes",
        default=[],
    )

    return [
        item
        for item in ensure_list(value)
        if isinstance(item, dict)
    ]


# ============================================================
# MATCH ODDS
# ============================================================

def parse_match_odds(
    raw_match_odds,
) -> list[dict]:

    markets = []

    for market in ensure_list(raw_match_odds):

        if not isinstance(market, dict):
            continue

        market_id = first_value(
            market,
            "mid",
            "marketId",
            "market_id",
            "marketID",
        )

        market_name = first_value(
            market,
            "market",
            "mname",
            "marketName",
            "name",
            default="Match Odds",
        )

        market_status = first_value(
            market,
            "mstatus",
            "status",
            "marketStatus",
            default="",
        )

        runners = []

        for item in get_odd_datas(market):

            selection_id = first_value(
                item,
                "sid",
                "selectionId",
                "selection_id",
                "runnerId",
                "runner_id",
            )

            runner_name = first_value(
                item,
                "rname",
                "runnerName",
                "selectionName",
                "name",
                default="Unknown",
            )

            back = to_number(
                first_value(
                    item,
                    "b1",
                    "back",
                    "backPrice",
                    "backOdds",
                    "backOdd",
                )
            )

            back_size = to_number(
                first_value(
                    item,
                    "bs1",
                    "backSize",
                    "backVolume",
                    "backAmount",
                )
            )

            lay = to_number(
                first_value(
                    item,
                    "l1",
                    "lay",
                    "layPrice",
                    "layOdds",
                    "layOdd",
                )
            )

            lay_size = to_number(
                first_value(
                    item,
                    "ls1",
                    "laySize",
                    "layVolume",
                    "layAmount",
                )
            )

            runners.append(
                {
                    "id": (
                        str(selection_id)
                        if selection_id is not None
                        else None
                    ),

                    "selection_id": (
                        str(selection_id)
                        if selection_id is not None
                        else None
                    ),

                    "name": str(runner_name),

                    "back": back,
                    "back_size": back_size,

                    "lay": lay,
                    "lay_size": lay_size,

                    # Extra aliases for templates.
                    "back_price": back,
                    "lay_price": lay,

                    "odds": back,

                    "status": first_value(
                        item,
                        "status",
                        "runnerStatus",
                        default="",
                    ),
                }
            )

        if runners:

            markets.append(
                {
                    "id": clean(market_id),
                    "name": str(market_name),
                    "status": market_status,
                    "type": "match_odds",
                    "runners": runners,
                    "outcomes": runners,
                }
            )

    return markets


# ============================================================
# BOOKMAKER
# ============================================================

def parse_bookmaker_odds(
    raw_bookmaker,
) -> list[dict]:

    markets = []

    for market in ensure_list(raw_bookmaker):

        if not isinstance(market, dict):
            continue

        runners = []

        for item in get_odd_datas(market):

            selection_id = first_value(
                item,
                "sid",
                "selectionId",
                "selection_id",
                "runnerId",
            )

            name = first_value(
                item,
                "rname",
                "runnerName",
                "selectionName",
                "name",
                default="Unknown",
            )

            back = to_number(
                first_value(
                    item,
                    "b1",
                    "back",
                    "backPrice",
                    "backOdds",
                )
            )

            back_size = to_number(
                first_value(
                    item,
                    "bs1",
                    "backSize",
                    "backVolume",
                )
            )

            lay = to_number(
                first_value(
                    item,
                    "l1",
                    "lay",
                    "layPrice",
                    "layOdds",
                )
            )

            lay_size = to_number(
                first_value(
                    item,
                    "ls1",
                    "laySize",
                    "layVolume",
                )
            )

            runners.append(
                {
                    "id": (
                        str(selection_id)
                        if selection_id is not None
                        else None
                    ),

                    "selection_id": (
                        str(selection_id)
                        if selection_id is not None
                        else None
                    ),

                    "name": str(name),

                    "back": back,
                    "back_size": back_size,

                    "lay": lay,
                    "lay_size": lay_size,

                    "back_price": back,
                    "lay_price": lay,

                    "odds": back,

                    "status": first_value(
                        item,
                        "status",
                        "runnerStatus",
                        default="",
                    ),
                }
            )

        if runners:

            market_id = first_value(
                market,
                "mid",
                "marketId",
                "market_id",
                "marketID",
            )

            market_name = first_value(
                market,
                "market",
                "mname",
                "marketName",
                "name",
                default="Bookmaker",
            )

            markets.append(
                {
                    "id": clean(market_id),
                    "name": str(market_name),
                    "status": first_value(
                        market,
                        "mstatus",
                        "status",
                        default="",
                    ),
                    "type": "bookmaker",
                    "runners": runners,
                    "outcomes": runners,
                }
            )

    return markets


# ============================================================
# FANCY / SESSION
# ============================================================

def parse_fancy_odds(
    raw_fancy,
) -> list[dict]:

    markets = []

    for market in ensure_list(raw_fancy):

        if not isinstance(market, dict):
            continue

        market_id = first_value(
            market,
            "mid",
            "marketId",
            "market_id",
            "marketID",
        )

        market_name = first_value(
            market,
            "market",
            "mname",
            "marketName",
            "name",
            default="Fancy / Session",
        )

        market_status = first_value(
            market,
            "mstatus",
            "status",
            "marketStatus",
            default="",
        )

        runners = []

        for item in get_odd_datas(market):

            sid = first_value(
                item,
                "sid",
                "selectionId",
                "selection_id",
                "runnerId",
            )

            name = first_value(
                item,
                "rname",
                "runnerName",
                "selectionName",
                "name",
                default="Session",
            )

            yes = to_number(
                first_value(
                    item,
                    "b1",
                    "yes",
                    "yesPrice",
                    "back",
                    "backPrice",
                )
            )

            yes_size = to_number(
                first_value(
                    item,
                    "bs1",
                    "yesSize",
                    "backSize",
                    "backVolume",
                )
            )

            no = to_number(
                first_value(
                    item,
                    "l1",
                    "no",
                    "noPrice",
                    "lay",
                    "layPrice",
                )
            )

            no_size = to_number(
                first_value(
                    item,
                    "ls1",
                    "noSize",
                    "laySize",
                    "layVolume",
                )
            )

            runners.append(
                {
                    "id": (
                        str(sid)
                        if sid is not None
                        else None
                    ),

                    "selection_id": (
                        str(sid)
                        if sid is not None
                        else None
                    ),

                    "name": str(name),

                    "yes": yes,
                    "yes_size": yes_size,

                    "no": no,
                    "no_size": no_size,

                    # Back/Lay aliases.
                    "back": yes,
                    "back_size": yes_size,

                    "lay": no,
                    "lay_size": no_size,

                    "odds": yes,

                    "status": first_value(
                        item,
                        "status",
                        "runnerStatus",
                        default="",
                    ),
                }
            )

        if runners:

            markets.append(
                {
                    "id": clean(market_id),

                    "name": str(market_name),

                    "status": market_status,

                    "type": "fancy",

                    "runners": runners,

                    "outcomes": runners,
                }
            )

    return markets


# ============================================================
# NORMALIZE ODDS
# ============================================================

def normalize_odds(
    raw_odds: dict,
) -> dict:

    raw_odds = unwrap_response(raw_odds)

    if not isinstance(raw_odds, dict):
        raw_odds = {}

    # --------------------------------------------------------
    # Match Odds
    # --------------------------------------------------------

    raw_match_odds = first_value(
        raw_odds,
        "matchOdds",
        "match_odds",
        "matchOddsData",
        default=[],
    )

    # --------------------------------------------------------
    # Bookmaker
    # --------------------------------------------------------

    raw_bookmaker = first_value(
        raw_odds,
        "bookMakerOdds",
        "bookmakerOdds",
        "bookmaker_odds",
        "bookMaker",
        default=[],
    )

    # --------------------------------------------------------
    # Fancy
    # --------------------------------------------------------

    raw_fancy = first_value(
        raw_odds,
        "fancyOdds",
        "fancy_odds",
        "sessionOdds",
        "fancy",
        default=[],
    )

    # --------------------------------------------------------
    # Other
    # --------------------------------------------------------

    raw_other = first_value(
        raw_odds,
        "otherMarketOdds",
        "other_market_odds",
        "otherOdds",
        default=[],
    )

    match_markets = parse_match_odds(
        raw_match_odds
    )

    bookmaker_markets = parse_bookmaker_odds(
        raw_bookmaker
    )

    fancy_markets = parse_fancy_odds(
        raw_fancy
    )

    return {
        "match_odds": match_markets,

        "bookmaker_odds": bookmaker_markets,

        "fancy_odds": fancy_markets,

        "other_market_odds": ensure_list(
            raw_other
        ),

        "raw": raw_odds,
    }


# ============================================================
# BUILD PAGE DATA
# ============================================================

def build_match_page_data(
    match: dict,
    odds: dict,
) -> dict:

    normalized = normalize_match(match)

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

    # --------------------------------------------------------
    # Keep individual sections directly on match
    # --------------------------------------------------------

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
        odds.get("other_market_odds", [])
    )

    # --------------------------------------------------------
    # Combined markets
    # --------------------------------------------------------

    markets = []

    for market in normalized["match_odds"]:

        markets.append(
            {
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
            }
        )

    for market in normalized["bookmaker_odds"]:

        markets.append(
            {
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
            }
        )

    for market in normalized["fancy_odds"]:

        markets.append(
            {
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
            }
        )

    normalized["markets"] = markets

    # Useful debugging counters for template/JS.
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


# ============================================================
# RESOLVE MATCH
# ============================================================

def resolve_match(
    game_id: str,
) -> tuple[
    dict | None,
    str | None,
    str | None,
]:

    matches = proexch_api.get_matches()

    if not isinstance(matches, list):
        matches = []

    match = find_match(
        matches,
        game_id,
    )

    if not match:
        return None, None, None

    event_id, market_id = get_match_ids(
        match
    )

    return (
        match,
        event_id,
        market_id,
    )


# ============================================================
# API - MATCHES
# ============================================================

@router.get("/api/cricket/matches")
async def cricket_matches(
    request: Request,
):

    if not is_logged_in(request):
        return unauthorized()

    try:

        matches = proexch_api.get_matches()

        if not isinstance(matches, list):
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
                "error": "Unable to load cricket matches",
            },
        )


# ============================================================
# API - ODDS
# ============================================================

@router.get("/api/cricket/odds")
async def cricket_odds(
    request: Request,

    gameId: str | None = None,
    eventId: str | None = None,
    marketId: str | None = None,

    game_id: str | None = None,
    event_id: str | None = None,
    market_id: str | None = None,
):

    if not is_logged_in(request):
        return unauthorized()

    game_id = clean(
        gameId or game_id
    )

    event_id = clean(
        eventId or event_id
    )

    market_id = clean(
        marketId or market_id
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

        # ----------------------------------------------------
        # Resolve IDs when required
        # ----------------------------------------------------

        if not event_id or not market_id:

            matches = proexch_api.get_matches()

            if not isinstance(matches, list):
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

            discovered_event_id, discovered_market_id = (
                get_match_ids(match)
            )

            if not event_id:
                event_id = discovered_event_id

            if not market_id:
                market_id = discovered_market_id

        if not event_id:

            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": (
                        "event_id could not be determined "
                        "from ProExch match data"
                    ),
                },
            )

        print(
            "[CRICKET] calling ProExch:",
            "gameId=", game_id,
            "eventId=", event_id,
            "marketId=", market_id,
        )

        # ----------------------------------------------------
        # Get odds
        # ----------------------------------------------------

        raw_odds = proexch_api.get_odds(
            game_id=game_id,
            event_id=event_id,
            market_id=market_id,
        )

        normalized = normalize_odds(
            raw_odds
        )

        print(
            "[CRICKET] odds received:",
            "match_markets=",
            len(normalized["match_odds"]),
            "match_runners=",
            sum(
                len(m.get("runners", []))
                for m in normalized["match_odds"]
            ),
            "bookmaker_markets=",
            len(normalized["bookmaker_odds"]),
            "fancy_markets=",
            len(normalized["fancy_odds"]),
        )

        return {
            "success": True,

            "game_id": game_id,
            "event_id": event_id,
            "market_id": market_id,

            "match_odds": normalized[
                "match_odds"
            ],

            "bookmaker_odds": normalized[
                "bookmaker_odds"
            ],

            "fancy_odds": normalized[
                "fancy_odds"
            ],

            "other_market_odds": normalized[
                "other_market_odds"
            ],

            # Compatibility aliases.
            "matchOdds": normalized[
                "match_odds"
            ],

            "bookMakerOdds": normalized[
                "bookmaker_odds"
            ],

            "fancyOdds": normalized[
                "fancy_odds"
            ],

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


# ============================================================
# API - SINGLE MATCH
# ============================================================

@router.get("/api/cricket/match/{game_id}")
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

        match, event_id, market_id = resolve_match(
            game_id
        )

        if not match:

            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "Match not found",
                },
            )

        if not event_id:

            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "eventId not available from ProExch",
                },
            )

        raw_odds = proexch_api.get_odds(
            game_id=game_id,
            event_id=event_id,
            market_id=market_id,
        )

        normalized_odds = normalize_odds(
            raw_odds
        )

        page_match = build_match_page_data(
            match,
            normalized_odds,
        )

        return {
            "success": True,

            "game_id": game_id,
            "event_id": event_id,
            "market_id": market_id,

            "match": page_match,

            "match_odds": normalized_odds[
                "match_odds"
            ],

            "bookmaker_odds": normalized_odds[
                "bookmaker_odds"
            ],

            "fancy_odds": normalized_odds[
                "fancy_odds"
            ],

            "other_market_odds": normalized_odds[
                "other_market_odds"
            ],

            "odds": normalized_odds["raw"],
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


# ============================================================
# HTML - MATCH PAGE
# ============================================================

@router.get("/match/{game_id}")
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

        # ----------------------------------------------------
        # Resolve match
        # ----------------------------------------------------

        match, event_id, market_id = resolve_match(
            game_id
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
                        "The requested cricket match "
                        "could not be found."
                    ),
                },
            )

        if not event_id:

            return templates.TemplateResponse(
                "match.html",
                {
                    "request": request,
                    "match": None,
                    "error": (
                        "ProExch did not return an "
                        "event ID for this match."
                    ),
                },
            )

        # ----------------------------------------------------
        # Initial odds
        # ----------------------------------------------------

        print(
            "[CRICKET] requesting initial odds:",
            game_id,
            event_id,
            market_id,
        )

        raw_odds = proexch_api.get_odds(
            game_id=game_id,
            event_id=event_id,
            market_id=market_id,
        )

        normalized_odds = normalize_odds(
            raw_odds
        )

        print(
            "[CRICKET] initial odds:",
            "match_markets=",
            len(normalized_odds["match_odds"]),
            "match_runners=",
            sum(
                len(m.get("runners", []))
                for m in normalized_odds["match_odds"]
            ),
            "bookmaker_markets=",
            len(normalized_odds["bookmaker_odds"]),
            "fancy_markets=",
            len(normalized_odds["fancy_odds"]),
            "raw_type=",
            type(raw_odds).__name__,
        )

        # ----------------------------------------------------
        # Build page structure
        # ----------------------------------------------------

        page_match = build_match_page_data(
            match,
            normalized_odds,
        )

        # ----------------------------------------------------
        # Send BOTH structures to template
        # ----------------------------------------------------

        return templates.TemplateResponse(
            "match.html",
            {
                "request": request,

                "match": page_match,

                "game_id": game_id,
                "event_id": event_id,
                "market_id": market_id,

                "odds": normalized_odds,

                # Direct aliases useful to Jinja templates.
                "match_odds": normalized_odds[
                    "match_odds"
                ],

                "bookmaker_odds": normalized_odds[
                    "bookmaker_odds"
                ],

                "fancy_odds": normalized_odds[
                    "fancy_odds"
                ],

                "other_market_odds": normalized_odds[
                    "other_market_odds"
                ],

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
                    "Unable to load this cricket match: "
                    + str(exc)
                ),

                "odds_error": str(exc),
            },
        )