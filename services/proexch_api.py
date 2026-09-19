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

# Cache durations
MATCH_CACHE_TTL = 15.0
ODDS_CACHE_TTL = 2.0
SCORE_CACHE_TTL = 3.0
RESULT_CACHE_TTL = 10.0

# Leave empty when your server IP is whitelisted.
PROXY = ""


# =========================================================
# CRICKETBZ SCORE / RESULT PROVIDER
# =========================================================

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
_score_cache: Dict[str, Dict[str, Any]] = {}
_result_cache: Dict[str, Dict[str, Any]] = {}


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

        if value in (
            "",
            "-",
            "null",
            "None",
            "N/A",
            "NA",
        ):
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None

    try:
        text = str(value).strip()

        if text in (
            "",
            "-",
            "null",
            "None",
            "N/A",
            "NA",
        ):
            return None

        return int(float(text))

    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    return str(value).strip()


def _first_value(
    data: Dict[str, Any],
    keys: List[str],
) -> Any:

    for key in keys:

        if key in data:

            value = data.get(key)

            if value is not None and value != "":
                return value

    return None


def _format_number(value: Any) -> str:
    number = _safe_float(value)

    if number is None:
        return ""

    if number.is_integer():
        return str(int(number))

    return str(number)


def _format_score(
    runs: Any,
    wickets: Any,
) -> str:

    runs_text = _format_number(runs)

    wickets_int = _safe_int(wickets)

    if not runs_text:
        return ""

    if wickets_int is None:
        return runs_text

    return f"{runs_text}/{wickets_int}"


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

    if match:

        whole = int(match.group(1))
        balls = match.group(2)

        if balls is None:
            return float(whole)

        if len(balls) == 1 and int(balls) <= 5:
            return whole + (
                int(balls) / 6
            )

        try:
            return float(text)

        except ValueError:
            return None

    return None


def _overs_display(value: Any) -> str:

    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    return text


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

                time.sleep(
                    0.25 * (attempt + 1)
                )

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

    for attempt in range(MAX_RETRIES + 1):

        try:

            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "Accept": (
                        "application/json,"
                        "text/plain,"
                        "*/*"
                    ),
                    "User-Agent": "CrickBet/1.0",
                },
            )

            response.raise_for_status()

            try:
                return response.json()

            except ValueError:
                return response.text

        except Exception as exc:

            last_error = exc

            if attempt < MAX_RETRIES:

                time.sleep(
                    0.25 * (attempt + 1)
                )

    raise RuntimeError(
        "CricketBZ request failed: "
        f"{last_error}"
    )


# =========================================================
# GENERIC RESPONSE UNWRAPPER
# =========================================================

def _unwrap_generic(
    payload: Any,
) -> Any:

    current = payload

    for _ in range(5):

        if not isinstance(
            current,
            dict,
        ):
            break

        next_value = None

        for key in (
            "data",
            "result",
            "response",
            "body",
            "payload",
        ):

            if key in current:

                value = current.get(key)

                if isinstance(
                    value,
                    (dict, list),
                ):

                    next_value = value
                    break

        if next_value is None:
            break

        current = next_value

    return current


# =========================================================
# SCOREBOARD
# =========================================================
#
# SCOREBOARD FLOW
#
# 1. Match list gives us score_id.
#
# 2. get_score(score_id) calls:
#
#       https://cricketbz.app/getScore/{score_id}
#
# 3. CricketBZ response is normalized.
#
# 4. If CricketBZ fails, ProExch's:
#
#       /api/cricket/cricketbz
#
#    is used as fallback.
#
# =========================================================

