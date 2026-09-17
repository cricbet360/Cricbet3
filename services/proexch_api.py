import requests
from urllib.parse import quote


# =========================================================
# PROEXCH CONFIG
# =========================================================

BASE_URL = "https://apidata.proexch.in"

TIMEOUT = 15

session = requests.Session()


# =========================================================
# ERROR
# =========================================================

class ProExchError(Exception):
    pass


# =========================================================
# COMMON REQUEST
# =========================================================

def _request(
    path,
    params=None,
    timeout=TIMEOUT,
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
            f"ProExch HTTP {response.status_code}: "
            f"{payload}"
        )

    provider_status = payload.get(
        "statusCode"
    )

    if provider_status is not None:

        if provider_status != 200:

            raise ProExchError(
                f"ProExch returned statusCode="
                f"{provider_status}: {payload}"
            )

    return payload


# =========================================================
# DATA UNWRAPPER
# =========================================================

def _unwrap_data(payload):

    if not isinstance(
        payload,
        dict,
    ):
        return payload

    data = payload.get(
        "data"
    )

    if isinstance(
        data,
        dict,
    ):

        nested = data.get(
            "data"
        )

        if nested is not None:

            return nested

    return data


# =========================================================
# HEALTH
# =========================================================

def health_check():

    return _request(
        "/api/cricket/matches"
    )


# =========================================================
# MATCHES
# =========================================================

def get_matches():

    payload = _request(
        "/api/cricket/matches"
    )

    data = _unwrap_data(payload)

    if not isinstance(data, list):
        return []

    return data

# =========================================================
# FIND MATCH
# =========================================================

def find_match(
    game_id,
):

    payload = get_matches()

    data = _unwrap_data(
        payload
    )

    if not isinstance(
        data,
        list,
    ):
        data = []

    for item in data:

        if not isinstance(
            item,
            dict,
        ):
            continue

        item_game_id = (
            item.get("gameId")
            or item.get("game_id")
            or item.get("eventId")
            or item.get("event_id")
        )

        if item_game_id is None:
            continue

        if str(
            item_game_id
        ) == str(
            game_id
        ):

            return item

    return None


# =========================================================
# EVENT ID
# =========================================================

def _extract_event_id(
    match,
):

    if not isinstance(
        match,
        dict,
    ):
        return None

    return (
        match.get("eventId")
        or match.get("event_id")
        or match.get("gameId")
        or match.get("game_id")
    )


# =========================================================
# MARKET ID
# =========================================================

def _extract_market_id(
    match,
):

    if not isinstance(
        match,
        dict,
    ):
        return None

    return (
        match.get("marketId")
        or match.get("market_id")
    )


# =========================================================
# RESOLVE MATCH IDS
# =========================================================

def resolve_match_ids(
    game_id,
    event_id=None,
    market_id=None,
):

    game_id = (
        str(game_id).strip()
        if game_id is not None
        else ""
    )

    if not game_id:

        raise ProExchError(
            "gameId is required."
        )

    if event_id is not None:

        event_id = str(
            event_id
        ).strip()

        if not event_id:
            event_id = None

    if market_id is not None:

        market_id = str(
            market_id
        ).strip()

        if not market_id:
            market_id = None

    # -----------------------------------------------------
    # If event ID already exists, use supplied values.
    # -----------------------------------------------------

    if event_id:

        return (
            game_id,
            event_id,
            market_id,
        )

    # -----------------------------------------------------
    # Resolve from matches API
    # -----------------------------------------------------

    match = find_match(
        game_id
    )

    if not match:

        raise ProExchError(
            f"Match not found for game_id={game_id}"
        )

    resolved_event_id = (
        _extract_event_id(
            match
        )
    )

    resolved_market_id = (
        _extract_market_id(
            match
        )
    )

    final_market_id = (
        market_id
        if market_id
        else resolved_market_id
    )

    if not resolved_event_id:

        raise ProExchError(
            "ProExch matches API did not return "
            f"eventId for gameId={game_id}."
        )

    return (
        game_id,
        resolved_event_id,
        final_market_id,
    )


