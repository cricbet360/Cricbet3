import re
import time
from typing import Any, Dict, List, Optional

import requests


# =========================================================
# CONFIGURATION
# =========================================================

BASE_URL = "https://apidata.proexch.in"

REQUEST_TIMEOUT = 8
MAX_RETRIES = 2

MATCH_CACHE_TTL = 15.0
ODDS_CACHE_TTL = 2.0
SCORE_CACHE_TTL = 3.0
RESULT_CACHE_TTL = 10.0

# Leave empty when your server IP is whitelisted.
PROXY = ""

# CricketBZ live score source
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

_matches_cache = {
    "timestamp": 0.0,
    "data": [],
}

_odds_cache: Dict[str, Dict[str, Any]] = {}
_score_cache: Dict[str, Dict[str, Any]] = {}
_result_cache: Dict[str, Dict[str, Any]] = {}


# =========================================================
# BASIC HELPERS
# =========================================================

def _now() -> float:
    return time.time()


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, bool):
        return float(value)

    try:
        text = str(value).strip()

        if not text:
            return None

        text = text.replace(",", "")

        return float(text)

    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None

    if isinstance(value, bool):
        return int(value)

    try:
        text = str(value).strip()

        if not text:
            return None

        text = text.replace(",", "")

        return int(float(text))

    except Exception:
        return None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    text = str(value or "").strip().lower()

    return text in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "live",
        "inplay",
        "in_play",
        "over",
    }


