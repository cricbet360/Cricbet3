
import time
from typing import Any, Dict, List, Optional

import requests


# =========================================================
# CONFIGURATION
# =========================================================

BASE_URL = "https://apidata.proexch.in"

REQUEST_TIMEOUT = 8
MAX_RETRIES = 2

# Cache durations
MATCH_CACHE_TTL = 15.0
ODDS_CACHE_TTL = 2.0

# Leave empty when your server IP is whitelisted.
PROXY = ""


# =========================================================
# CRICKETBZ SCORE / RESULT PROVIDER
# =========================================================
# These endpoints are called by the backend only.
# The browser never calls cricketbz.app directly.

CRICKETBZ_BASE_URL = "https://cricketbz.app"


# =========================================================
# HTTP SESSION
# =========================================================

session = requests.Session()

session.headers.update(
    {
        "User-Agent": "CrickBet/1.0",
        "Accept": "application/json",
        "Connection": "keep-alive",
    }
)

if PROXY:
    session.proxies.update(
        {
            "http": PROXY,
            "https": PROXY,
        }
    )


# =========================================================
# CACHE
# =========================================================

_matches_cache: Dict[str, Any] = {
    "timestamp": 0.0,
    "data": [],
}

_odds_cache: Dict[str, Dict[str, Any]] = {}


# =========================================================
# HELPERS
# =========================================================

def _now() -> float:
    return time.monotonic()


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    try:
        value = str(value).strip()

        if value in ("", "-", "null", "None"):
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None

    try:
        return int(value)

    except (TypeError, ValueError):
        return None


# =========================================================
# PROEXCH REQUEST
# =========================================================

def _request(
    path: str,
    params: Optional[Dict[str, Any]] = None,
) -> Any:

    url = f"{BASE_URL}{path}"

    last_error = None

    for attempt in range(MAX_RETRIES + 1):

        try:

            response = session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            return response.json()

        except Exception as exc:

            last_error = exc

            if attempt < MAX_RETRIES:
                time.sleep(0.25 * (attempt + 1))

    raise RuntimeError(
        f"ProExch request failed: {last_error}"
    )


# =========================================================
# CRICKETBZ REQUEST
# =========================================================

def _request_cricketbz(
    url: str,
) -> Any:
    """
    Fetch CricketBZ response through the backend.

    The provider may return JSON or plain text.
    Both formats are preserved.
    """

    try:

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "User-Agent": "CrickBet/1.0",
            },
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get("content-type", "")
            .lower()
        )

        if "json" in content_type:

            try:
                return response.json()

            except ValueError:
                pass

        try:
            return response.json()

        except ValueError:
            return response.text

    except Exception as exc:

        raise RuntimeError(
            "CricketBZ request failed: "
            f"{exc}"
        ) from exc


# =========================================================
# CRICKETBZ SCORE
# =========================================================

def get_score(
    score_id: str,
) -> Any:
    """
    Get live scoreboard data from CricketBZ.

    Endpoint:
        https://cricketbz.app/getScore/<score_id>
    """

    score_id = str(score_id).strip()

    if not score_id:
        raise ValueError(
            "score_id is required"
        )

    url = (
        f"{CRICKETBZ_BASE_URL}"
        f"/getScore/{score_id}"
    )

    return _request_cricketbz(url)


# =========================================================
# CRICKETBZ RESULT
# =========================================================

def get_cricketbz_result(
    result_id: str,
) -> Any:
    """
    Get match/result data from CricketBZ.

    Endpoint:
        https://cricketbz.app/getResults/<result_id>

    IMPORTANT:
    This has a different function name from the ProExch
    betfair-result endpoint so there is no function collision.
    """

    result_id = str(result_id).strip()

    if not result_id:
        raise ValueError(
            "result_id is required"
        )

    url = (
        f"{CRICKETBZ_BASE_URL}"
        f"/getResults/{result_id}"
    )

    return _request_cricketbz(url)


# =========================================================
# PROEXCH RESULT
# =========================================================