def get_score(
    score_id: str,
    force_refresh: bool = False,
) -> Any:

    score_id = str(
        score_id
    ).strip()

    if not score_id:
        raise ValueError(
            "score_id is required"
        )

    current = _now()

    cached = _score_cache.get(
        score_id
    )

    if (
        not force_refresh
        and cached
        and (
            current
            - cached["timestamp"]
        ) < SCORE_CACHE_TTL
    ):
        return cached["data"]

    # -----------------------------------------------------
    # PRIMARY SCOREBOARD
    # -----------------------------------------------------

    url = (
        f"{CRICKETBZ_BASE_URL}"
        f"/getScore/{score_id}"
    )

    try:

        print(
            "[SCOREBOARD] requesting CricketBZ:",
            score_id,
        )

        raw = _request_cricketbz(
            url
        )

        normalized = normalize_score(
            raw
        )

        normalized["score_id"] = score_id

        normalized["provider"] = "CricketBZ"

        normalized["raw"] = raw

        _score_cache[score_id] = {
            "timestamp": current,
            "data": normalized,
        }

        return normalized

    except Exception as exc:

        print(
            "[CRICKETBZ] score request failed:",
            exc,
        )

    # -----------------------------------------------------
    # PROEXCH SCOREBOARD FALLBACK
    # -----------------------------------------------------

    try:

        print(
            "[SCOREBOARD] trying ProExch fallback:",
            score_id,
        )

        fallback = get_cricketbz(
            score_id
        )

        if fallback is not None:

            normalized = normalize_score(
                fallback
            )

            normalized["score_id"] = (
                score_id
            )

            normalized["provider"] = (
                "ProExch/CricketBZ"
            )

            normalized["raw"] = fallback

            _score_cache[score_id] = {
                "timestamp": current,
                "data": normalized,
            }

            return normalized

    except Exception as fallback_exc:

        print(
            "[PROEXCH] score fallback failed:",
            fallback_exc,
        )

    raise RuntimeError(
        "Unable to retrieve live score"
    )


# =========================================================
# SCOREBOARD BY GAME ID
# =========================================================

def get_score_by_game_id(
    game_id: str,
    force_refresh: bool = False,
) -> Any:

    game_id = str(
        game_id
    ).strip()

    if not game_id:
        raise ValueError(
            "game_id is required"
        )

    ids = get_match_ids(
        game_id
    )

    score_id = (
        ids.get("score_id")
        or game_id
    )

    return get_score(
        score_id,
        force_refresh=force_refresh,
    )


# =========================================================
# SCOREBOARD ALIAS
# =========================================================

def get_scoreboard(
    score_id: str,
    force_refresh: bool = False,
) -> Any:

    return get_score(
        score_id,
        force_refresh=force_refresh,
    )


# =========================================================
# SCORE NORMALIZATION HELPERS
# =========================================================

_SCORE_CONTAINER_KEYS = (
    "innings",
    "inning",
    "inningsData",
    "innings_data",
    "scores",
    "score",
    "scorecard",
    "scoreCard",
    "score_data",
    "scoreData",
    "teamScores",
    "team_scores",
)

_TEAM_KEYS = (
    "team",
    "teamName",
    "team_name",
    "name",
    "title",
    "battingTeam",
    "batting_team",
    "team1",
    "team2",
)

_RUN_KEYS = (
    "runs",
    "run",
    "score",
    "total",
    "r",
    "runsScored",
    "totalRuns",
    "teamScore",
)

_WICKET_KEYS = (
    "wickets",
    "wicket",
    "wkts",
    "wkt",
    "w",
    "wicketsLost",
)

_OVERS_KEYS = (
    "overs",
    "over",
    "ovs",
    "overNumber",
    "oversPlayed",
)

_RATE_KEYS = (
    "runRate",
    "run_rate",
    "rr",
    "currentRunRate",
    "crr",
)

_TARGET_KEYS = (
    "target",
    "targetRuns",
    "target_runs",
)

_REQUIRED_RUN_KEYS = (
    "requiredRuns",
    "required_runs",
    "runsRequired",
    "runs_required",
    "remainingRuns",
    "remaining_runs",
)

_REQUIRED_BALL_KEYS = (
    "requiredBalls",
    "required_balls",
    "ballsRequired",
    "balls_required",
    "remainingBalls",
)

_REQUIRED_RATE_KEYS = (
    "requiredRunRate",
    "required_run_rate",
    "rrr",
    "requiredRR",
)


def _looks_like_innings(
    value: Dict[str, Any],
) -> bool:

    if not isinstance(
        value,
        dict,
    ):
        return False

    has_team = any(
        key in value
        for key in _TEAM_KEYS
    )

    has_score = any(
        key in value
        for key in _RUN_KEYS
    )

    has_overs = any(
        key in value
        for key in _OVERS_KEYS
    )

    has_wickets = any(
        key in value
        for key in _WICKET_KEYS
    )

    return (
        has_score
        and (
            has_team
            or has_overs
            or has_wickets
        )
    )