def _first_value(
    data: Dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    for key in keys:
        if key in data:
            value = data.get(key)

            if value is not None and value != "":
                return value

    return default


def _format_number(value: Any) -> str:
    number = _safe_float(value)

    if number is None:
        return ""

    if number.is_integer():
        return str(int(number))

    return f"{number:.2f}".rstrip("0").rstrip(".")


def _format_score(
    runs: Any,
    wickets: Any = None,
) -> str:
    runs_text = _format_number(runs)

    if not runs_text:
        return ""

    wickets_text = _format_number(wickets)

    if wickets_text:
        return f"{runs_text}-{wickets_text}"

    return runs_text


# =========================================================
# OVERS HELPERS
# =========================================================

def _parse_overs(value: Any) -> Optional[float]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    match = re.match(
        r"^\s*(\d+)(?:\.(\d+))?\s*$",
        text,
    )

    if not match:
        return _safe_float(value)

    overs = int(match.group(1))
    balls_text = match.group(2)

    if not balls_text:
        return float(overs)

    try:
        balls = int(balls_text)
    except Exception:
        return float(overs)

    if 0 <= balls <= 5:
        return overs + (balls / 6.0)

    return float(overs)


def _overs_display(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    match = re.match(
        r"^\s*(\d+)(?:\.(\d+))?\s*$",
        text,
    )

    if match:
        overs = match.group(1)
        balls = match.group(2)

        if balls is None:
            return f"{overs}.0"

        return f"{overs}.{balls}"

    number = _safe_float(value)

    if number is None:
        return text

    return f"{number:.1f}"


# =========================================================
# PROEXCH REQUEST
# =========================================================

def _request(
    path: str,
    params: Optional[Dict[str, Any]] = None,
) -> Any:

    url = f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"

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

    last_error = None

    headers = {
        "User-Agent": "CrickBet/1.0",
        "Accept": "application/json,text/plain,*/*",
        "Connection": "keep-alive",
    }

    for attempt in range(MAX_RETRIES + 1):

        try:

            response = session.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            try:
                return response.json()

            except Exception:

                text = response.text.strip()

                if not text:
                    return None

                return text

        except Exception as exc:

            last_error = exc

            if attempt < MAX_RETRIES:
                time.sleep(0.25 * (attempt + 1))

    raise RuntimeError(
        f"CricketBZ request failed: {last_error}"
    )


# =========================================================
# GENERIC UNWRAP
# =========================================================

def _unwrap_generic(
    payload: Any,
) -> Any:

    current = payload

    for _ in range(6):

        if not isinstance(current, dict):
            break

        found = False

        for key in (
            "data",
            "result",
            "response",
            "body",
            "payload",
        ):

            value = current.get(key)

            if value is not None:

                current = value
                found = True
                break

        if not found:
            break

    return current


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

        inner = data.get("data")

        if isinstance(inner, list):
            return inner

        if isinstance(inner, dict):
            return [inner]

    if isinstance(data, list):
        return data

    for key in (
        "result",
        "matches",
        "events",
    ):

        value = payload.get(key)

        if isinstance(value, list):
            return value

    return []


# =========================================================
# RECURSIVE VALUE FINDER
# =========================================================

def _find_value(
    data: Any,
    keys: List[str],
) -> Any:

    if isinstance(data, dict):

        lowered = {
            str(k).lower(): v
            for k, v in data.items()
        }

        for key in keys:

            value = lowered.get(
                str(key).lower()
            )

            if value is not None and value != "":
                return value

        for value in data.values():

            found = _find_value(
                value,
                keys,
            )

            if found is not None:
                return found

    elif isinstance(data, list):

        for item in data:

            found = _find_value(
                item,
                keys,
            )

            if found is not None:
                return found

    return None


# =========================================================
# MATCHES
# =========================================================

def get_matches(
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:

    global _matches_cache

    now = _now()

    if (
        not force_refresh
        and _matches_cache["data"]
        and (
            now
            - _matches_cache["timestamp"]
        )
        <= MATCH_CACHE_TTL
    ):
        return _matches_cache["data"]

    payload = _request(
        "/api/cricket/matches"
    )

    items = _unwrap_matches(
        payload
    )

    matches: List[Dict[str, Any]] = []

    for item in items:

        if not isinstance(item, dict):
            continue

        game_id = _first_value(
            item,
            "gameId",
            "gameID",
            "game_id",
        )

        market_id = _first_value(
            item,
            "marketId",
            "marketID",
            "market_id",
        )

        event_id = _first_value(
            item,
            "eventId",
            "eventID",
            "event_id",
        )

        event_name = _first_value(
            item,
            "eventName",
            "event_name",
            "name",
        )

        event_time = _first_value(
            item,
            "eventTime",
            "event_time",
            "startTime",
            "start_time",
        )

        in_play = _first_value(
            item,
            "inPlay",
            "inplay",
            "in_play",
            "isLive",
            "live",
        )

        tv = _first_value(
            item,
            "tv",
            "TV",
        )

        score_id = _first_value(
            item,
            "scoreId",
            "scoreID",
            "score_id",
            "scoreid",
            "gameId",
            "gameID",
            "game_id",
            "eventId",
            "eventID",
            "event_id",
        )

        result_id = _first_value(
            item,
            "resultId",
            "resultID",
            "result_id",
            "gameId",
            "gameID",
            "game_id",
        )

        team1 = _first_value(
            item,
            "runnerName1",
            "runner1",
            "team1",
            "teamName1",
        )

        team2 = _first_value(
            item,
            "runnerName2",
            "runner2",
            "team2",
            "teamName2",
        )

        team3 = _first_value(
            item,
            "runnerName3",
            "runner3",
            "team3",
            "teamName3",
        )

        if game_id is None:
            continue

        matches.append(
            {
                "game_id": str(game_id),

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

                "event_name": (
                    str(event_name)
                    if event_name is not None
                    else ""
                ),

                "event_time": (
                    str(event_time)
                    if event_time is not None
                    else ""
                ),

                "in_play": _as_bool(in_play),

                "tv": tv,

                "score_id": (
                    str(score_id)
                    if score_id is not None
                    else str(game_id)
                ),

                "result_id": (
                    str(result_id)
                    if result_id is not None
                    else str(game_id)
                ),

                "team1": (
                    str(team1)
                    if team1 is not None
                    else ""
                ),

                "team2": (
                    str(team2)
                    if team2 is not None
                    else ""
                ),

                "team3": (
                    str(team3)
                    if team3 is not None
                    else ""
                ),

                "raw": item,
            }
        )

    _matches_cache = {
        "timestamp": now,
        "data": matches,
    }

    print(
        f"[PROEXCH] Matches loaded: {len(matches)}"
    )

    return matches


# =========================================================
# FIND MATCH
# =========================================================

def find_match(
    game_id: Any,
) -> Optional[Dict[str, Any]]:

    game_id = str(
        game_id or ""
    ).strip()

    if not game_id:
        return None

    matches = get_matches()

    for match in matches:

        if (
            str(
                match.get(
                    "game_id",
                    "",
                )
            )
            == game_id
        ):
            return match

    return None


# =========================================================
# MATCH IDS
# =========================================================

def get_match_ids(
    game_id: Any,
) -> Dict[str, str]:

    game_id = str(
        game_id or ""
    ).strip()

    match = find_match(
        game_id
    )

    if match:

        return {
            "game_id": game_id,

            "event_id": str(
                match.get(
                    "event_id",
                    "",
                )
            ),

            "market_id": str(
                match.get(
                    "market_id",
                    "",
                )
            ),

            "score_id": str(
                match.get("score_id")
                or game_id
            ),

            "result_id": str(
                match.get("result_id")
                or game_id
            ),
        }

    return {
        "game_id": game_id,
        "event_id": game_id,
        "market_id": "",
        "score_id": game_id,
        "result_id": game_id,
    }


# =========================================================
# ODDS UNWRAPPER
# =========================================================

def _unwrap_odds(
    payload: Any,
) -> Any:

    current = payload

    for _ in range(7):

        if not isinstance(current, dict):
            break

        if (
            "matchOdds" in current
            or "match_odds" in current
            or "bookmakerOdds" in current
            or "bookmaker_odds" in current
            or "fancyOdds" in current
            or "fancy_odds" in current
            or "oddDatas" in current
            or "runners" in current
        ):
            return current

        found = False

        for key in (
            "data",
            "result",
            "response",
            "body",
            "payload",
        ):

            value = current.get(key)

            if value is not None:

                current = value
                found = True
                break

        if not found:
            break

    return current


# =========================================================
# MATCH ODDS
# =========================================================

def parse_match_odds(
    data: Any,
) -> List[Dict[str, Any]]:

    if not isinstance(data, dict):
        return []

    match_odds = data.get("matchOdds")

    if match_odds is None:
        match_odds = data.get("match_odds")

    if isinstance(match_odds, dict):
        match_odds = [match_odds]

    if not isinstance(match_odds, list):
        return []

    result = []

    for market in match_odds:

        if not isinstance(market, dict):
            continue

        # Support already-normalized direct runner objects.
        direct_runner = (
            (
                "id" in market
                or "selectionId" in market
                or "sid" in market
            )
            and (
                "b1" in market
                or "back" in market
                or "backPrice" in market
            )
        )

        if direct_runner:

            runner_list = [market]

            market_id = str(
                _first_value(
                    market,
                    "marketId",
                    "id",
                    default="",
                )
            )

            market_name = str(
                _first_value(
                    market,
                    "marketName",
                    "name",
                    default="Match Odds",
                )
            )

        else:

            runner_list = market.get(
                "oddDatas"
            )

            if runner_list is None:
                runner_list = market.get(
                    "runners"
                )

            if isinstance(runner_list, dict):
                runner_list = [runner_list]

            if not isinstance(runner_list, list):
                runner_list = []

            market_id = str(
                _first_value(
                    market,
                    "id",
                    "marketId",
                    default="",
                )
            )

            market_name = str(
                _first_value(
                    market,
                    "name",
                    "marketName",
                    default="Match Odds",
                )
            )

        runners = []

        for runner in runner_list:

            if not isinstance(runner, dict):
                continue

            runner_id = _first_value(
                runner,
                "id",
                "selectionId",
                "selection_id",
                "sid",
                default="",
            )

            runner_name = _first_value(
                runner,
                "rname",
                "runnerName",
                "runner_name",
                "name",
                default="",
            )

            runners.append(
                {
                    "id": str(
                        runner_id
                    ),

                    "name": str(
                        runner_name
                    ),

                    "back": _safe_float(
                        _first_value(
                            runner,
                            "b1",
                            "back",
                            "backPrice",
                            "back_price",
                        )
                    ),

                    "back_size": _safe_float(
                        _first_value(
                            runner,
                            "bs1",
                            "backSize",
                            "back_size",
                            "back_volume",
                        )
                    ),

                    "lay": _safe_float(
                        _first_value(
                            runner,
                            "l1",
                            "lay",
                            "layPrice",
                            "lay_price",
                        )
                    ),

                    "lay_size": _safe_float(
                        _first_value(
                            runner,
                            "ls1",
                            "laySize",
                            "lay_size",
                            "lay_volume",
                        )
                    ),

                    "raw": runner,
                }
            )

        result.append(
            {
                "id": market_id,

                "name": market_name,

                "status": str(
                    _first_value(
                        market,
                        "status",
                        default="OPEN",
                    )
                ),

                "type": "match_odds",

                "runners": runners,

                "raw": market,
            }
        )

    return result


# =========================================================
# BOOKMAKER ODDS
# =========================================================

def parse_bookmaker_odds(
    data: Any,
) -> List[Dict[str, Any]]:

    if not isinstance(data, dict):
        return []

    bookmaker = (
        data.get("bookmakerOdds")
        or data.get("bookmaker_odds")
        or data.get("bookMakerOdds")
        or data.get("bookmaker")
    )

    if isinstance(bookmaker, dict):
        bookmaker = [bookmaker]

    if not isinstance(bookmaker, list):
        return []

    result = []

    for market in bookmaker:

        if not isinstance(market, dict):
            continue

        direct_runner = (
            (
                "id" in market
                or "selectionId" in market
            )
            and (
                "b1" in market
                or "back" in market
            )
        )

        if direct_runner:

            runner_list = [market]

        else:

            runner_list = market.get(
                "oddDatas"
            )

            if runner_list is None:
                runner_list = market.get(
                    "runners"
                )

            if isinstance(runner_list, dict):
                runner_list = [runner_list]

            if not isinstance(runner_list, list):
                runner_list = []

        runners = []

        for runner in runner_list:

            if not isinstance(runner, dict):
                continue

            runners.append(
                {
                    "id": str(
                        _first_value(
                            runner,
                            "id",
                            "selectionId",
                            "selection_id",
                            "sid",
                            default="",
                        )
                    ),

                    "name": str(
                        _first_value(
                            runner,
                            "rname",
                            "runnerName",
                            "runner_name",
                            "name",
                            default="",
                        )
                    ),

                    "back": _safe_float(
                        _first_value(
                            runner,
                            "b1",
                            "back",
                            "backPrice",
                        )
                    ),

                    "back_size": _safe_float(
                        _first_value(
                            runner,
                            "bs1",
                            "backSize",
                            "back_size",
                        )
                    ),

                    "lay": _safe_float(
                        _first_value(
                            runner,
                            "l1",
                            "lay",
                            "layPrice",
                        )
                    ),

                    "lay_size": _safe_float(
                        _first_value(
                            runner,
                            "ls1",
                            "laySize",
                            "lay_size",
                        )
                    ),

                    "raw": runner,
                }
            )

        result.append(
            {
                "id": str(
                    _first_value(
                        market,
                        "id",
                        "marketId",
                        default="",
                    )
                ),

                "name": str(
                    _first_value(
                        market,
                        "name",
                        "marketName",
                        default="Bookmaker",
                    )
                ),

                "status": str(
                    _first_value(
                        market,
                        "status",
                        default="OPEN",
                    )
                ),

                "type": "bookmaker",

                "runners": runners,

                "raw": market,
            }
        )

    return result


# =========================================================
# FANCY ODDS
# =========================================================

def parse_fancy_odds(
    data: Any,
) -> List[Dict[str, Any]]:

    if not isinstance(data, dict):
        return []

    fancy = (
        data.get("fancyOdds")
        or data.get("fancy_odds")
        or data.get("fancy")
    )

    if isinstance(fancy, dict):
        fancy = [fancy]

    if not isinstance(fancy, list):
        return []

    result = []

    for market in fancy:

        if not isinstance(market, dict):
            continue

        # -------------------------------------------------
        # IMPORTANT:
        # Support direct normalized fancy rows as well as:
        # fancyOdds -> oddDatas
        # -------------------------------------------------

        has_direct_fancy_fields = any(
            key in market
            for key in (
                "rname",
                "yes_score",
                "yesScore",
                "yes",
                "b1",
                "no_score",
                "noScore",
                "no",
                "l1",
            )
        )

        nested_rows = market.get(
            "oddDatas"
        )

        if isinstance(nested_rows, dict):
            nested_rows = [nested_rows]

        if isinstance(nested_rows, list):
            odd_datas = nested_rows

        elif has_direct_fancy_fields:
            odd_datas = [market]

        else:
            odd_datas = []

        # -------------------------------------------------
        # MARKET NAME
        # -------------------------------------------------

        default_market_name = str(
            _first_value(
                market,
                "mName",
                "marketName",
                "name",
                default="Fancy",
            )
        )

        # -------------------------------------------------
        # MARKET ID
        # -------------------------------------------------

        default_market_id = str(
            _first_value(
                market,
                "id",
                "marketId",
                default="",
            )
        )

        # -------------------------------------------------
        # STATUS
        # -------------------------------------------------

        default_status = str(
            _first_value(
                market,
                "status",
                default="OPEN",
            )
        )

        for runner in odd_datas:

            if not isinstance(runner, dict):
                continue

            sid = _first_value(
                runner,
                "sid",
                "selectionId",
                "selection_id",
                "id",
                default="",
            )

            name = _first_value(
                runner,
                "rname",
                "sName",
                "runnerName",
                "runner_name",
                "selectionName",
                "selection_name",
                "name",
                default="",
            )

            # -------------------------------------------------
            # YES
            #
            # b1  = YES score
            # bs1 = YES amount/rate
            # -------------------------------------------------

            yes_score = _safe_float(
                _first_value(
                    runner,
                    "yes_score",
                    "yesScore",
                    "yes",
                    "b1",
                    "back",
                    "backPrice",
                    "back_price",
                )
            )

            yes_amount = _safe_float(
                _first_value(
                    runner,
                    "yes_amount",
                    "yesAmount",
                    "yes_size",
                    "yesSize",
                    "bs1",
                    "backSize",
                    "back_size",
                    "backVolume",
                )
            )

            # -------------------------------------------------
            # NO
            #
            # l1  = NO score
            # ls1 = NO amount/rate
            # -------------------------------------------------

            no_score = _safe_float(
                _first_value(
                    runner,
                    "no_score",
                    "noScore",
                    "no",
                    "l1",
                    "lay",
                    "layPrice",
                    "lay_price",
                )
            )

            no_amount = _safe_float(
                _first_value(
                    runner,
                    "no_amount",
                    "noAmount",
                    "no_size",
                    "noSize",
                    "ls1",
                    "laySize",
                    "lay_size",
                    "layVolume",
                )
            )

            # -------------------------------------------------
            # NORMALIZED ROW
            # -------------------------------------------------

            result.append(
                {
                    "id": str(sid),

                    "sid": str(sid),

                    "name": str(name),

                    "market_name": default_market_name,

                    "market_id": default_market_id,

                    "status": default_status,

                    "type": "fancy",

                    # YES
                    "yes": yes_score,
                    "yes_score": yes_score,
                    "yes_amount": yes_amount,
                    "yes_size": yes_amount,

                    # NO
                    "no": no_score,
                    "no_score": no_score,
                    "no_amount": no_amount,
                    "no_size": no_amount,

                    # Compatibility fields
                    "back": yes_score,
                    "back_size": yes_amount,

                    "lay": no_score,
                    "lay_size": no_amount,

                    "raw": runner,
                }
            )

    return result


# =========================================================
# NORMALIZE ODDS
# =========================================================

def normalize_odds(
    payload: Any,
) -> Dict[str, Any]:

    data = _unwrap_odds(
        payload
    )

    if not isinstance(data, dict):

        return {
            "success": False,
            "match_odds": [],
            "bookmaker_odds": [],
            "fancy_odds": [],
            "other_market_odds": [],
            "raw": payload,
        }

    match_odds = parse_match_odds(
        data
    )

    bookmaker_odds = parse_bookmaker_odds(
        data
    )

    fancy_odds = parse_fancy_odds(
        data
    )

    return {
        "success": True,

        "match_odds": match_odds,

        "bookmaker_odds": bookmaker_odds,

        "fancy_odds": fancy_odds,

        "other_market_odds": [],

        # Camel-case compatibility
        "matchOdds": match_odds,

        "bookmakerOdds": bookmaker_odds,

        "fancyOdds": fancy_odds,

        "otherMarketOdds": [],

        "raw": payload,
    }


# =========================================================
# GET ODDS
# =========================================================

def get_odds(
    game_id: Any,
    event_id: Any = None,
    market_id: Any = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:

    game_id = str(
        game_id or ""
    ).strip()

    if not game_id:

        return {
            "success": False,
            "match_odds": [],
            "bookmaker_odds": [],
            "fancy_odds": [],
            "other_market_odds": [],
        }

    if not event_id or not market_id:

        ids = get_match_ids(
            game_id
        )

        if not event_id:
            event_id = ids.get(
                "event_id"
            )

        if not market_id:
            market_id = ids.get(
                "market_id"
            )

    event_id = str(
        event_id or ""
    ).strip()

    market_id = str(
        market_id or ""
    ).strip()

    if not market_id:

        return {
            "success": False,
            "message": "Market ID is missing",
            "game_id": game_id,
            "event_id": event_id,
            "market_id": "",
            "match_odds": [],
            "bookmaker_odds": [],
            "fancy_odds": [],
            "other_market_odds": [],
        }

    cache_key = (
        f"{game_id}:{event_id}:{market_id}"
    )

    now = _now()

    cached = _odds_cache.get(
        cache_key
    )

    if cached and not force_refresh:

        age = (
            now
            - cached.get(
                "timestamp",
                0.0,
            )
        )

        if age <= ODDS_CACHE_TTL:

            return cached.get(
                "data",
                {},
            )

    payload = _request(
        "/api/cricket/odds",
        params={
            "gameId": game_id,
            "eventId": event_id,
            "marketId": market_id,
        },
    )

    normalized = normalize_odds(
        payload
    )

    normalized["game_id"] = game_id
    normalized["event_id"] = event_id
    normalized["market_id"] = market_id

    _odds_cache[cache_key] = {
        "timestamp": now,
        "data": normalized,
    }

    print(
        "[PROEXCH] Odds:",
        game_id,
        "match=",
        len(normalized.get("match_odds", [])),
        "bookmaker=",
        len(normalized.get("bookmaker_odds", [])),
        "fancy=",
        len(normalized.get("fancy_odds", [])),
    )

    return normalized


# =========================================================
# GENERIC SCORE NORMALIZATION
# =========================================================

_SCORE_CONTAINER_KEYS = (
    "score",
    "scores",
    "scoreData",
    "score_data",
    "liveScore",
    "live_score",
    "currentScore",
    "current_score",
)

_TEAM_KEYS = (
    "team",
    "teamName",
    "team_name",
    "name",
)

_RUN_KEYS = (
    "runs",
    "run",
    "score",
    "total",
)

_WICKET_KEYS = (
    "wickets",
    "wicket",
    "wkts",
)

_OVERS_KEYS = (
    "overs",
    "over",
)

_RATE_KEYS = (
    "crr",
    "currentRunRate",
    "current_run_rate",
)

_TARGET_KEYS = (
    "target",
    "Target",
)

_REQUIRED_RUN_KEYS = (
    "requiredRuns",
    "required_runs",
)

_REQUIRED_BALL_KEYS = (
    "requiredBalls",
    "required_balls",
)

_REQUIRED_RATE_KEYS = (
    "rrr",
    "requiredRunRate",
    "required_run_rate",
)


def _looks_like_innings(
    value: Any,
) -> bool:

    if not isinstance(
        value,
        dict,
    ):
        return False

    keys = {
        str(key).lower()
        for key in value.keys()
    }

    return bool(
        keys.intersection(
            {
                "team",
                "teamname",
                "team_name",
                "runs",
                "score",
                "wickets",
                "wkts",
                "overs",
            }
        )
    )


def _walk_dicts(
    value: Any,
):
    if isinstance(
        value,
        dict,
    ):

        yield value

        for child in value.values():

            yield from _walk_dicts(
                child
            )

    elif isinstance(
        value,
        list,
    ):

        for item in value:

            yield from _walk_dicts(
                item
            )


def _extract_innings_candidates(
    payload: Any,
) -> List[Dict[str, Any]]:

    candidates = []

    for item in _walk_dicts(
        payload
    ):

        if _looks_like_innings(
            item
        ):
            candidates.append(item)

    return candidates


def _normalize_innings(
    innings: Dict[str, Any],
) -> Dict[str, Any]:

    team = _first_value(
        innings,
        *_TEAM_KEYS,
        default="",
    )

    runs = _first_value(
        innings,
        *_RUN_KEYS,
        default=None,
    )

    wickets = _first_value(
        innings,
        *_WICKET_KEYS,
        default=None,
    )

    overs = _first_value(
        innings,
        *_OVERS_KEYS,
        default=None,
    )

    crr = _first_value(
        innings,
        *_RATE_KEYS,
        default=None,
    )

    return {
        "team": _clean_text(team),

        "runs": _safe_int(runs),

        "wickets": _safe_int(wickets),

        "overs": (
            _overs_display(overs)
            if overs is not None
            else ""
        ),

        "crr": _safe_float(crr),

        "raw": innings,
    }


def _find_top_level_value(
    payload: Any,
    keys: tuple,
) -> Any:

    if isinstance(
        payload,
        dict,
    ):

        for key in keys:

            if key in payload:

                value = payload.get(
                    key
                )

                if value is not None:
                    return value

    return _find_value(
        payload,
        list(keys),
    )


def _parse_score_text(
    text: Any,
) -> Dict[str, Any]:

    result = {
        "runs": None,
        "wickets": None,
        "overs": "",
    }

    value = str(
        text or ""
    ).strip()

    if not value:
        return result

    match = re.search(
        r"(\d+)\s*-\s*(\d+)"
        r"(?:\s*\((\d+(?:\.\d+)?)\))?",
        value,
    )

    if not match:
        return result

    result["runs"] = _safe_int(
        match.group(1)
    )

    result["wickets"] = _safe_int(
        match.group(2)
    )

    if match.group(3):

        result["overs"] = _overs_display(
            match.group(3)
        )

    return result


def normalize_score(
    payload: Any,
) -> Dict[str, Any]:

    if not payload:

        return {
            "success": False,
            "status": "UNAVAILABLE",
            "score": None,
            "scores": [],
            "raw": payload,
        }

    innings_candidates = (
        _extract_innings_candidates(
            payload
        )
    )

    innings = [
        _normalize_innings(
            item
        )
        for item in innings_candidates
    ]

    target = _find_top_level_value(
        payload,
        _TARGET_KEYS,
    )

    required_runs = _find_top_level_value(
        payload,
        _REQUIRED_RUN_KEYS,
    )

    required_balls = _find_top_level_value(
        payload,
        _REQUIRED_BALL_KEYS,
    )

    rrr = _find_top_level_value(
        payload,
        _REQUIRED_RATE_KEYS,
    )

    if innings:

        return {
            "success": True,
            "status": "LIVE",
            "source": "generic",
            "is_live": True,
            "score": innings[0],
            "scores": innings,
            "target": _safe_int(target),
            "required_runs": _safe_int(
                required_runs
            ),
            "required_balls": _safe_int(
                required_balls
            ),
            "rrr": _safe_float(rrr),
            "raw": payload,
        }

    return {
        "success": False,
        "status": "UNAVAILABLE",
        "source": "generic",
        "score": None,
        "scores": [],
        "raw": payload,
    }


# =========================================================
# REQUIRED SCORE STATUS PARSER
# =========================================================

def _parse_required_score_status(
    text: Any,
) -> Dict[str, Any]:

    result = {
        "required_runs": None,
        "required_overs": None,
        "required_balls": None,
    }

    value = str(
        text or ""
    ).strip()

    if not value:
        return result

    match = re.search(
        r"Need\s+([\d,]+)"
        r"\s+Runs\s+In\s+"
        r"(\d+(?:\.\d+)?)"
        r"\s+Overs\s*"
        r"\((\d+)\s+Balls\)",
        value,
        re.IGNORECASE,
    )

    if match:

        try:
            result["required_runs"] = int(
                match.group(1).replace(
                    ",",
                    "",
                )
            )
        except Exception:
            pass

        result["required_overs"] = match.group(2)

        try:
            result["required_balls"] = int(
                match.group(3)
            )
        except Exception:
            pass

        return result

    runs_match = re.search(
        r"([\d,]+)\s+Runs",
        value,
        re.IGNORECASE,
    )

    overs_match = re.search(
        r"(\d+(?:\.\d+)?)\s+Overs",
        value,
        re.IGNORECASE,
    )

    balls_match = re.search(
        r"\((\d+)\s+Balls\)",
        value,
        re.IGNORECASE,
    )

    if runs_match:

        try:
            result["required_runs"] = int(
                runs_match.group(1).replace(
                    ",",
                    "",
                )
            )
        except Exception:
            pass

    if overs_match:
        result["required_overs"] = overs_match.group(1)

    if balls_match:

        try:
            result["required_balls"] = int(
                balls_match.group(1)
            )
        except Exception:
            pass

    return result


# =========================================================
# NORMALIZE TEAM SCORE
# =========================================================

def _normalize_team_score(
    name: str,
    short_name: str,
    flag: str,
    score_display: str,
    only_score: str,
    score_only: str,
    overs: str,
) -> Dict[str, Any]:

    parsed = _parse_score_text(
        only_score
        or score_display
        or score_only
    )

    runs = parsed.get(
        "runs"
    )

    wickets = parsed.get(
        "wickets"
    )

    parsed_overs = (
        overs
        or parsed.get(
            "overs"
        )
        or ""
    )

    final_score = (
        score_only
        or _format_score(
            runs,
            wickets,
        )
    )

    return {
        "name": name,

        "short_name": short_name,

        "short": short_name,

        "flag": flag,

        "score": final_score,

        "score_display": (
            score_display
            or only_score
            or score_only
            or ""
        ),

        "only_score": (
            only_score
            or ""
        ),

        "score_only": (
            score_only
            or ""
        ),

        "runs": runs,

        "wickets": wickets,

        "overs": parsed_overs,

        "has_score": bool(
            final_score
            or runs is not None
        ),
    }


# =========================================================
# NORMALIZE LAST OVERS
# =========================================================

def _normalize_last_overs(
    values: Any,
) -> List[Dict[str, Any]]:

    if not isinstance(
        values,
        list,
    ):
        return []

    result = []

    for item in values:

        if isinstance(
            item,
            dict,
        ):

            balls = item.get(
                "balls"
            )

            if not isinstance(
                balls,
                list,
            ):
                balls = []

            result.append(
                {
                    "over": item.get(
                        "over"
                    ),

                    "balls": [
                        str(ball)
                        for ball in balls
                    ],

                    "runs": (
                        _safe_int(
                            item.get(
                                "runs"
                            )
                        )
                        if _safe_int(
                            item.get(
                                "runs"
                            )
                        ) is not None
                        else 0
                    ),

                    "raw": item,
                }
            )

        elif isinstance(
            item,
            list,
        ):

            result.append(
                {
                    "over": len(result) + 1,

                    "balls": [
                        str(ball)
                        for ball in item
                    ],

                    "runs": 0,

                    "raw": item,
                }
            )

    return result


# =========================================================
# NORMALIZE CURRENT OVER
# =========================================================

def _normalize_current_over(
    score: Dict[str, Any],
) -> List[str]:

    # First check array-style response.
    for key in (
        "CurrentOverBalls",
        "currentOverBalls",
        "current_over_balls",
    ):

        value = score.get(key)

        if isinstance(
            value,
            list,
        ):

            return [
                str(ball)
                for ball in value
                if (
                    ball is not None
                    and str(ball).strip() != ""
                )
            ]

    # Then use numbered fields.
    balls = []

    for index in range(1, 21):

        value = score.get(
            f"CurrentOverBalls{index}"
        )

        if (
            value is not None
            and str(value).strip() != ""
        ):

            balls.append(
                str(value)
            )

    return balls


# =========================================================
# NORMALIZE LAST 6 BALLS
# =========================================================

def _normalize_last6(
    score: Dict[str, Any],
) -> List[str]:

    last6_balls = score.get(
        "Last6Balls"
    )

    if isinstance(
        last6_balls,
        list,
    ):

        return [
            str(ball)
            for ball in last6_balls
            if (
                ball is not None
                and str(ball).strip() != ""
            )
        ]

    balls = []

    for index in range(1, 7):

        value = score.get(
            f"Last6Balls{index}"
        )

        if (
            value is not None
            and str(value).strip() != ""
        ):

            balls.append(
                str(value)
            )

    return balls


# =========================================================
# EXACT CRICKETBZ SCORE PARSER
# =========================================================

def _parse_cricketbz_single_score(
    score: Dict[str, Any],
    provider_status: Any = None,
    provider_message: Any = None,
) -> Dict[str, Any]:

    # -----------------------------------------------------
    # TEAM INFORMATION
    # -----------------------------------------------------

    team1_name = _clean_text(
        score.get(
            "Team1Name"
        )
    )

    team1_short = _clean_text(
        score.get(
            "Team1Name_Short"
        )
    )

    team1_flag = _clean_text(
        score.get(
            "Team1Flag"
        )
    )

    team1_score_display = _clean_text(
        score.get(
            "Team1Score"
        )
    )

    team1_only_score = _clean_text(
        score.get(
            "Team1OnlyScore"
        )
    )

    team1_score_only = _clean_text(
        score.get(
            "Team1ScoreOnly"
        )
    )

    team1_overs = _clean_text(
        score.get(
            "Team1Overs"
        )
    )

    team2_name = _clean_text(
        score.get(
            "Team2Name"
        )
    )

    team2_short = _clean_text(
        score.get(
            "Team2Name_Short"
        )
    )

    team2_flag = _clean_text(
        score.get(
            "Team2Flag"
        )
    )

    team2_score_display = _clean_text(
        score.get(
            "Team2Score"
        )
    )

    team2_only_score = _clean_text(
        score.get(
            "Team2OnlyScore"
        )
    )

    team2_score_only = _clean_text(
        score.get(
            "Team2ScoreOnly"
        )
    )

    team2_overs = _clean_text(
        score.get(
            "Team2Overs"
        )
    )

    # -----------------------------------------------------
    # TEAM STRUCTURES
    # -----------------------------------------------------

    team1 = _normalize_team_score(
        name=team1_name,
        short_name=team1_short,
        flag=team1_flag,
        score_display=team1_score_display,
        only_score=team1_only_score,
        score_only=team1_score_only,
        overs=team1_overs,
    )

    team2 = _normalize_team_score(
        name=team2_name,
        short_name=team2_short,
        flag=team2_flag,
        score_display=team2_score_display,
        only_score=team2_only_score,
        score_only=team2_score_only,
        overs=team2_overs,
    )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    score_status = _clean_text(
        score.get(
            "ScoreStatus"
        )
    )

    nr_msg = _clean_text(
        score.get(
            "NRMsg"
        )
    )

    live_commentary = score.get(
        "LiveCommentary"
    )

    score_message = _clean_text(
        score.get(
            "Message"
        )
    )

    commentary = _clean_text(
        score.get(
            "Commentary"
        )
    )

    is_live = _as_bool(
        live_commentary
    )

    if (
        team1_score_display
        or team1_only_score
        or team1_score_only
        or team2_score_display
        or team2_only_score
        or team2_score_only
    ):
        is_live = True

    if is_live:
        status = "LIVE"
    elif provider_status:
        status = str(
            provider_status
        ).upper()
    else:
        status = "AVAILABLE"

    # -----------------------------------------------------
    # CURRENT INNING
    # -----------------------------------------------------

    current_inning = _clean_text(
        score.get(
            "CurrentInning"
        )
    )

    # -----------------------------------------------------
    # BATTING TEAM
    #
    # Usually the populated/current score is the batting
    # side. The CricketBZ object can have Team1 score blank
    # while Team2 is batting, so do not assume Team1.
    # -----------------------------------------------------

    if team1.get("has_score") and not team2.get("has_score"):

        batting_team = {
            "name": team1_name,
            "short_name": team1_short,
            "team": "team1",
        }

    elif team2.get("has_score") and not team1.get("has_score"):

        batting_team = {
            "name": team2_name,
            "short_name": team2_short,
            "team": "team2",
        }

    elif team1.get("has_score") and team2.get("has_score"):

        # In a chase, the second populated score is normally
        # the current batting side.
        batting_team = {
            "name": team2_name,
            "short_name": team2_short,
            "team": "team2",
        }

    else:

        batting_team = {
            "name": "",
            "short_name": "",
            "team": "",
        }

    # -----------------------------------------------------
    # REQUIRED RUNS / BALLS
    # -----------------------------------------------------

    required_text = (
        nr_msg
        or score_status
    )

    required = (
        _parse_required_score_status(
            required_text
        )
    )

    # -----------------------------------------------------
    # BATSMAN 1
    # -----------------------------------------------------

    player1 = {
        "id": _clean_text(
            score.get(
                "Player1ID"
            )
        ),

        "name": _clean_text(
            score.get(
                "Player1"
            )
        ),

        "image": _clean_text(
            score.get(
                "Player1Image"
            )
        ),

        "runs": _safe_int(
            score.get(
                "Player1Run"
            )
        ),

        "balls": _safe_int(
            score.get(
                "Player1Balls"
            )
        ),

        "fours": _safe_int(
            score.get(
                "Player1Fours"
            )
        ),

        "sixes": _safe_int(
            score.get(
                "Player1Sixes"
            )
        ),

        "strike_rate": _safe_float(
            score.get(
                "Player1StrikeRate"
            )
        ),
    }

    # -----------------------------------------------------
    # BATSMAN 2
    # -----------------------------------------------------

    player2 = {
        "id": _clean_text(
            score.get(
                "Player2ID"
            )
        ),

        "name": _clean_text(
            score.get(
                "Player2"
            )
        ),

        "image": _clean_text(
            score.get(
                "Player2Image"
            )
        ),

        "runs": _safe_int(
            score.get(
                "Player2Run"
            )
        ),

        "balls": _safe_int(
            score.get(
                "Player2Balls"
            )
        ),

        "fours": _safe_int(
            score.get(
                "Player2Fours"
            )
        ),

        "sixes": _safe_int(
            score.get(
                "Player2Sixes"
            )
        ),

        "strike_rate": _safe_float(
            score.get(
                "Player2StrikeRate"
            )
        ),
    }

    # -----------------------------------------------------
    # CURRENT BOWLER
    # -----------------------------------------------------

    bowler = {
        "id": _clean_text(
            score.get(
                "BowlerID"
            )
        ),

        "name": _clean_text(
            score.get(
                "Bowler"
            )
        ),

        "image": _clean_text(
            score.get(
                "BowlerImage"
            )
        ),

        "runs": _safe_int(
            score.get(
                "BowlerRun"
            )
        ),

        "maidens": _safe_int(
            score.get(
                "BowlerMaiden"
            )
        ),

        "overs": _clean_text(
            score.get(
                "BowlerOver"
            )
        ),

        "wickets": _safe_int(
            score.get(
                "BowlerWicket"
            )
        ),

        "economy": _safe_float(
            score.get(
                "BowlerEconomy"
            )
        ),
    }

    # -----------------------------------------------------
    # CURRENT OVER
    # -----------------------------------------------------

    current_over_balls = _normalize_current_over(
        score
    )

    # -----------------------------------------------------
    # LAST 6 BALLS
    # -----------------------------------------------------

    last6_balls = _normalize_last6(
        score
    )

    # -----------------------------------------------------
    # LAST 4 OVERS
    # -----------------------------------------------------

    last4_overs = _normalize_last_overs(
        score.get(
            "Last4Overs"
        )
    )

    # -----------------------------------------------------
    # CHASE DATA
    # -----------------------------------------------------

    target = _safe_int(
        score.get(
            "Target"
        )
    )

    required_runs = required.get(
        "required_runs"
    )

    required_overs = required.get(
        "required_overs"
    )

    required_balls = required.get(
        "required_balls"
    )

    # -----------------------------------------------------
    # RATES
    # -----------------------------------------------------

    crr = _safe_float(
        score.get(
            "CRR"
        )
    )

    rrr = _safe_float(
        score.get(
            "RRR"
        )
    )

    # -----------------------------------------------------
    # EVENT NAME
    # -----------------------------------------------------

    event_name = (
        f"{team1_name} v {team2_name}"
        if team1_name and team2_name
        else ""
    )

    # -----------------------------------------------------
    # FULL STRUCTURED SCOREBOARD
    # -----------------------------------------------------

    scoreboard = {

        "status": status,

        "is_live": is_live,

        "live": is_live,

        "provider_status": provider_status,

        "provider_message": provider_message,

        "current_inning": current_inning,

        "event_name": event_name,

        # -------------------------------------------------
        # MATCH
        # -------------------------------------------------

        "match": {

            "event_name": event_name,

            "team1": team1,

            "team2": team2,

            "batting_team": batting_team,
        },

        # -------------------------------------------------
        # TEAMS
        # -------------------------------------------------

        "team1": team1,

        "team2": team2,

        "batting_team": batting_team,

        # -------------------------------------------------
        # INNINGS
        # -------------------------------------------------

        "innings": {

            "current": _safe_int(
                current_inning
            ),

            "current_display": current_inning,

        },

        # -------------------------------------------------
        # BATTING
        # -------------------------------------------------

        "batting": {

            "team": batting_team,

            "player1": player1,

            "player2": player2,

            "batsman1": player1,

            "batsman2": player2,

        },

        # -------------------------------------------------
        # BOWLING
        # -------------------------------------------------

        "bowling": {

            "current": bowler,

            "bowler": bowler,

        },

        # -------------------------------------------------
        # RATES
        # -------------------------------------------------

        "rates": {

            "crr": crr,

            "rrr": rrr,

        },

        # -------------------------------------------------
        # CHASE
        # -------------------------------------------------

        "chase": {

            "target": target,

            "required_runs": required_runs,

            "required_overs": required_overs,

            "required_balls": required_balls,

            "required_text": required_text,

        },

        # -------------------------------------------------
        # CURRENT OVER
        # -------------------------------------------------

        "current_over": {

            "balls": current_over_balls,

            "ball_count": len(
                current_over_balls
            ),

        },

        # -------------------------------------------------
        # LAST SIX BALLS
        # -------------------------------------------------

        "last_six_balls": last6_balls,

        "last6_balls": last6_balls,

        # -------------------------------------------------
        # LAST FOUR OVERS
        # -------------------------------------------------

        "last_four_overs": last4_overs,

        "last4_overs": last4_overs,

        # -------------------------------------------------
        # COMMENTARY
        # -------------------------------------------------

        "commentary": {

            "score_status": score_status,

            "message": score_message,

            "commentary": commentary,

            "live_commentary": live_commentary,

            "nr_msg": nr_msg,

        },

        # -------------------------------------------------
        # RAW SCORE
        # -------------------------------------------------

        "raw_score": score,
    }

    # =====================================================
    # BACKWARD COMPATIBILITY
    # =====================================================

    scoreboard.update(
        {

            "team1_name": team1_name,

            "team1_short": team1_short,

            "team1_flag": team1_flag,

            "team1_score": team1_score_display,

            "team1_only_score": team1_only_score,

            "team1_score_only": team1_score_only,

            "team1_overs": team1_overs,

            "team2_name": team2_name,

            "team2_short": team2_short,

            "team2_flag": team2_flag,

            "team2_score": team2_score_display,

            "team2_only_score": team2_only_score,

            "team2_score_only": team2_score_only,

            "team2_overs": team2_overs,

            "crr": crr,

            "rrr": rrr,

            "player1": player1,

            "player2": player2,

            "batsman1": player1,

            "batsman2": player2,

            "bowler": bowler,

            "message": score_message,

            "score_status": score_status,

            "commentary_text": commentary,

            "commentary": commentary,

            "live_commentary": live_commentary,

            "current_over_balls": current_over_balls,

            "last6_balls": last6_balls,

            "last_6_balls": last6_balls,

            "last4_overs": last4_overs,

            "last_4_overs": last4_overs,

            "nr_msg": nr_msg,

            "target": target,

            "required_runs": required_runs,

            "required_overs": required_overs,

            "required_balls": required_balls,

            "raw_score": score,

        }
    )

    return scoreboard


def _parse_cricketbz_score(
    payload: Any,
) -> Dict[str, Any]:

    empty_result = {
        "success": False,
        "status": "UNAVAILABLE",
        "source": "cricketbz",
        "score": None,
        "scoreboard": None,
        "scores": [],
        "scoreboards": [],
        "data": None,
        "raw": payload,
    }

    try:

        if not isinstance(
            payload,
            dict,
        ):
            return empty_result

        outer_data = payload.get(
            "data"
        )

        if not isinstance(
            outer_data,
            dict,
        ):
            return empty_result

        provider_status = outer_data.get(
            "Status"
        )

        provider_message = outer_data.get(
            "Message"
        )

        score_data = outer_data.get(
            "Data"
        )

        if not isinstance(
            score_data,
            dict,
        ):
            return empty_result

        score_list = score_data.get(
            "Score"
        )

        if isinstance(
            score_list,
            dict,
        ):
            score_list = [
                score_list
            ]

        if not isinstance(
            score_list,
            list,
        ):
            return empty_result

        if not score_list:
            return empty_result

        # -------------------------------------------------
        # PARSE EVERY SCORE OBJECT
        # -------------------------------------------------

        scoreboards: List[Dict[str, Any]] = []

        for score in score_list:

            if not isinstance(
                score,
                dict,
            ):
                continue

            parsed = _parse_cricketbz_single_score(
                score=score,
                provider_status=provider_status,
                provider_message=provider_message,
            )

            scoreboards.append(
                parsed
            )

        if not scoreboards:
            return empty_result

        # -------------------------------------------------
        # CHOOSE ACTIVE SCOREBOARD
        #
        # Prefer the scoreboard containing live/current
        # score information. Otherwise use the first item.
        # -------------------------------------------------

        active_scoreboard = scoreboards[0]

        for item in scoreboards:

            if item.get(
                "is_live"
            ):
                active_scoreboard = item
                break

        # -------------------------------------------------
        # TOP-LEVEL RESPONSE
        # -------------------------------------------------

        return {

            "success": True,

            "status": active_scoreboard.get(
                "status",
                "AVAILABLE",
            ),

            "is_live": bool(
                active_scoreboard.get(
                    "is_live"
                )
            ),

            "source": "cricketbz",

            # Main scoreboard
            "scoreboard": active_scoreboard,

            # Same scoreboard for compatibility
            "data": active_scoreboard,

            "score": active_scoreboard,

            "scores": scoreboards,

            "scoreboards": scoreboards,

            "provider_status": provider_status,

            "provider_message": provider_message,

            "raw": payload,

        }

    except Exception as exc:

        print(
            "[PROEXCH] CricketBZ score parser error:",
            repr(exc),
        )

        return empty_result


# =========================================================
# GET CRICKETBZ THROUGH PROEXCH
# =========================================================

def get_cricketbz(
    game_id: Any,
) -> Any:

    game_id = str(
        game_id or ""
    ).strip()

    if not game_id:
        return None

    return _request(
        "/api/cricket/cricketbz",
        params={
            "gameId": game_id,
        },
    )


# =========================================================
# GET LIVE SCORE
# =========================================================

def get_score(
    score_id: Any,
    force_refresh: bool = False,
) -> Dict[str, Any]:

    score_id = str(
        score_id or ""
    ).strip()

    if not score_id:

        return {
            "success": False,
            "status": "UNAVAILABLE",
            "source": "cricketbz",
            "score": None,
            "scoreboard": None,
            "scores": [],
            "scoreboards": [],
            "data": None,
            "message": "Score ID is missing",
        }

    now = _now()

    # =====================================================
    # CACHE
    # =====================================================

    cached = _score_cache.get(
        score_id
    )

    if (
        cached
        and not force_refresh
    ):

        age = (
            now
            - cached.get(
                "timestamp",
                0.0,
            )
        )

        if age <= SCORE_CACHE_TTL:

            cached_data = cached.get(
                "data"
            )

            if isinstance(
                cached_data,
                dict,
            ):
                return cached_data

    # =====================================================
    # IMPORTANT:
    # score_id is the CricketBZ match ID.
    #
    # For example:
    # score_id = 35890910
    #
    # becomes:
    # https://cricketbz.app/getScore/35890910
    # =====================================================

    url = (
        f"{CRICKETBZ_BASE_URL.rstrip('/')}"
        f"/getScore/{score_id}"
    )

    try:

        print(
            "[PROEXCH] Getting CricketBZ score:",
            url,
        )

        raw = _request_cricketbz(
            url
        )

        normalized = _parse_cricketbz_score(
            raw
        )

        # Generic fallback only if the exact parser
        # cannot understand the response.
        if not normalized.get(
            "success"
        ):

            normalized = normalize_score(
                raw
            )

        if normalized.get(
            "success"
        ):

            _score_cache[
                score_id
            ] = {
                "timestamp": now,
                "data": normalized,
            }

            print(
                "[PROEXCH] CricketBZ score found:",
                score_id,
            )

            return normalized

    except Exception as exc:

        print(
            "[PROEXCH] Direct CricketBZ score failed:",
            repr(exc),
        )

    # =====================================================
    # PROEXCH FALLBACK
    # =====================================================

    try:

        print(
            "[PROEXCH] Trying ProExch cricketbz fallback:",
            score_id,
        )

        fallback = get_cricketbz(
            score_id
        )

        normalized = _parse_cricketbz_score(
            fallback
        )

        if not normalized.get(
            "success"
        ):

            normalized = normalize_score(
                fallback
            )

        if normalized.get(
            "success"
        ):

            _score_cache[
                score_id
            ] = {
                "timestamp": now,
                "data": normalized,
            }

            return normalized

    except Exception as exc:

        print(
            "[PROEXCH] ProExch scoreboard fallback failed:",
            repr(exc),
        )

    # =====================================================
    # UNAVAILABLE
    # =====================================================

    return {
        "success": False,
        "status": "UNAVAILABLE",
        "source": "cricketbz",
        "score": None,
        "scoreboard": None,
        "scores": [],
        "scoreboards": [],
        "data": None,
        "message": "Live score is currently unavailable",
    }


# =========================================================
# RESULT
# =========================================================

def get_cricketbz_result(
    game_id: Any,
) -> Any:

    game_id = str(
        game_id or ""
    ).strip()

    if not game_id:
        return None

    return _request(
        "/api/cricket/result",
        params={
            "gameId": game_id,
        },
    )


def get_proexch_result(
    game_id: Any,
) -> Dict[str, Any]:

    game_id = str(
        game_id or ""
    ).strip()

    if not game_id:

        return {
            "success": False,
            "result": None,
        }

    now = _now()

    cached = _result_cache.get(
        game_id
    )

    if cached:

        age = (
            now
            - cached.get(
                "timestamp",
                0.0,
            )
        )

        if age <= RESULT_CACHE_TTL:

            return cached.get(
                "data",
                {},
            )

    try:

        raw = get_cricketbz_result(
            game_id
        )

        normalized = {
            "success": True,
            "result": raw,
            "raw": raw,
        }

        _result_cache[
            game_id
        ] = {
            "timestamp": now,
            "data": normalized,
        }

        return normalized

    except Exception as exc:

        print(
            "[PROEXCH] Result request failed:",
            repr(exc),
        )

        return {
            "success": False,
            "result": None,
            "message": str(exc),
        }


# =========================================================
# VIDEO
# =========================================================

def get_video(
    game_id: Any,
) -> Any:

    game_id = str(
        game_id or ""
    ).strip()

    if not game_id:
        return None

    try:

        return _request(
            "/api/cricket/video",
            params={
                "gameId": game_id,
            },
        )

    except Exception as exc:

        print(
            "[PROEXCH] Video request failed:",
            repr(exc),
        )

        return None


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

    _score_cache.clear()

    _result_cache.clear()


def clear_odds_cache() -> None:
    _odds_cache.clear()


def clear_score_cache() -> None:
    _score_cache.clear()


def clear_result_cache() -> None:
    _result_cache.clear()