def get_proexch_result(
    market_id: str,
) -> Any:
    """
    Get result/settlement information from ProExch.

    Endpoint:
        /api/betfair-result
    """

    market_id = str(market_id).strip()

    if not market_id:
        raise ValueError(
            "market_id is required"
        )

    return _request(
        "/api/betfair-result",
        params={
            "sport": "cricket",
            "type": "new_fancy",
            "marketId": market_id,
        },
    )


# =========================================================
# MATCH RESPONSE UNWRAPPER
# =========================================================

def _unwrap_matches(
    payload: Any,
) -> List[Dict[str, Any]]:

    if not isinstance(payload, dict):
        return []

    data = payload.get("data")

    if isinstance(data, dict):
        data = data.get("data", [])

    if isinstance(data, list):
        return data

    return []


# =========================================================
# ODDS RESPONSE UNWRAPPER
# =========================================================

def _unwrap_odds(
    payload: Any,
) -> Dict[str, Any]:

    if not isinstance(payload, dict):
        return {}

    data = payload.get("data")

    if isinstance(data, dict):
        return data

    return {}


# =========================================================
# MATCHES
# =========================================================

def get_matches(
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:

    global _matches_cache

    current = _now()

    if (
        not force_refresh
        and _matches_cache["data"]
        and (
            current
            - _matches_cache["timestamp"]
        ) < MATCH_CACHE_TTL
    ):
        return _matches_cache["data"]

    payload = _request(
        "/api/cricket/matches"
    )

    raw_matches = _unwrap_matches(
        payload
    )

    matches: List[Dict[str, Any]] = []

    for item in raw_matches:

        if not isinstance(item, dict):
            continue

        game_id = (
            item.get("gameId")
            or item.get("game_id")
            or item.get("id")
        )

        market_id = (
            item.get("marketId")
            or item.get("market_id")
        )

        event_id = (
            item.get("eventId")
            or item.get("event_id")
            or game_id
        )

        event_name = (
            item.get("eventName")
            or item.get("event_name")
            or "Cricket Match"
        )

        event_time = (
            item.get("eventTime")
            or item.get("event_time")
        )

        team1 = (
            item.get("runnerName1")
            or item.get("team1")
            or ""
        )

        team2 = (
            item.get("runnerName2")
            or item.get("team2")
            or ""
        )

        team3 = (
            item.get("runnerName3")
            or item.get("team3")
            or ""
        )

        in_play = item.get("inPlay")

        tv = item.get("tv")

        # -------------------------------------------------
        # Optional score/result identifiers.
        #
        # If ProExch supplies these, use them.
        # Otherwise leave empty so the frontend/backend
        # can fall back to game_id.
        # -------------------------------------------------

        score_id = (
            item.get("scoreId")
            or item.get("score_id")
        )

        result_id = (
            item.get("resultId")
            or item.get("result_id")
        )

        normalized = {
            "game_id": (
                str(game_id)
                if game_id is not None
                else ""
            ),

            "market_id": (
                str(market_id)
                if market_id is not None
                else ""
            ),

            "event_id": (
                str(event_id)
                if event_id is not None
                else ""
            ),

            "event_name": str(
                event_name
            ),

            "event_time": event_time,

            "in_play": bool(
                in_play
            ),

            "tv": tv,

            "score_id": (
                str(score_id)
                if score_id is not None
                else ""
            ),

            "result_id": (
                str(result_id)
                if result_id is not None
                else ""
            ),

            "team1": str(team1),
            "team2": str(team2),
            "team3": str(team3),

            "raw": item,
        }

        if normalized["game_id"]:
            matches.append(
                normalized
            )

    _matches_cache = {
        "timestamp": current,
        "data": matches,
    }

    print(
        "[PROEXCH] matches refreshed: "
        f"{len(matches)}"
    )

    return matches


# =========================================================
# FIND MATCH
# =========================================================

def find_match(
    game_id: str,
) -> Optional[Dict[str, Any]]:

    game_id = str(
        game_id
    ).strip()

    matches = get_matches()

    for match in matches:

        if (
            str(match.get("game_id"))
            == game_id
        ):
            return match

    return None


# =========================================================
# GET MATCH IDS
# =========================================================

def get_match_ids(
    game_id: str,
) -> Dict[str, str]:

    game_id = str(
        game_id
    ).strip()

    match = find_match(
        game_id
    )

    if not match:

        return {
            "game_id": game_id,
            "event_id": game_id,
            "market_id": "",
            "score_id": game_id,
            "result_id": game_id,
        }

    return {
        "game_id": str(
            match.get(
                "game_id"
            )
            or game_id
        ),

        "event_id": str(
            match.get(
                "event_id"
            )
            or game_id
        ),

        "market_id": str(
            match.get(
                "market_id"
            )
            or ""
        ),

        "score_id": str(
            match.get(
                "score_id"
            )
            or match.get(
                "game_id"
            )
            or game_id
        ),

        "result_id": str(
            match.get(
                "result_id"
            )
            or match.get(
                "game_id"
            )
            or game_id
        ),
    }


# =========================================================
# ODDS
# =========================================================

def get_odds(
    game_id: str,
    event_id: Optional[str] = None,
    market_id: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:

    game_id = str(
        game_id
    ).strip()

    if not market_id:

        ids = get_match_ids(
            game_id
        )

        market_id = ids.get(
            "market_id"
        )

        if not event_id:
            event_id = ids.get(
                "event_id"
            )

    if not market_id:

        raise ValueError(
            "Market ID not found for "
            f"gameId={game_id}"
        )

    market_id = str(
        market_id
    )

    cache_key = (
        f"{game_id}:{market_id}"
    )

    current = _now()

    cached = _odds_cache.get(
        cache_key
    )

    if (
        not force_refresh
        and cached
        and (
            current
            - cached["timestamp"]
        ) < ODDS_CACHE_TTL
    ):
        return cached["data"]

    print(
        "[PROEXCH] odds request: "
        f"gameId={game_id} "
        f"marketId={market_id}"
    )

    payload = _request(
        "/api/cricket/odds",
        params={
            "gameId": game_id,
            "marketId": market_id,
        },
    )

    normalized = normalize_odds(
        payload
    )

    _odds_cache[cache_key] = {
        "timestamp": current,
        "data": normalized,
    }

    return normalized


# =========================================================
# MATCH ODDS
# =========================================================

def parse_match_odds(
    markets: Any,
) -> List[Dict[str, Any]]:

    result: List[Dict[str, Any]] = []

    if not isinstance(
        markets,
        list,
    ):
        return result

    for market in markets:

        if not isinstance(
            market,
            dict,
        ):
            continue

        odd_datas = market.get(
            "oddDatas"
        )

        if not isinstance(
            odd_datas,
            list,
        ):
            odd_datas = []

        runners = []

        for runner in odd_datas:

            if not isinstance(
                runner,
                dict,
            ):
                continue

            back1 = _safe_float(
                runner.get("b1")
            )

            back2 = _safe_float(
                runner.get("b2")
            )

            back3 = _safe_float(
                runner.get("b3")
            )

            lay1 = _safe_float(
                runner.get("l1")
            )

            lay2 = _safe_float(
                runner.get("l2")
            )

            lay3 = _safe_float(
                runner.get("l3")
            )

            normalized_runner = {
                "id": runner.get(
                    "sid"
                ),

                "sid": runner.get(
                    "sid"
                ),

                "name": (
                    runner.get("rname")
                    or runner.get(
                        "runnerName"
                    )
                    or "Runner"
                ),

                "status": runner.get(
                    "status"
                ),

                "back": back1,

                "back_size": _safe_float(
                    runner.get("bs1")
                ),

                "back2": back2,

                "back2_size": _safe_float(
                    runner.get("bs2")
                ),

                "back3": back3,

                "back3_size": _safe_float(
                    runner.get("bs3")
                ),

                "lay": lay1,

                "lay_size": _safe_float(
                    runner.get("ls1")
                ),

                "lay2": lay2,

                "lay2_size": _safe_float(
                    runner.get("ls2")
                ),

                "lay3": lay3,

                "lay3_size": _safe_float(
                    runner.get("ls3")
                ),

                "raw": runner,
            }

            runners.append(
                normalized_runner
            )

        result.append(
            {
                "id": (
                    market.get("mid")
                    or market.get(
                        "marketId"
                    )
                ),

                "name": (
                    market.get("market")
                    or market.get("mname")
                    or "Match Odds"
                ),

                "status": (
                    market.get("mstatus")
                    or market.get("status")
                    or "OPEN"
                ),

                "type": "match_odds",

                "runners": runners,

                "outcomes": runners,

                "raw": market,
            }
        )

    return result


# =========================================================
# BOOKMAKER
# =========================================================

def parse_bookmaker_odds(
    markets: Any,
) -> List[Dict[str, Any]]:

    result: List[Dict[str, Any]] = []

    if not isinstance(
        markets,
        list,
    ):
        return result

    for market in markets:

        if not isinstance(
            market,
            dict,
        ):
            continue

        odd_datas = market.get(
            "oddDatas"
        )

        if not isinstance(
            odd_datas,
            list,
        ):
            odd_datas = []

        runners = []

        for runner in odd_datas:

            if not isinstance(
                runner,
                dict,
            ):
                continue

            back = _safe_float(
                runner.get("b1")
            )

            lay = _safe_float(
                runner.get("l1")
            )

            normalized_runner = {
                "id": runner.get(
                    "sid"
                ),

                "sid": runner.get(
                    "sid"
                ),

                "name": (
                    runner.get("rname")
                    or runner.get(
                        "runnerName"
                    )
                    or "Runner"
                ),

                "status": runner.get(
                    "status"
                ),

                "back": back,

                "back_size": _safe_float(
                    runner.get("bs1")
                ),

                "lay": lay,

                "lay_size": _safe_float(
                    runner.get("ls1")
                ),

                "raw": runner,
            }

            runners.append(
                normalized_runner
            )

        result.append(
            {
                "id": (
                    market.get("mid")
                    or market.get(
                        "marketId"
                    )
                ),

                "name": (
                    market.get("market")
                    or market.get("mname")
                    or "Bookmaker"
                ),

                "status": (
                    market.get("mstatus")
                    or market.get("status")
                    or "OPEN"
                ),

                "type": "bookmaker",

                "runners": runners,

                "outcomes": runners,

                "raw": market,
            }
        )

    return result


# =========================================================
# FANCY / SESSION
# =========================================================

def parse_fancy_odds(
    markets: Any,
) -> List[Dict[str, Any]]:

    result: List[Dict[str, Any]] = []

    if not isinstance(
        markets,
        list,
    ):
        return result

    for market in markets:

        if not isinstance(
            market,
            dict,
        ):
            continue

        odd_datas = market.get(
            "oddDatas"
        )

        if not isinstance(
            odd_datas,
            list,
        ):
            odd_datas = []

        rows = []

        for runner in odd_datas:

            if not isinstance(
                runner,
                dict,
            ):
                continue

            yes = _safe_float(
                runner.get("b1")
            )

            yes_size = _safe_float(
                runner.get("bs1")
            )

            no = _safe_float(
                runner.get("l1")
            )

            no_size = _safe_float(
                runner.get("ls1")
            )

            name = (
                runner.get("rname")
                or runner.get(
                    "runnerName"
                )
                or runner.get("name")
                or "Session"
            )

            row = {
                "id": runner.get(
                    "sid"
                ),

                "sid": runner.get(
                    "sid"
                ),

                "name": str(name),

                "status": runner.get(
                    "status"
                ),

                "yes": yes,

                "yes_size": yes_size,

                "no": no,

                "no_size": no_size,

                "back": yes,

                "back_size": yes_size,

                "lay": no,

                "lay_size": no_size,

                "raw": runner,
            }

            rows.append(
                row
            )

        market_name = (
            market.get("market")
            or market.get("mname")
            or market.get("name")
            or "Fancy / Session"
        )

        normalized_market = {
            "id": (
                market.get("mid")
                or market.get(
                    "marketId"
                )
            ),

            "name": str(
                market_name
            ),

            "status": (
                market.get("mstatus")
                or market.get("status")
                or "OPEN"
            ),

            "type": "fancy",

            "rows": rows,

            "runners": rows,

            "outcomes": rows,

            "raw": market,
        }

        result.append(
            normalized_market
        )

    return result


# =========================================================
# NORMALIZE ALL ODDS
# =========================================================

def normalize_odds(
    payload: Any,
) -> Dict[str, Any]:

    data = _unwrap_odds(
        payload
    )

    match_markets = data.get(
        "matchOdds",
        [],
    )

    bookmaker_markets = (
        data.get(
            "bookMakerOdds"
        )
        or data.get(
            "bookmakerOdds"
        )
        or data.get(
            "bookmaker_odds"
        )
        or []
    )

    fancy_markets = data.get(
        "fancyOdds",
        [],
    )

    other_markets = data.get(
        "otherMarketOdds",
        [],
    )

    match_odds = parse_match_odds(
        match_markets
    )

    bookmaker_odds = (
        parse_bookmaker_odds(
            bookmaker_markets
        )
    )

    fancy_odds = parse_fancy_odds(
        fancy_markets
    )

    normalized = {
        "match_odds": match_odds,

        "bookmaker_odds":
            bookmaker_odds,

        "fancy_odds":
            fancy_odds,

        "other_market_odds": (
            other_markets
            if isinstance(
                other_markets,
                list,
            )
            else []
        ),

        "counts": {
            "match_markets":
                len(match_odds),

            "match_runners":
                sum(
                    len(
                        x.get(
                            "runners",
                            [],
                        )
                    )
                    for x in match_odds
                ),

            "bookmaker_markets":
                len(
                    bookmaker_odds
                ),

            "bookmaker_runners":
                sum(
                    len(
                        x.get(
                            "runners",
                            [],
                        )
                    )
                    for x in bookmaker_odds
                ),

            "fancy_markets":
                len(fancy_odds),

            "fancy_rows":
                sum(
                    len(
                        x.get(
                            "rows",
                            [],
                        )
                    )
                    for x in fancy_odds
                ),

            "other_markets":
                len(
                    other_markets
                    if isinstance(
                        other_markets,
                        list,
                    )
                    else []
                ),
        },

        "raw": data,
    }

    return normalized


# =========================================================
# CACHE MANAGEMENT
# =========================================================

def clear_cache() -> None:

    global _matches_cache

    _matches_cache = {
        "timestamp": 0.0,
        "data": [],
    }

    _odds_cache.clear()

    print(
        "[PROEXCH] cache cleared"
    )


def clear_odds_cache(
    game_id: Optional[str] = None,
) -> None:

    if game_id is None:

        _odds_cache.clear()

        return

    game_id = str(
        game_id
    )

    keys = [
        key
        for key in _odds_cache
        if key.startswith(
            f"{game_id}:"
        )
    ]

    for key in keys:

        _odds_cache.pop(
            key,
            None
        )


# =========================================================
# PROEXCH CRICKETBZ DATA
# =========================================================

def get_cricketbz(
    game_id: str,
) -> Any:

    try:

        return _request(
            "/api/cricket/cricketbz",
            params={
                "gameId": str(
                    game_id
                ),
            },
        )

    except Exception as exc:

        print(
            "[PROEXCH] cricketbz error:",
            exc
        )

        return None


# =========================================================
# PROEXCH VIDEO
# =========================================================

def get_video(
    game_id: str,
) -> Any:

    try:

        return _request(
            "/api/cricket/video",
            params={
                "gameId": str(
                    game_id
                ),
            },
        )

    except Exception as exc:

        print(
            "[PROEXCH] video error:",
            exc
        )

        return None