def _walk_dicts(
    value: Any,
) -> List[Dict[str, Any]]:

    found: List[Dict[str, Any]] = []

    if isinstance(value, dict):

        found.append(value)

        for child in value.values():

            if isinstance(
                child,
                (dict, list),
            ):

                found.extend(
                    _walk_dicts(child)
                )

    elif isinstance(value, list):

        for item in value:

            if isinstance(
                item,
                (dict, list),
            ):

                found.extend(
                    _walk_dicts(item)
                )

    return found


def _extract_innings_candidates(
    payload: Any,
) -> List[Dict[str, Any]]:

    candidates: List[
        Dict[str, Any]
    ] = []

    all_dicts = _walk_dicts(
        payload
    )

    for obj in all_dicts:

        for key in _SCORE_CONTAINER_KEYS:

            value = obj.get(key)

            if isinstance(
                value,
                list,
            ):

                for item in value:

                    if (
                        isinstance(item, dict)
                        and _looks_like_innings(
                            item
                        )
                    ):
                        candidates.append(
                            item
                        )

            elif (
                isinstance(
                    value,
                    dict,
                )
                and _looks_like_innings(
                    value
                )
            ):

                candidates.append(
                    value
                )

    for obj in all_dicts:

        if _looks_like_innings(obj):
            candidates.append(obj)

    unique: List[
        Dict[str, Any]
    ] = []

    seen = set()

    for item in candidates:

        marker = repr(
            sorted(
                (
                    str(k),
                    str(v),
                )
                for k, v in item.items()
                if k in (
                    *_TEAM_KEYS,
                    *_RUN_KEYS,
                    *_WICKET_KEYS,
                    *_OVERS_KEYS,
                )
            )
        )

        if marker in seen:
            continue

        seen.add(marker)
        unique.append(item)

    return unique