# =========================================================
# ODDS
# =========================================================

def get_odds(
    game_id,
    event_id=None,
    market_id=None,
):

    (
        game_id,
        event_id,
        market_id,
    ) = resolve_match_ids(
        game_id=game_id,
        event_id=event_id,
        market_id=market_id,
    )

    if not event_id:

        raise ProExchError(
            "Unable to resolve event_id "
            "for ProExch odds."
        )

    params = {
        "gameId": game_id,
        "eventId": event_id,
    }

    if market_id:

        params["marketId"] = market_id

    return _request(
        "/api/cricket/odds",
        params=params,
    )


# =========================================================
# RESULTS
# =========================================================

def get_results(
    market_ids,
):

    if isinstance(
        market_ids,
        (list, tuple),
    ):

        market_ids = ",".join(
            str(value).strip()
            for value in market_ids
            if value is not None
            and str(value).strip()
        )

    if not market_ids:

        return {
            "statusCode": 200,
            "data": {
                "data": []
            },
        }

    return _request(
        "/api/betfair-result",
        params={
            "sport": "cricket",
            "type": "new_fancy",
            "marketId": market_ids,
        },
    )


# =========================================================
# NUMBER HELPERS
# =========================================================

def _to_float(
    value,
):

    if value is None:
        return None

    try:

        number = float(
            str(value).strip()
        )

        if number <= 0:
            return None

        return number

    except (
        TypeError,
        ValueError,
    ):

        return None


def _extract_price(
    data,
    keys,
):

    if not isinstance(
        data,
        dict,
    ):
        return None

    for key in keys:

        value = data.get(
            key
        )

        if value is None:
            continue

        if isinstance(
            value,
            dict,
        ):

            for nested_key in (
                "price",
                "odds",
                "rate",
                "value",
            ):

                nested_value = (
                    value.get(
                        nested_key
                    )
                )

                if nested_value is not None:

                    result = _to_float(
                        nested_value
                    )

                    if result is not None:
                        return result

        result = _to_float(
            value
        )

        if result is not None:
            return result

    return None


# =========================================================
# PARSE MATCH ODDS
# =========================================================

def parse_match_odds(
    match_odds_raw,
):

    if not isinstance(
        match_odds_raw,
        list,
    ):
        return []

    parsed = []

    for market in match_odds_raw:

        if not isinstance(
            market,
            dict,
        ):
            continue

        market_name = (
            market.get("mname")
            or market.get("mName")
            or market.get("marketName")
            or market.get("market")
            or "MATCH ODDS"
        )

        odd_datas = market.get(
            "oddDatas"
        )

        if not isinstance(
            odd_datas,
            list,
        ):
            odd_datas = []

        runners = []

        for odd in odd_datas:

            if not isinstance(
                odd,
                dict,
            ):
                continue

            selection_id = (
                odd.get("sid")
                or odd.get("selectionId")
                or odd.get("selection_id")
            )

            runner_name = (
                odd.get("rname")
                or odd.get("sName")
                or odd.get("runnerName")
                or odd.get("selectionName")
                or odd.get("name")
                or ""
            )

            back = _extract_price(
                odd,
                [
                    "b1",
                    "back",
                    "backPrice",
                    "backOdds",
                    "b1Price",
                ],
            )

            lay = _extract_price(
                odd,
                [
                    "l1",
                    "lay",
                    "layPrice",
                    "layOdds",
                    "l1Price",
                ],
            )

            back_size = _extract_price(
                odd,
                [
                    "bs1",
                    "backSize",
                    "backVolume",
                    "b1Size",
                ],
            )

            lay_size = _extract_price(
                odd,
                [
                    "ls1",
                    "laySize",
                    "layVolume",
                    "l1Size",
                ],
            )

            runners.append(
                {
                    "selection_id": (
                        str(selection_id)
                        if selection_id is not None
                        else ""
                    ),
                    "name": str(
                        runner_name
                    ),
                    "back": back,
                    "lay": lay,
                    "back_size": back_size,
                    "lay_size": lay_size,
                    "raw": odd,
                }
            )

        parsed.append(
            {
                "name": str(
                    market_name
                ),
                "market_name": str(
                    market_name
                ),
                "status": (
                    market.get("mstatus")
                    or market.get("status")
                    or ""
                ),
                "runners": runners,
                "raw": market,
            }
        )

    return parsed


