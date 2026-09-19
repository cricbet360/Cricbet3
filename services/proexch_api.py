# services/proexch_api.py

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

# CricketBZ score provider
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


# =========================================================
# CACHES
# =========================================================

_match_cache: Dict[str, Any] = {
    "timestamp": 0.0,
    "data": None,
}

_odds_cache: Dict[str, Dict[str, Any]] = {}

_score_cache: Dict[str, Dict[str, Any]] = {}

_result_cache: Dict[str, Dict[str, Any]] = {}


# =========================================================
# BASIC HELPERS
# =========================================================

def _now() -> float:
    return time.time()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default

        if isinstance(value, bool):
            return float(value)

        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default

        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return default


def _safe_string(value: Any, default: str = "") -> str:
    if value is None:
        return default

    return str(value).strip()


def _first_value(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            value = data.get(key)

            if value is not None and value != "":
                return value

    return None


def _clean_name(value: Any) -> str:
    name = _safe_string(value)

    if not name:
        return ""

    return name.rstrip("*").strip()


def _extract_score_numbers(score_text: Any) -> Dict[str, Any]:
    """
    Converts examples like:

        335-7 (50.0)
        12-1 (2.1)
        QL 335-7 (50.0)

    into:

        {
            "runs": 335,
            "wickets": 7,
            "overs": "50.0"
        }
    """

    text = _safe_string(score_text)

    result = {
        "runs": 0,
        "wickets": 0,
        "overs": "",
    }

    if not text:
        return result

    match = re.search(
        r"(\d+)\s*[-/]\s*(\d+)\s*\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)",
        text,
    )

    if match:
        result["runs"] = _safe_int(match.group(1))
        result["wickets"] = _safe_int(match.group(2))
        result["overs"] = match.group(3)
        return result

    match = re.search(
        r"(\d+)\s*[-/]\s*(\d+)",
        text,
    )

    if match:
        result["runs"] = _safe_int(match.group(1))
        result["wickets"] = _safe_int(match.group(2))

    over_match = re.search(
        r"\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)",
        text,
    )

    if over_match:
        result["overs"] = over_match.group(1)

    return result


def _request_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """
    Common GET helper with small retry logic.
    """

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
                time.sleep(0.15 * (attempt + 1))

    return None


# =========================================================
# EXACT CRICKETBZ SCORE PARSER
# =========================================================

def _parse_cricketbz_score(raw: Any) -> Optional[Dict[str, Any]]:
    """
    Parses the actual CricketBZ response structure:

    {
        "success": true,
        "data": {
            "Status": "Success",
            "Message": "Score data found",
            "Data": {
                "Score": [
                    {
                        "CurrentInning": "2",
                        "Team1Name": "Queensland",
                        ...
                    }
                ]
            }
        }
    }
    """

    if not isinstance(raw, dict):
        return None

    provider_data = raw.get("data")

    if not isinstance(provider_data, dict):
        return None

    nested_data = provider_data.get("Data")

    if not isinstance(nested_data, dict):
        return None

    score_list = nested_data.get("Score")

    if not isinstance(score_list, list) or not score_list:
        return None

    row = score_list[0]

    if not isinstance(row, dict):
        return None

    # -----------------------------------------------------
    # TEAM 1
    # -----------------------------------------------------

    team1_name = _safe_string(row.get("Team1Name"), "Team 1")
    team1_short = _safe_string(
        row.get("Team1Name_Short"),
        team1_name[:3].upper(),
    )

    team1_flag = _safe_string(row.get("Team1Flag"))

    team1_score_text = _safe_string(
        row.get("Team1OnlyScore")
        or row.get("Team1Score")
    )

    team1_parsed = _extract_score_numbers(team1_score_text)

    team1_runs = _safe_int(
        row.get("Team1ScoreOnly", "").split("-")[0]
        if row.get("Team1ScoreOnly")
        else team1_parsed["runs"]
    )

    team1_wickets = team1_parsed["wickets"]

    if row.get("Team1ScoreOnly"):
        score_only = _safe_string(row.get("Team1ScoreOnly"))

        score_match = re.match(
            r"^\s*(\d+)\s*[-/]\s*(\d+)",
            score_only,
        )

        if score_match:
            team1_runs = _safe_int(score_match.group(1))
            team1_wickets = _safe_int(score_match.group(2))

    team1_overs = _safe_string(
        row.get("Team1Overs"),
        team1_parsed["overs"],
    )

    # -----------------------------------------------------
    # TEAM 2
    # -----------------------------------------------------

    team2_name = _safe_string(row.get("Team2Name"), "Team 2")
    team2_short = _safe_string(
        row.get("Team2Name_Short"),
        team2_name[:3].upper(),
    )

    team2_flag = _safe_string(row.get("Team2Flag"))

    team2_score_text = _safe_string(
        row.get("Team2OnlyScore")
        or row.get("Team2Score")
    )

    team2_parsed = _extract_score_numbers(team2_score_text)

    team2_runs = _safe_int(
        row.get("Team2ScoreOnly", "").split("-")[0]
        if row.get("Team2ScoreOnly")
        else team2_parsed["runs"]
    )

    team2_wickets = team2_parsed["wickets"]

    if row.get("Team2ScoreOnly"):
        score_only = _safe_string(row.get("Team2ScoreOnly"))

        score_match = re.match(
            r"^\s*(\d+)\s*[-/]\s*(\d+)",
            score_only,
        )

        if score_match:
            team2_runs = _safe_int(score_match.group(1))
            team2_wickets = _safe_int(score_match.group(2))

    team2_overs = _safe_string(
        row.get("Team2Overs"),
        team2_parsed["overs"],
    )

    # -----------------------------------------------------
    # CURRENT INNINGS
    # -----------------------------------------------------

    current_inning = _safe_int(
        row.get("CurrentInning"),
        0,
    )

    if current_inning == 2:
        batting_team = team2_name
        bowling_team = team1_name
    elif current_inning == 1:
        batting_team = team1_name
        bowling_team = team2_name
    else:
        batting_team = ""
        bowling_team = ""

    # -----------------------------------------------------
    # TARGET / CHASE
    # -----------------------------------------------------

    target = _safe_int(row.get("Target"))

    required_runs = 0
    required_overs = ""
    required_balls = 0

    status_text = _safe_string(
        row.get("ScoreStatus")
        or row.get("NRMsg")
        or row.get("Message")
    )

    # Example:
    #
    # Victoria Need 324 Runs In 47.5 Overs (287 Balls) To Win
    #
    chase_match = re.search(
        r"Need\s+(\d+)\s+Runs\s+In\s+"
        r"([0-9]+(?:\.[0-9]+)?)\s+Overs"
        r"(?:\s*\((\d+)\s*Balls\))?",
        status_text,
        re.IGNORECASE,
    )

    if chase_match:
        required_runs = _safe_int(chase_match.group(1))
        required_overs = _safe_string(chase_match.group(2))
        required_balls = _safe_int(chase_match.group(3))

    if target <= 0 and current_inning == 2:
        target = team1_runs + 1

    if required_runs <= 0 and target > 0 and current_inning == 2:
        required_runs = max(target - team2_runs, 0)

    # -----------------------------------------------------
    # BATTERS
    # -----------------------------------------------------

    player1_name_raw = _safe_string(row.get("Player1"))
    player2_name_raw = _safe_string(row.get("Player2"))

    player1 = {
        "id": _safe_string(row.get("Player1ID")),
        "name": _clean_name(player1_name_raw),
        "display_name": player1_name_raw,
        "runs": _safe_int(row.get("Player1Run")),
        "balls": _safe_int(row.get("Player1Balls")),
        "fours": _safe_int(row.get("Player1Fours")),
        "sixes": _safe_int(row.get("Player1Sixes")),
        "strike_rate": _safe_float(row.get("Player1StrikeRate")),
        "image": _safe_string(row.get("Player1Image")),
        "is_striker": "*" in player1_name_raw,
    }

    player2 = {
        "id": _safe_string(row.get("Player2ID")),
        "name": _clean_name(player2_name_raw),
        "display_name": player2_name_raw,
        "runs": _safe_int(row.get("Player2Run")),
        "balls": _safe_int(row.get("Player2Balls")),
        "fours": _safe_int(row.get("Player2Fours")),
        "sixes": _safe_int(row.get("Player2Sixes")),
        "strike_rate": _safe_float(row.get("Player2StrikeRate")),
        "image": _safe_string(row.get("Player2Image")),
        "is_striker": "*" in player2_name_raw,
    }

    batters = []

    if player1["name"]:
        batters.append(player1)

    if player2["name"]:
        batters.append(player2)

    # -----------------------------------------------------
    # BOWLER
    # -----------------------------------------------------

    bowler_name = _safe_string(row.get("Bowler"))

    bowler = {
        "id": _safe_string(row.get("BowlerID")),
        "name": bowler_name or "-",
        "image": _safe_string(row.get("BowlerImage")),
        "overs": _safe_string(row.get("BowlerOver"), "0"),
        "maidens": _safe_int(row.get("BowlerMaiden")),
        "runs": _safe_int(row.get("BowlerRun")),
        "wickets": _safe_int(row.get("BowlerWicket")),
        "economy": _safe_float(row.get("BowlerEconomy")),
    }

    # -----------------------------------------------------
    # LAST 6 BALLS
    # -----------------------------------------------------

    last6_balls = row.get("Last6Balls")

    if isinstance(last6_balls, list):
        last6 = [
            _safe_string(ball)
            for ball in last6_balls
            if _safe_string(ball)
        ]
    else:
        last6 = []

        for i in range(1, 7):
            value = _safe_string(row.get(f"Last6Balls{i}"))

            if value:
                last6.append(value)

    # -----------------------------------------------------
    # CURRENT OVER BALLS
    # -----------------------------------------------------

    current_over_balls = []

    for i in range(1, 7):
        value = _safe_string(
            row.get(f"CurrentOverBalls{i}")
        )

        if value:
            current_over_balls.append(value)

    # -----------------------------------------------------
    # LAST 4 OVERS
    # -----------------------------------------------------

    last4_overs_raw = row.get("Last4Overs")

    last4_overs: List[Dict[str, Any]] = []

    if isinstance(last4_overs_raw, list):
        for over in last4_overs_raw:
            if not isinstance(over, dict):
                continue

            balls = over.get("balls")

            if not isinstance(balls, list):
                balls = []

            last4_overs.append(
                {
                    "over": _safe_int(over.get("over")),
                    "balls": [
                        _safe_string(ball)
                        for ball in balls
                    ],
                    "runs": _safe_int(over.get("runs")),
                }
            )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    score_status = _safe_string(
        row.get("ScoreStatus")
        or row.get("NRMsg")
    )

    message = _safe_string(row.get("Message"))

    live_commentary = _safe_string(
        row.get("LiveCommentary")
    )

    commentary = _safe_string(
        row.get("Commentary")
    )

    # -----------------------------------------------------
    # NORMALIZED INNINGS
    # -----------------------------------------------------

    innings = [
        {
            "team": team1_name,
            "short_name": team1_short,
            "flag": team1_flag,
            "runs": team1_runs,
            "wickets": team1_wickets,
            "overs": team1_overs,
            "score": f"{team1_runs}/{team1_wickets}",
            "full_score": (
                f"{team1_runs}/{team1_wickets}"
                f" ({team1_overs})"
                if team1_overs
                else f"{team1_runs}/{team1_wickets}"
            ),
            "is_current": current_inning == 1,
        },
        {
            "team": team2_name,
            "short_name": team2_short,
            "flag": team2_flag,
            "runs": team2_runs,
            "wickets": team2_wickets,
            "overs": team2_overs,
            "score": f"{team2_runs}/{team2_wickets}",
            "full_score": (
                f"{team2_runs}/{team2_wickets}"
                f" ({team2_overs})"
                if team2_overs
                else f"{team2_runs}/{team2_wickets}"
            ),
            "is_current": current_inning == 2,
        },
    ]

    # -----------------------------------------------------
    # FINAL NORMALIZED SCORE
    # -----------------------------------------------------

    return {
        "success": True,

        "status": "LIVE" if live_commentary == "1" else "AVAILABLE",

        "message": message,

        "current_inning": current_inning,

        "batting_team": batting_team,
        "bowling_team": bowling_team,

        "team1": team1_name,
        "team1_short": team1_short,
        "team1_flag": team1_flag,
        "team1_score": f"{team1_runs}/{team1_wickets}",
        "team1_runs": team1_runs,
        "team1_wickets": team1_wickets,
        "team1_overs": team1_overs,

        "team2": team2_name,
        "team2_short": team2_short,
        "team2_flag": team2_flag,
        "team2_score": f"{team2_runs}/{team2_wickets}",
        "team2_runs": team2_runs,
        "team2_wickets": team2_wickets,
        "team2_overs": team2_overs,

        "innings": innings,

        "crr": _safe_float(row.get("CRR")),
        "rrr": _safe_float(row.get("RRR")),

        "target": target,
        "required_runs": required_runs,
        "required_overs": required_overs,
        "required_balls": required_balls,

        "score_status": score_status,
        "nr_message": _safe_string(row.get("NRMsg")),

        "batters": batters,

        "player1": player1,
        "player2": player2,

        "bowler": bowler,

        "last6_balls": last6,
        "current_over_balls": current_over_balls,
        "last4_overs": last4_overs,

        "live_commentary": live_commentary,
        "commentary": commentary,

        "raw_score": row,
    }


# =========================================================
# GENERIC SCORE NORMALIZER
# =========================================================

def normalize_score(raw: Any) -> Dict[str, Any]:
    """
    Main score normalizer.

    First handles the exact CricketBZ structure.
    Then falls back to a generic parser for older/alternate
    score response structures.
    """

    exact = _parse_cricketbz_score(raw)

    if exact:
        return exact

    # -----------------------------------------------------
    # Generic fallback
    # -----------------------------------------------------

    if not isinstance(raw, dict):
        return {
            "success": False,
            "message": "Invalid score response",
            "raw": raw,
        }

    # Try to locate a likely score object.
    score_object: Optional[Dict[str, Any]] = None

    def walk(value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            keys = {
                str(k).lower()
                for k in value.keys()
            }

            if (
                "team1" in keys
                or "team1name" in keys
                or "team2" in keys
                or "team2name" in keys
                or "innings" in keys
            ):
                return value

            for child in value.values():
                found = walk(child)

                if found:
                    return found

        elif isinstance(value, list):
            for child in value:
                found = walk(child)

                if found:
                    return found

        return None

    score_object = walk(raw)

    if score_object is None:
        return {
            "success": False,
            "message": "Score data unavailable",
            "raw": raw,
        }

    team1_name = _safe_string(
        _first_value(
            score_object,
            "Team1Name",
            "team1Name",
            "team1",
        ),
        "Team 1",
    )

    team2_name = _safe_string(
        _first_value(
            score_object,
            "Team2Name",
            "team2Name",
            "team2",
        ),
        "Team 2",
    )

    team1_score = _safe_string(
        _first_value(
            score_object,
            "Team1Score",
            "team1Score",
            "score1",
        )
    )

    team2_score = _safe_string(
        _first_value(
            score_object,
            "Team2Score",
            "team2Score",
            "score2",
        )
    )

    parsed1 = _extract_score_numbers(team1_score)
    parsed2 = _extract_score_numbers(team2_score)

    return {
        "success": True,
        "status": "AVAILABLE",

        "current_inning": _safe_int(
            _first_value(
                score_object,
                "CurrentInning",
                "currentInning",
            )
        ),

        "batting_team": "",
        "bowling_team": "",

        "team1": team1_name,
        "team1_short": team1_name[:3].upper(),
        "team1_flag": "",
        "team1_score": (
            f"{parsed1['runs']}/{parsed1['wickets']}"
        ),
        "team1_runs": parsed1["runs"],
        "team1_wickets": parsed1["wickets"],
        "team1_overs": parsed1["overs"],

        "team2": team2_name,
        "team2_short": team2_name[:3].upper(),
        "team2_flag": "",
        "team2_score": (
            f"{parsed2['runs']}/{parsed2['wickets']}"
        ),
        "team2_runs": parsed2["runs"],
        "team2_wickets": parsed2["wickets"],
        "team2_overs": parsed2["overs"],

        "innings": [],

        "crr": _safe_float(
            _first_value(
                score_object,
                "CRR",
                "crr",
            )
        ),

        "rrr": _safe_float(
            _first_value(
                score_object,
                "RRR",
                "rrr",
            )
        ),

        "target": _safe_int(
            _first_value(
                score_object,
                "Target",
                "target",
            )
        ),

        "required_runs": 0,
        "required_overs": "",
        "required_balls": 0,

        "score_status": _safe_string(
            _first_value(
                score_object,
                "ScoreStatus",
                "scoreStatus",
                "message",
            )
        ),

        "nr_message": "",

        "batters": [],
        "player1": {},
        "player2": {},

        "bowler": {
            "name": "-",
            "overs": "0",
            "maidens": 0,
            "runs": 0,
            "wickets": 0,
            "economy": 0,
            "image": "",
        },

        "last6_balls": [],
        "current_over_balls": [],
        "last4_overs": [],

        "live_commentary": "",
        "commentary": "",

        "raw_score": score_object,
        "raw": raw,
    }


# =========================================================
# MATCH NORMALIZER
# =========================================================

def _normalize_match(match: Dict[str, Any]) -> Dict[str, Any]:
    game_id = _safe_string(
        _first_value(
            match,
            "gameId",
            "game_id",
            "gameID",
            "id",
        )
    )

    market_id = _safe_string(
        _first_value(
            match,
            "marketId",
            "market_id",
            "marketID",
        )
    )

    event_id = _safe_string(
        _first_value(
            match,
            "eventId",
            "event_id",
            "eventID",
        )
    )

    event_name = _safe_string(
        _first_value(
            match,
            "eventName",
            "event_name",
            "name",
        ),
        "Cricket Match",
    )

    event_time = _first_value(
        match,
        "eventTime",
        "event_time",
        "startTime",
        "start_time",
    )

    in_play = _first_value(
        match,
        "inPlay",
        "in_play",
        "inplay",
    )

    if isinstance(in_play, str):
        in_play = in_play.lower() in {
            "1",
            "true",
            "yes",
            "live",
        }

    in_play = bool(in_play)

    tv = _first_value(
        match,
        "tv",
        "TV",
        "video",
    )

    team1 = _safe_string(
        _first_value(
            match,
            "runnerName1",
            "runner_name1",
            "team1",
            "team1Name",
        )
    )

    team2 = _safe_string(
        _first_value(
            match,
            "runnerName2",
            "runner_name2",
            "team2",
            "team2Name",
        )
    )

    team3 = _safe_string(
        _first_value(
            match,
            "runnerName3",
            "runner_name3",
            "team3",
            "team3Name",
        )
    )

    score_id = _safe_string(
        _first_value(
            match,
            "scoreId",
            "score_id",
        )
    )

    result_id = _safe_string(
        _first_value(
            match,
            "resultId",
            "result_id",
        )
    )

    # In many ProExch responses scoreId is absent.
    # The game ID can be used by the CricketBZ fallback.
    if not score_id:
        score_id = game_id

    return {
        "game_id": game_id,
        "market_id": market_id,
        "event_id": event_id,

        "event_name": event_name,
        "event_time": event_time,

        "in_play": in_play,
        "tv": tv,

        "score_id": score_id,
        "result_id": result_id,

        "team1": team1,
        "team2": team2,
        "team3": team3,

        "raw": match,
    }


# =========================================================
# GET MATCHES
# =========================================================

def get_matches(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetch cricket matches from ProExch.
    """

    now = _now()

    if (
        not force_refresh
        and _match_cache["data"] is not None
        and now - _match_cache["timestamp"] < MATCH_CACHE_TTL
    ):
        return _match_cache["data"]

    url = f"{BASE_URL}/api/cricket/matches"

    raw = _request_json(url)

    if raw is None:
        if _match_cache["data"] is not None:
            return _match_cache["data"]

        return {
            "success": False,
            "matches": [],
            "message": "Unable to fetch cricket matches",
        }

    matches_raw: List[Any] = []

    # Expected:
    #
    # {
    #   "statusCode": 200,
    #   "data": {
    #       "data": [...]
    #   }
    # }

    if isinstance(raw, dict):

        data = raw.get("data")

        if isinstance(data, dict):
            nested = data.get("data")

            if isinstance(nested, list):
                matches_raw = nested

            elif isinstance(nested, dict):
                matches_raw = [nested]

        elif isinstance(data, list):
            matches_raw = data

    elif isinstance(raw, list):
        matches_raw = raw

    matches = []

    for item in matches_raw:
        if not isinstance(item, dict):
            continue

        normalized = _normalize_match(item)

        if normalized["game_id"]:
            matches.append(normalized)

    result = {
        "success": True,
        "matches": matches,
        "count": len(matches),
        "raw": raw,
    }

    _match_cache["timestamp"] = now
    _match_cache["data"] = result

    return result


# =========================================================
# FIND MATCH IDS
# =========================================================

def get_match_ids(game_id: str) -> Dict[str, str]:
    """
    Resolve game/event/market/score IDs.
    """

    game_id = _safe_string(game_id)

    result = {
        "game_id": game_id,
        "event_id": "",
        "market_id": "",
        "score_id": game_id,
        "result_id": "",
    }

    matches_response = get_matches()

    matches = matches_response.get(
        "matches",
        [],
    )

    for match in matches:

        if _safe_string(
            match.get("game_id")
        ) != game_id:
            continue

        result["event_id"] = _safe_string(
            match.get("event_id")
        )

        result["market_id"] = _safe_string(
            match.get("market_id")
        )

        result["score_id"] = _safe_string(
            match.get("score_id")
        ) or game_id

        result["result_id"] = _safe_string(
            match.get("result_id")
        )

        break

    return result


# =========================================================
# GET ODDS
# =========================================================

def get_odds(
    game_id: str,
    event_id: Optional[str] = None,
    market_id: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Fetch cricket odds from ProExch.
    """

    game_id = _safe_string(game_id)
    event_id = _safe_string(event_id)
    market_id = _safe_string(market_id)

    ids = get_match_ids(game_id)

    if not event_id:
        event_id = ids.get("event_id", "")

    if not market_id:
        market_id = ids.get("market_id", "")

    cache_key = (
        f"{game_id}|"
        f"{event_id}|"
        f"{market_id}"
    )

    now = _now()

    cached = _odds_cache.get(cache_key)

    if (
        not force_refresh
        and cached
        and now - cached["timestamp"] < ODDS_CACHE_TTL
    ):
        return cached["data"]

    params = {
        "gameId": game_id,
    }

    if event_id:
        params["eventId"] = event_id

    if market_id:
        params["marketId"] = market_id

    url = f"{BASE_URL}/api/cricket/odds"

    raw = _request_json(
        url,
        params=params,
    )

    if raw is None:
        return {
            "success": False,
            "game_id": game_id,
            "event_id": event_id,
            "market_id": market_id,
            "match_odds": [],
            "bookmaker_odds": [],
            "fancy_odds": [],
            "other_market_odds": [],
            "message": "Unable to fetch odds",
        }

    normalized = normalize_odds(
        raw,
        game_id=game_id,
        event_id=event_id,
        market_id=market_id,
    )

    _odds_cache[cache_key] = {
        "timestamp": now,
        "data": normalized,
    }

    return normalized


# =========================================================
# ODDS NORMALIZER
# =========================================================

def _normalize_runner(runner: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _safe_string(
            _first_value(
                runner,
                "id",
                "selectionId",
                "selection_id",
                "runnerId",
            )
        ),

        "name": _safe_string(
            _first_value(
                runner,
                "name",
                "runnerName",
                "rname",
            ),
            "Runner",
        ),

        "status": _safe_string(
            _first_value(
                runner,
                "status",
            ),
            "OPEN",
        ),

        "back": _safe_float(
            _first_value(
                runner,
                "back",
                "backPrice",
                "b1",
                "back1",
            )
        ),

        "back_size": _safe_float(
            _first_value(
                runner,
                "back_size",
                "backSize",
                "bs1",
            )
        ),

        "lay": _safe_float(
            _first_value(
                runner,
                "lay",
                "layPrice",
                "l1",
                "lay1",
            )
        ),

        "lay_size": _safe_float(
            _first_value(
                runner,
                "lay_size",
                "laySize",
                "ls1",
            )
        ),

        "back_price": _safe_float(
            _first_value(
                runner,
                "back_price",
                "backPrice",
                "b1",
            )
        ),

        "lay_price": _safe_float(
            _first_value(
                runner,
                "lay_price",
                "layPrice",
                "l1",
            )
        ),

        "raw": runner,
    }


def _normalize_market(
    market: Dict[str, Any],
    market_type: str,
) -> Dict[str, Any]:

    odd_datas = market.get("oddDatas")

    if not isinstance(odd_datas, list):
        odd_datas = market.get("runners")

    if not isinstance(odd_datas, list):
        odd_datas = []

    runners = []

    for item in odd_datas:
        if isinstance(item, dict):
            runners.append(
                _normalize_runner(item)
            )

    return {
        "id": _safe_string(
            _first_value(
                market,
                "id",
                "marketId",
                "market_id",
            )
        ),

        "name": _safe_string(
            _first_value(
                market,
                "name",
                "marketName",
                "market_name",
            ),
            market_type.replace("_", " ").title(),
        ),

        "status": _safe_string(
            _first_value(
                market,
                "status",
            ),
            "OPEN",
        ),

        "type": market_type,

        "runners": runners,

        "raw": market,
    }


def normalize_odds(
    raw: Any,
    game_id: str = "",
    event_id: str = "",
    market_id: str = "",
) -> Dict[str, Any]:

    match_odds: List[Dict[str, Any]] = []
    bookmaker_odds: List[Dict[str, Any]] = []
    fancy_odds: List[Dict[str, Any]] = []
    other_market_odds: List[Dict[str, Any]] = []

    # -----------------------------------------------------
    # Find provider payload
    # -----------------------------------------------------

    payload = raw

    if isinstance(raw, dict):

        if isinstance(raw.get("data"), dict):
            payload = raw["data"]

        if isinstance(payload, dict):
            nested = payload.get("data")

            if isinstance(nested, dict):
                payload = nested

    if not isinstance(payload, dict):
        payload = {}

    # -----------------------------------------------------
    # Match Odds
    # -----------------------------------------------------

    raw_match = payload.get("matchOdds")

    if isinstance(raw_match, dict):
        match_odds.append(
            _normalize_market(
                raw_match,
                "match_odds",
            )
        )

    elif isinstance(raw_match, list):
        for market in raw_match:
            if isinstance(market, dict):
                match_odds.append(
                    _normalize_market(
                        market,
                        "match_odds",
                    )
                )

    # -----------------------------------------------------
    # Bookmaker
    # -----------------------------------------------------

    raw_bookmaker = (
        payload.get("bookmakerOdds")
        or payload.get("bookMakerOdds")
        or payload.get("bookmaker")
    )

    if isinstance(raw_bookmaker, dict):
        bookmaker_odds.append(
            _normalize_market(
                raw_bookmaker,
                "bookmaker",
            )
        )

    elif isinstance(raw_bookmaker, list):
        for market in raw_bookmaker:
            if isinstance(market, dict):
                bookmaker_odds.append(
                    _normalize_market(
                        market,
                        "bookmaker",
                    )
                )

    # -----------------------------------------------------
    # Fancy / Session
    # -----------------------------------------------------

    raw_fancy = payload.get("fancyOdds")

    if isinstance(raw_fancy, dict):
        fancy_odds.append(
            _normalize_market(
                raw_fancy,
                "fancy",
            )
        )

    elif isinstance(raw_fancy, list):
        for market in raw_fancy:
            if isinstance(market, dict):
                fancy_odds.append(
                    _normalize_market(
                        market,
                        "fancy",
                    )
                )

    # -----------------------------------------------------
    # Other markets
    # -----------------------------------------------------

    raw_other = (
        payload.get("otherMarketOdds")
        or payload.get("otherMarkets")
        or payload.get("other_market_odds")
    )

    if isinstance(raw_other, dict):
        other_market_odds.append(
            _normalize_market(
                raw_other,
                "other_market",
            )
        )

    elif isinstance(raw_other, list):
        for market in raw_other:
            if isinstance(market, dict):
                other_market_odds.append(
                    _normalize_market(
                        market,
                        "other_market",
                    )
                )

    return {
        "success": True,

        "game_id": game_id,
        "event_id": event_id,
        "market_id": market_id,

        "match_odds": match_odds,
        "bookmaker_odds": bookmaker_odds,
        "fancy_odds": fancy_odds,
        "other_market_odds": other_market_odds,

        "raw": raw,
    }


# =========================================================
# GET SCORE
# =========================================================

def get_score(
    score_id: str,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Fetch live score.

    Primary:
        https://cricketbz.app/getScore/{score_id}

    Fallback:
        ProExch /api/cricket/cricketbz?gameId={score_id}
    """

    score_id = _safe_string(score_id)

    if not score_id:
        return {
            "success": False,
            "message": "Missing score ID",
        }

    now = _now()

    cached = _score_cache.get(score_id)

    if (
        not force_refresh
        and cached
        and now - cached["timestamp"] < SCORE_CACHE_TTL
    ):
        result = dict(cached["data"])

        result["source"] = "cache"
        result["cached"] = True

        return result

    # -----------------------------------------------------
    # PRIMARY: CricketBZ
    # -----------------------------------------------------

    url = (
        f"{CRICKETBZ_BASE_URL}/getScore/"
        f"{score_id}"
    )

    raw = _request_json(url)

    normalized = None

    if raw is not None:
        normalized = normalize_score(raw)

    # -----------------------------------------------------
    # FALLBACK: PROEXCH
    # -----------------------------------------------------

    if (
        normalized is None
        or not normalized.get("success")
        or not normalized.get("innings")
    ):
        fallback = get_cricketbz(score_id)

        if fallback.get("success"):
            fallback_raw = fallback.get("raw")

            fallback_normalized = normalize_score(
                fallback_raw
            )

            if fallback_normalized.get("success"):
                normalized = fallback_normalized
                raw = fallback_raw

    # -----------------------------------------------------
    # FAILED
    # -----------------------------------------------------

    if normalized is None:
        normalized = {
            "success": False,
            "message": "Score currently unavailable",
            "score_id": score_id,
        }

    normalized["score_id"] = score_id
    normalized["source"] = (
        "cricketbz"
        if raw is not None
        else "unavailable"
    )
    normalized["cached"] = False

    _score_cache[score_id] = {
        "timestamp": now,
        "data": normalized,
    }

    return normalized


# =========================================================
# GET CRICKETBZ THROUGH PROEXCH
# =========================================================

def get_cricketbz(
    game_id: str,
    force_refresh: bool = False,
) -> Dict[str, Any]:

    game_id = _safe_string(game_id)

    if not game_id:
        return {
            "success": False,
            "message": "Missing game ID",
        }

    url = f"{BASE_URL}/api/cricket/cricketbz"

    raw = _request_json(
        url,
        params={
            "gameId": game_id,
        },
    )

    if raw is None:
        return {
            "success": False,
            "message": "Unable to fetch CricketBZ data",
        }

    return {
        "success": True,
        "game_id": game_id,
        "raw": raw,
    }


# =========================================================
# GET VIDEO
# =========================================================

def get_video(
    game_id: str,
) -> Dict[str, Any]:

    game_id = _safe_string(game_id)

    if not game_id:
        return {
            "success": False,
            "message": "Missing game ID",
        }

    url = f"{BASE_URL}/api/cricket/video"

    raw = _request_json(
        url,
        params={
            "gameId": game_id,
        },
    )

    if raw is None:
        return {
            "success": False,
            "game_id": game_id,
            "video": None,
            "message": "Video unavailable",
        }

    video = None

    if isinstance(raw, dict):

        data = raw.get("data")

        if isinstance(data, dict):
            video = (
                data.get("video")
                or data.get("url")
                or data.get("videoUrl")
            )

        elif isinstance(data, str):
            video = data

        if not video:
            video = (
                raw.get("video")
                or raw.get("url")
                or raw.get("videoUrl")
            )

    return {
        "success": True,
        "game_id": game_id,
        "video": video,
        "raw": raw,
    }


# =========================================================
# GET RESULT
# =========================================================

def get_result(
    result_id: str,
    force_refresh: bool = False,
) -> Dict[str, Any]:

    result_id = _safe_string(result_id)

    if not result_id:
        return {
            "success": False,
            "message": "Missing result ID",
        }

    now = _now()

    cached = _result_cache.get(result_id)

    if (
        not force_refresh
        and cached
        and now - cached["timestamp"] < RESULT_CACHE_TTL
    ):
        return cached["data"]

    # Try ProExch result endpoint.
    possible_urls = [
        f"{BASE_URL}/api/cricket/result",
        f"{BASE_URL}/api/cricket/results",
    ]

    raw = None

    for url in possible_urls:

        raw = _request_json(
            url,
            params={
                "resultId": result_id,
                "result_id": result_id,
                "gameId": result_id,
            },
        )

        if raw is not None:
            break

    if raw is None:
        result = {
            "success": False,
            "result_id": result_id,
            "message": "Result unavailable",
        }

        return result

    result = {
        "success": True,
        "result_id": result_id,
        "data": raw,
        "raw": raw,
    }

    _result_cache[result_id] = {
        "timestamp": now,
        "data": result,
    }

    return result


# =========================================================
# CACHE CLEAR
# =========================================================

def clear_caches() -> None:
    """
    Clear all local ProExch/score caches.
    """

    _match_cache["timestamp"] = 0.0
    _match_cache["data"] = None

    _odds_cache.clear()
    _score_cache.clear()
    _result_cache.clear()


# =========================================================
# CONVENIENCE ALIASES
# =========================================================

fetch_matches = get_matches
fetch_odds = get_odds
fetch_score = get_score
fetch_result = get_result
fetch_video = get_video