def _normalize_innings(
    item: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:

    team_value = _first_value(
        item,
        list(_TEAM_KEYS),
    )

    runs_value = _first_value(
        item,
        list(_RUN_KEYS),
    )

    wickets_value = _first_value(
        item,
        list(_WICKET_KEYS),
    )

    overs_value = _first_value(
        item,
        list(_OVERS_KEYS),
    )

    rate_value = _first_value(
        item,
        list(_RATE_KEYS),
    )

    if isinstance(
        runs_value,
        str,
    ):

        score_match = re.search(
            r"(\d+)\s*/\s*(\d+)",
            runs_value,
        )

        if score_match:

            parsed_runs = _safe_int(
                score_match.group(1)
            )

            parsed_wickets = _safe_int(
                score_match.group(2)
            )

            if parsed_runs is not None:
                runs_value = parsed_runs

            if parsed_wickets is not None:
                wickets_value = (
                    parsed_wickets
                )

        overs_match = re.search(
            r"\(?\s*(\d+(?:\.\d+)?)\s*\)?",
            runs_value,
        )

        if (
            overs_value is None
            and overs_match
        ):

            overs_value = (
                overs_match.group(1)
            )

    runs = _safe_int(
        runs_value
    )

    wickets = _safe_int(
        wickets_value
    )

    overs = _overs_display(
        overs_value
    )

    run_rate = _safe_float(
        rate_value
    )

    if (
        run_rate is None
        and runs is not None
        and overs
    ):

        overs_decimal = _parse_overs(
            overs
        )

        if (
            overs_decimal is not None
            and overs_decimal > 0
        ):

            run_rate = (
                runs
                / overs_decimal
            )

    team = _clean_text(
        team_value
    )

    if not team:

        team = (
            _clean_text(
                item.get("batting")
            )
            or _clean_text(
                item.get(
                    "battingTeamName"
                )
            )
            or f"Innings {index + 1}"
        )

    target = _safe_int(
        _first_value(
            item,
            list(_TARGET_KEYS),
        )
    )

    required_runs = _safe_int(
        _first_value(
            item,
            list(_REQUIRED_RUN_KEYS),
        )
    )

    required_balls = _safe_int(
        _first_value(
            item,
            list(_REQUIRED_BALL_KEYS),
        )
    )

    required_rate = _safe_float(
        _first_value(
            item,
            list(_REQUIRED_RATE_KEYS),
        )
    )

    score_text = _format_score(
        runs,
        wickets,
    )

    return {
        "team": team,
        "runs": runs,
        "wickets": wickets,
        "overs": overs,
        "score": score_text,
        "run_rate": (
            round(run_rate, 2)
            if run_rate is not None
            else None
        ),
        "target": target,
        "required_runs": required_runs,
        "required_balls": required_balls,
        "required_run_rate": (
            round(required_rate, 2)
            if required_rate is not None
            else None
        ),
        "is_current": bool(
            item.get("isCurrent")
            or item.get("is_current")
            or item.get("current")
            or item.get("batting") is True
        ),
        "raw": item,
    }


def _find_top_level_value(
    payload: Any,
    keys: List[str],
) -> Any:

    for obj in _walk_dicts(payload):

        for key in keys:

            if key in obj:

                value = obj.get(key)

                if (
                    value is not None
                    and value != ""
                ):
                    return value

    return None


def _parse_score_text(
    text: str,
) -> List[Dict[str, Any]]:

    if not text:
        return []

    text = str(text)

    innings: List[
        Dict[str, Any]
    ] = []

    pattern = re.compile(
        r"""
        (?P<team>[A-Za-z][A-Za-z0-9 .&'()\_-]{1,40}?)
        \s*[:\-]?\s*
        (?P<runs>\d+)
        \s*/\s*
        (?P<wickets>\d+)
        (?:
            \s*
            \(?
            (?P<overs>\d+(?:\.\d+)?)
            \)?
            \s*(?:overs|ov)?
        )?
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    for match in pattern.finditer(text):

        team = match.group(
            "team"
        ).strip()

        if team.lower() in {
            "score",
            "scores",
            "result",
            "live",
            "status",
        }:
            continue

        runs = _safe_int(
            match.group("runs")
        )

        wickets = _safe_int(
            match.group("wickets")
        )

        overs = match.group(
            "overs"
        )

        innings.append(
            {
                "team": team,
                "runs": runs,
                "wickets": wickets,
                "overs": overs or "",
                "score": _format_score(
                    runs,
                    wickets,
                ),
                "run_rate": None,
                "target": None,
                "required_runs": None,
                "required_balls": None,
                "required_run_rate": None,
                "is_current": False,
                "raw": match.group(0),
            }
        )

    return innings


# =========================================================
# NORMALIZE SCORE
# =========================================================

def normalize_score(
    payload: Any,
) -> Dict[str, Any]:

    root = _unwrap_generic(
        payload
    )

    innings_raw = (
        _extract_innings_candidates(
            payload
        )
    )

    innings: List[
        Dict[str, Any]
    ] = []

    for index, item in enumerate(
        innings_raw
    ):

        normalized = _normalize_innings(
            item,
            index,
        )

        if (
            normalized["runs"]
            is not None
            or normalized["score"]
        ):

            innings.append(
                normalized
            )

    if not innings:

        if isinstance(
            root,
            str,
        ):

            innings = _parse_score_text(
                root
            )

        elif isinstance(
            payload,
            str,
        ):

            innings = _parse_score_text(
                payload
            )

    # -----------------------------------------------------
    # TEAM / MATCH INFORMATION
    # -----------------------------------------------------

    event_name = _find_top_level_value(
        payload,
        [
            "eventName",
            "event_name",
            "matchName",
            "match_name",
            "match",
            "title",
            "name",
        ],
    )

    status = _find_top_level_value(
        payload,
        [
            "status",
            "matchStatus",
            "match_status",
            "state",
            "gameStatus",
            "game_status",
        ],
    )

    toss = _find_top_level_value(
        payload,
        [
            "toss",
            "tossResult",
            "toss_result",
        ],
    )

    message = _find_top_level_value(
        payload,
        [
            "message",
            "msg",
        ],
    )

    batting_team = _find_top_level_value(
        payload,
        [
            "battingTeam",
            "batting_team",
            "currentBattingTeam",
            "current_batting_team",
        ],
    )

    bowling_team = _find_top_level_value(
        payload,
        [
            "bowlingTeam",
            "bowling_team",
            "currentBowlingTeam",
            "current_bowling_team",
        ],
    )

    target = _safe_int(
        _find_top_level_value(
            payload,
            list(_TARGET_KEYS),
        )
    )

    required_runs = _safe_int(
        _find_top_level_value(
            payload,
            list(_REQUIRED_RUN_KEYS),
        )
    )

    required_balls = _safe_int(
        _find_top_level_value(
            payload,
            list(_REQUIRED_BALL_KEYS),
        )
    )

    required_rate = _safe_float(
        _find_top_level_value(
            payload,
            list(_REQUIRED_RATE_KEYS),
        )
    )

    # -----------------------------------------------------
    # CURRENT INNINGS
    # -----------------------------------------------------

    if innings:

        current_innings = None

        for inning in innings:

            if inning.get(
                "is_current"
            ):

                current_innings = inning
                break

        if current_innings is None:
            current_innings = innings[-1]

        if target is None:
            target = current_innings.get(
                "target"
            )

        if required_runs is None:
            required_runs = (
                current_innings.get(
                    "required_runs"
                )
            )

        if required_balls is None:
            required_balls = (
                current_innings.get(
                    "required_balls"
                )
            )

        if required_rate is None:
            required_rate = (
                current_innings.get(
                    "required_run_rate"
                )
            )

        if not batting_team:
            batting_team = (
                current_innings.get(
                    "team"
                )
            )

    # -----------------------------------------------------
    # CALCULATE REQUIRED RUNS
    # -----------------------------------------------------

    if (
        required_runs is None
        and target is not None
        and innings
    ):

        current = innings[-1]

        current_runs = current.get(
            "runs"
        )

        if current_runs is not None:

            required_runs = max(
                0,
                target - current_runs,
            )

    # -----------------------------------------------------
    # CURRENT INNINGS MARKER
    # -----------------------------------------------------

    if innings:

        current_index = None

        for index, inning in enumerate(
            innings
        ):

            if inning.get(
                "is_current"
            ):

                current_index = index
                break

        if current_index is None:
            current_index = len(innings) - 1

        for index, inning in enumerate(
            innings
        ):

            inning["is_current"] = (
                index == current_index
            )

    # -----------------------------------------------------
    # PROVIDER STATUS
    # -----------------------------------------------------

    if not status:

        if innings:
            status = "LIVE"

        elif message:
            status = str(message)

        else:
            status = "SCORE UNAVAILABLE"

    # -----------------------------------------------------
    # EXTRA SCOREBOARD FIELDS
    # -----------------------------------------------------

    score_status = _find_top_level_value(
        payload,
        [
            "ScoreStatus",
            "scoreStatus",
            "score_status",
        ],
    )

    commentary = _find_top_level_value(
        payload,
        [
            "Commentary",
            "commentary",
        ],
    )

    live_commentary = _find_top_level_value(
        payload,
        [
            "LiveCommentary",
            "liveCommentary",
            "live_commentary",
        ],
    )

    current_inning = _find_top_level_value(
        payload,
        [
            "CurrentInning",
            "currentInning",
            "current_inning",
        ],
    )

    crr = _safe_float(
        _find_top_level_value(
            payload,
            [
                "CRR",
                "crr",
                "currentRunRate",
            ],
        )
    )

    rrr = _safe_float(
        _find_top_level_value(
            payload,
            [
                "RRR",
                "rrr",
                "requiredRunRate",
            ],
        )
    )

    # -----------------------------------------------------
    # RETURN NORMALIZED SCORE
    # -----------------------------------------------------

    return {
        "success": bool(
            len(innings) > 0
        ),

        "event_name": (
            str(event_name)
            if event_name is not None
            else ""
        ),

        "status": str(status),

        "toss": (
            str(toss)
            if toss is not None
            else ""
        ),

        "batting_team": (
            str(batting_team)
            if batting_team is not None
            else ""
        ),

        "bowling_team": (
            str(bowling_team)
            if bowling_team is not None
            else ""
        ),

        "current_inning": (
            str(current_inning)
            if current_inning is not None
            else ""
        ),

        "innings": innings,

        "target": target,

        "required_runs": required_runs,

        "required_balls": required_balls,

        "required_run_rate": (
            round(required_rate, 2)
            if required_rate is not None
            else None
        ),

        "crr": (
            round(crr, 2)
            if crr is not None
            else None
        ),

        "rrr": (
            round(rrr, 2)
            if rrr is not None
            else None
        ),

        "score_status": (
            str(score_status)
            if score_status is not None
            else ""
        ),

        "commentary": (
            str(commentary)
            if commentary is not None
            else ""
        ),

        "live_commentary": (
            str(live_commentary)
            if live_commentary is not None
            else ""
        ),

        "message": (
            str(message)
            if message is not None
            else ""
        ),
    }


# =========================================================
# CRICKETBZ RESULT
# =========================================================

def get_cricketbz_result(
    result_id: str,
    force_refresh: bool = False,
) -> Any:

    result_id = str(
        result_id
    ).strip()

    if not result_id:
        raise ValueError(
            "result_id is required"
        )

    current = _now()

    cached = _result_cache.get(
        result_id
    )

    if (
        not force_refresh
        and cached
        and (
            current
            - cached["timestamp"]
        ) < RESULT_CACHE_TTL
    ):

        return cached["data"]

    url = (
        f"{CRICKETBZ_BASE_URL}"
        f"/getResults/{result_id}"
    )

    data = _request_cricketbz(
        url
    )

    _result_cache[result_id] = {
        "timestamp": current,
        "data": data,
    }

    return data


# =========================================================
# PROEXCH RESULT
# =========================================================

def get_proexch_result(
    market_id: str,
) -> Any:

    market_id = str(
        market_id
    ).strip()

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

    if not isinstance(
        payload,
        dict,
    ):
        return []

    data = payload.get(
        "data"
    )

    if isinstance(
        data,
        dict,
    ):

        data = data.get(
            "data",
            [],
        )

    if isinstance(
        data,
        list,
    ):

        return data

    return []


# =========================================================
# ODDS RESPONSE UNWRAPPER
# =========================================================

def _unwrap_odds(
    payload: Any,
) -> Dict[str, Any]:

    if not isinstance(
        payload,
        dict,
    ):
        return {}

    data = payload.get(
        "data"
    )

    if isinstance(
        data,
        dict,
    ):
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

    matches: List[
        Dict[str, Any]
    ] = []

    for item in raw_matches:

        if not isinstance(
            item,
            dict,
        ):
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

        in_play = item.get(
            "inPlay"
        )

        tv = item.get(
            "tv"
        )

        score_id = (
            item.get("scoreId")
            or item.get("score_id")
            or item.get("scoreBoardId")
            or game_id
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

            "team1": str(
                team1
            ),

            "team2": str(
                team2
            ),

            "team3": str(
                team3
            ),

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
            str(
                match.get("game_id")
            )
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

    result: List[
        Dict[str, Any]
    ] = []

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

                "back": _safe_float(
                    runner.get("b1")
                ),

                "back_size": _safe_float(
                    runner.get("bs1")
                ),

                "back2": _safe_float(
                    runner.get("b2")
                ),

                "back2_size": _safe_float(
                    runner.get("bs2")
                ),

                "back3": _safe_float(
                    runner.get("b3")
                ),

                "back3_size": _safe_float(
                    runner.get("bs3")
                ),

                "lay": _safe_float(
                    runner.get("l1")
                ),

                "lay_size": _safe_float(
                    runner.get("ls1")
                ),

                "lay2": _safe_float(
                    runner.get("l2")
                ),

                "lay2_size": _safe_float(
                    runner.get("ls2")
                ),

                "lay3": _safe_float(
                    runner.get("l3")
                ),

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

    result: List[
        Dict[str, Any]
    ] = []

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

                "back": _safe_float(
                    runner.get("b1")
                ),

                "back_size": _safe_float(
                    runner.get("bs1")
                ),

                "lay": _safe_float(
                    runner.get("l1")
                ),

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

    result: List[
        Dict[str, Any]
    ] = []

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

                "name": str(
                    name
                ),

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

        result.append(
            {

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
    _score_cache.clear()
    _result_cache.clear()

    print(
        "[PROEXCH] cache cleared"
    )


def clear_caches() -> None:
    clear_cache()


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


def clear_score_cache(
    score_id: Optional[str] = None,
) -> None:

    if score_id is None:

        _score_cache.clear()
        return

    _score_cache.pop(
        str(score_id),
        None,
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
            exc,
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
            exc,
        )

        return None


# =========================================================
# COMPATIBILITY ALIASES
# =========================================================

fetch_matches = get_matches
fetch_odds = get_odds
fetch_score = get_score
fetch_result = get_proexch_result
fetch_video = get_video