from __future__ import annotations

import requests
from urllib.parse import quote
from typing import Any


# =========================================================
# CONFIGURATION
# =========================================================

BASE_URL = "https://apidata.proexch.in"
TIMEOUT = 15

session = requests.Session()

session.headers.update({
    "User-Agent": "CrickBet/1.0",
    "Accept": "application/json",
})


# =========================================================
# ERROR
# =========================================================

class ProExchError(Exception):
    pass


# =========================================================
# COMMON HTTP REQUEST
# =========================================================

def _request(
    path: str,
    params: dict | None = None,
    timeout: int = TIMEOUT,
):
    url = f"{BASE_URL}{path}"

    try:
        response = session.get(
            url,
            params=params or {},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ProExchError(
            f"Could not connect to ProExch: {exc}"
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ProExchError(
            "ProExch returned invalid JSON. "
            f"HTTP status: {response.status_code}"
        ) from exc

    if response.status_code >= 400:
        raise ProExchError(
            f"ProExch HTTP {response.status_code}: {payload}"
        )

    provider_status = payload.get("statusCode")

    if provider_status is not None and provider_status != 200:
        raise ProExchError(
            f"ProExch returned statusCode={provider_status}: "
            f"{payload}"
        )

    return payload


# =========================================================
# MATCHES
# =========================================================

def get_matches():
    """
    ProExch:

    GET /api/cricket/matches

    Provider response:

    {
        "statusCode": 200,
        "data": {
            "data": [...]
        }
    }

    Return only the actual match list.
    """

    payload = _request("/api/cricket/matches")

    if not isinstance(payload, dict):
        return []

    data = payload.get("data")

    if isinstance(data, dict):
        data = data.get("data")

    if not isinstance(data, list):
        return []

    return data


def health_check():
    return _request("/api/cricket/matches")


# =========================================================
# FIND MATCH
# =========================================================

def find_match(game_id: str | int):
    game_id = str(game_id).strip()

    matches = get_matches()

    for match in matches:
        if not isinstance(match, dict):
            continue

        current_game_id = (
            match.get("gameId")
            or match.get("game_id")
        )

        if current_game_id is None:
            continue

        if str(current_game_id).strip() == game_id:
            return match

    return None


# =========================================================
# MATCH IDS
# =========================================================

def get_match_ids(match: dict):
    if not isinstance(match, dict):
        return None, None

    event_id = (
        match.get("eventId")
        or match.get("event_id")
    )

    market_id = (
        match.get("marketId")
        or match.get("market_id")
    )

    return (
        str(event_id).strip() if event_id is not None else None,
        str(market_id).strip() if market_id is not None else None,
    )


# =========================================================
# ODDS
# =========================================================

def get_odds(
    game_id: str | int,
    event_id: str | None = None,
    market_id: str | None = None,
):
    """
    ProExch odds endpoint requires:

        gameId
        marketId

    Example:

    /api/cricket/odds
        ?gameId=36074941
        &marketId=1.262469350

    eventId is intentionally NOT sent.
    """

    game_id = str(game_id).strip()

    if not game_id:
        raise ProExchError("gameId is required.")

    if not market_id:
        match = find_match(game_id)

        if not match:
            raise ProExchError(
                f"Match not found for gameId={game_id}"
            )

        _, market_id = get_match_ids(match)

    if not market_id:
        raise ProExchError(
            f"marketId could not be determined for gameId={game_id}"
        )

    market_id = str(market_id).strip()

    print(
        "[PROEXCH] odds request:",
        "gameId=", game_id,
        "marketId=", market_id,
    )

    return _request(
        "/api/cricket/odds",
        params={
            "gameId": game_id,
            "marketId": market_id,
        },
    )


# =========================================================
# UNWRAP ODDS RESPONSE
# =========================================================

def _unwrap_odds(payload: Any) -> dict:
    """
    Converts:

    {
        statusCode: 200,
        data: {
            bookMakerOdds: [],
            fancyOdds: [],
            matchOdds: []
        }
    }

    into:

    {
        bookMakerOdds: [],
        fancyOdds: [],
        matchOdds: []
    }
    """

    if not isinstance(payload, dict):
        return {}

    data = payload.get("data")

    if isinstance(data, dict):
        return data

    return payload


# =========================================================
# NUMBER
# =========================================================

def _number(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    try:
        text = str(value).strip()

        if not text:
            return None

        number = float(text)

        if number.is_integer():
            return int(number)

        return number

    except (TypeError, ValueError):
        return None


# =========================================================
# MATCH ODDS
# =========================================================

def parse_match_odds(raw):
    """
    Exact ProExch structure:

    matchOdds
      [
        {
          "mid": "...",
          "market": "Match Odds",
          "oddDatas": [
            {
              "sid": ...,
              "b1": ...,
              "bs1": ...,
              "b2": ...,
              "bs2": ...,
              "b3": ...,
              "bs3": ...,
              "l1": ...,
              "ls1": ...,
              "l2": ...,
              "ls2": ...,
              "l3": ...,
              "ls3": ...,
              "rname": "..."
            }
          ]
        }
      ]
    """

    if not isinstance(raw, list):
        return []

    markets = []

    for market in raw:

        if not isinstance(market, dict):
            continue

        odd_datas = market.get("oddDatas", [])

        if not isinstance(odd_datas, list):
            continue

        runners = []

        for item in odd_datas:

            if not isinstance(item, dict):
                continue

            runner = {
                "id": str(item.get("sid"))
                if item.get("sid") is not None
                else None,

                "selection_id": str(item.get("sid"))
                if item.get("sid") is not None
                else None,

                "name": str(
                    item.get("rname")
                    or "Unknown"
                ),

                # -------------------------
                # BACK 1
                # -------------------------

                "back": _number(item.get("b1")),
                "back_size": _number(item.get("bs1")),

                # -------------------------
                # BACK 2
                # -------------------------

                "back2": _number(item.get("b2")),
                "back2_size": _number(item.get("bs2")),

                # -------------------------
                # BACK 3
                # -------------------------

                "back3": _number(item.get("b3")),
                "back3_size": _number(item.get("bs3")),

                # -------------------------
                # LAY 1
                # -------------------------

                "lay": _number(item.get("l1")),
                "lay_size": _number(item.get("ls1")),

                # -------------------------
                # LAY 2
                # -------------------------

                "lay2": _number(item.get("l2")),
                "lay2_size": _number(item.get("ls2")),

                # -------------------------
                # LAY 3
                # -------------------------

                "lay3": _number(item.get("l3")),
                "lay3_size": _number(item.get("ls3")),

                "back_price": _number(item.get("b1")),
                "lay_price": _number(item.get("l1")),

                "odds": _number(item.get("b1")),

                "status": item.get("status") or "",

                "raw": item,
            }

            runners.append(runner)

        if runners:

            markets.append({
                "id": str(
                    market.get("mid")
                )
                if market.get("mid") is not None
                else None,

                "name": (
                    market.get("market")
                    or market.get("mname")
                    or "Match Odds"
                ),

                "status": (
                    market.get("mstatus")
                    or market.get("status")
                    or ""
                ),

                "type": "match_odds",

                "runners": runners,

                "outcomes": runners,

                "raw": market,
            })

    return markets


# =========================================================
# BOOKMAKER
# =========================================================

def parse_bookmaker_odds(raw):
    """
    ProExch bookmaker structure uses the same oddDatas
    format as Match Odds.
    """

    if not isinstance(raw, list):
        return []

    markets = []

    for market in raw:

        if not isinstance(market, dict):
            continue

        odd_datas = market.get("oddDatas", [])

        if not isinstance(odd_datas, list):
            continue

        runners = []

        for item in odd_datas:

            if not isinstance(item, dict):
                continue

            runner = {
                "id": str(item.get("sid"))
                if item.get("sid") is not None
                else None,

                "selection_id": str(item.get("sid"))
                if item.get("sid") is not None
                else None,

                "name": str(
                    item.get("rname")
                    or "Unknown"
                ),

                "back": _number(item.get("b1")),
                "back_size": _number(item.get("bs1")),

                "back2": _number(item.get("b2")),
                "back2_size": _number(item.get("bs2")),

                "back3": _number(item.get("b3")),
                "back3_size": _number(item.get("bs3")),

                "lay": _number(item.get("l1")),
                "lay_size": _number(item.get("ls1")),

                "lay2": _number(item.get("l2")),
                "lay2_size": _number(item.get("ls2")),

                "lay3": _number(item.get("l3")),
                "lay3_size": _number(item.get("ls3")),

                "back_price": _number(item.get("b1")),
                "lay_price": _number(item.get("l1")),

                "odds": _number(item.get("b1")),

                "status": item.get("status") or "",

                "raw": item,
            }

            runners.append(runner)

        if runners:

            markets.append({
                "id": str(
                    market.get("mid")
                )
                if market.get("mid") is not None
                else None,

                "name": (
                    market.get("market")
                    or market.get("mname")
                    or "Bookmaker"
                ),

                "status": (
                    market.get("mstatus")
                    or market.get("status")
                    or ""
                ),

                "type": "bookmaker",

                "runners": runners,

                "outcomes": runners,

                "raw": market,
            })

    return markets


# =========================================================
# FANCY / SESSION
# =========================================================

def parse_fancy_odds(raw):
    """
    Exact ProExch format:

    fancyOdds
      [
        {
          ...
          "oddDatas": [...]
        }
      ]

    A fancy row is exposed as:

        YES = b1
        YES SIZE = bs1

        NO = l1
        NO SIZE = ls1
    """

    if not isinstance(raw, list):
        return []

    markets = []

    for market in raw:

        if not isinstance(market, dict):
            continue

        odd_datas = market.get("oddDatas", [])

        if not isinstance(odd_datas, list):
            continue

        rows = []

        for item in odd_datas:

            if not isinstance(item, dict):
                continue

            yes = _number(item.get("b1"))
            yes_size = _number(item.get("bs1"))

            no = _number(item.get("l1"))
            no_size = _number(item.get("ls1"))

            row = {
                "id": str(item.get("sid"))
                if item.get("sid") is not None
                else None,

                "selection_id": str(item.get("sid"))
                if item.get("sid") is not None
                else None,

                "sid": str(item.get("sid"))
                if item.get("sid") is not None
                else None,

                "name": str(
                    item.get("rname")
                    or "Session"
                ),

                "yes": yes,
                "yes_size": yes_size,

                "no": no,
                "no_size": no_size,

                "back": yes,
                "back_size": yes_size,

                "lay": no,
                "lay_size": no_size,

                "odds": yes,

                "status": item.get("status") or "",

                "raw": item,
            }

            rows.append(row)

        if rows:

            markets.append({
                "id": str(
                    market.get("mid")
                )
                if market.get("mid") is not None
                else None,

                "name": (
                    market.get("market")
                    or market.get("mname")
                    or "Fancy / Session"
                ),

                "status": (
                    market.get("mstatus")
                    or market.get("status")
                    or ""
                ),

                "type": "fancy",

                "rows": rows,

                "runners": rows,

                "outcomes": rows,

                "raw": market,
            })

    return markets


# =========================================================
# NORMALIZE ODDS
# =========================================================

def normalize_odds(payload):
    data = _unwrap_odds(payload)

    match_raw = data.get(
        "matchOdds",
        []
    )

    bookmaker_raw = data.get(
        "bookMakerOdds",
        []
    )

    fancy_raw = data.get(
        "fancyOdds",
        []
    )

    other_raw = data.get(
        "otherMarketOdds",
        []
    )

    match_odds = parse_match_odds(
        match_raw
    )

    bookmaker_odds = parse_bookmaker_odds(
        bookmaker_raw
    )

    fancy_odds = parse_fancy_odds(
        fancy_raw
    )

    if not isinstance(other_raw, list):
        other_raw = []

    return {
        "match_odds": match_odds,
        "bookmaker_odds": bookmaker_odds,
        "fancy_odds": fancy_odds,
        "other_market_odds": other_raw,

        # Keep raw provider response
        # available for debugging.
        "raw": data,
    }


# =========================================================
# RESULT
# =========================================================

def get_results(market_id):
    market_id = str(market_id).strip()

    if not market_id:
        raise ProExchError(
            "marketId is required."
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
# CRICKETBZ RESULT / SCORE
# =========================================================

CRICKETBZ_BASE_URL = "https://cricketbz.app"


def _cricketbz_request(
    path: str,
    timeout: int = TIMEOUT,
):
    url = f"{CRICKETBZ_BASE_URL}{path}"

    try:
        response = session.get(
            url,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ProExchError(
            f"Could not connect to CricketBZ: {exc}"
        ) from exc

    try:
        return response.json()
    except ValueError:
        return response.text


def get_cricketbz_result(result_id):
    result_id = str(result_id).strip()

    if not result_id:
        raise ProExchError(
            "resultId is required."
        )

    return _cricketbz_request(
        "/getResults/"
        + quote(result_id, safe="")
    )


def get_cricketbz_score(score_id):
    score_id = str(score_id).strip()

    if not score_id:
        raise ProExchError(
            "scoreId is required."
        )

    return _cricketbz_request(
        "/getScore/"
        + quote(score_id, safe="")
    )


# =========================================================
# VIDEO
# =========================================================

VIDEO_BASE_URL = "https://video.proexch.in"


def get_video_stream_url(stream_id):
    stream_id = str(stream_id).strip()

    if not stream_id:
        raise ProExchError(
            "streamId is required."
        )

    return (
        f"{VIDEO_BASE_URL}/tv/v4/stream/"
        f"{quote(stream_id, safe='')}"
    )