# =========================================================
# PARSE FANCY ODDS
# =========================================================

def parse_fancy_odds(
    fancy_odds_raw,
):

    if not isinstance(
        fancy_odds_raw,
        list,
    ):
        return []

    parsed = []

    for market in fancy_odds_raw:

        if not isinstance(
            market,
            dict,
        ):
            continue

        market_name = (
            market.get("mName")
            or market.get("mname")
            or market.get("marketName")
            or market.get("name")
            or "FANCY"
        )

        odd_datas = market.get(
            "oddDatas"
        )

        if not isinstance(
            odd_datas,
            list,
        ):
            odd_datas = []

        rows = []

        for odd in odd_datas:

            if not isinstance(
                odd,
                dict,
            ):
                continue

            sid = (
                odd.get("sid")
                or odd.get("selectionId")
                or odd.get("selection_id")
            )

            name = (
                odd.get("rname")
                or odd.get("sName")
                or odd.get("runnerName")
                or odd.get("selectionName")
                or odd.get("name")
                or ""
            )

            yes = _extract_price(
                odd,
                [
                    "b1",
                    "yes",
                    "yesPrice",
                    "back",
                    "backPrice",
                ],
            )

            no = _extract_price(
                odd,
                [
                    "l1",
                    "no",
                    "noPrice",
                    "lay",
                    "layPrice",
                ],
            )

            yes_size = _extract_price(
                odd,
                [
                    "bs1",
                    "yesSize",
                ],
            )

            no_size = _extract_price(
                odd,
                [
                    "ls1",
                    "noSize",
                ],
            )

            rows.append(
                {
                    "sid": (
                        str(sid)
                        if sid is not None
                        else ""
                    ),
                    "name": str(
                        name
                    ),
                    "yes": yes,
                    "no": no,
                    "yes_size": yes_size,
                    "no_size": no_size,
                    "raw": odd,
                }
            )

        parsed.append(
            {
                "name": str(
                    market_name
                ),
                "market_name": str(
                    market_name
                ),
                "rows": rows,
                "raw": market,
            }
        )

    return parsed


# =========================================================
# EXTRA CRICKETBZ FEATURES
# =========================================================

CRICKETBZ_BASE_URL = "https://cricketbz.app"


# =========================================================
# CRICKETBZ COMMON REQUEST
# =========================================================

def _cricketbz_request(
    path,
    timeout=TIMEOUT,
):

    url = (
        f"{CRICKETBZ_BASE_URL}{path}"
    )

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

        # Some score/result endpoints can return
        # text instead of JSON.

        return response.text


# =========================================================
# CRICKETBZ RESULT
# =========================================================

def get_cricketbz_result(
    result_id,
):

    result_id = str(
        result_id
    ).strip()

    if not result_id:

        raise ProExchError(
            "resultId is required."
        )

    return _cricketbz_request(
        "/getResults/"
        + quote(
            result_id,
            safe="",
        )
    )


# =========================================================
# CRICKETBZ SCORE
# =========================================================

def get_cricketbz_score(
    score_id,
):

    score_id = str(
        score_id
    ).strip()

    if not score_id:

        raise ProExchError(
            "scoreId is required."
        )

    return _cricketbz_request(
        "/getScore/"
        + quote(
            score_id,
            safe="",
        )
    )


# =========================================================
# PROEXCH VIDEO
# =========================================================

VIDEO_BASE_URL = (
    "https://video.proexch.in"
)


def get_video_stream_url(
    stream_id,
):

    stream_id = str(
        stream_id
    ).strip()

    if not stream_id:

        raise ProExchError(
            "streamId is required."
        )

    return (
        f"{VIDEO_BASE_URL}"
        f"/tv/v4/stream/"
        f"{quote(stream_id, safe='')}"
    )