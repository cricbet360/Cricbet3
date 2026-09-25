
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services import proexch_api


# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/api/cricket",
    tags=["Cricket"],
)


# =========================================================
# AUTH
# =========================================================

def _is_logged_in(
    request: Request,
) -> bool:

    return (
        request.session.get("user_id")
        is not None
    )


# =========================================================
# MATCHES
# =========================================================

@router.get("/matches")
def cricket_matches(
    request: Request,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        matches = (
            proexch_api.get_matches()
        )

        return {
            "success": True,
            "data": matches,
            "count": len(matches),
        }

    except Exception as exc:

        print(
            "[CRICKET] matches error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "cricket matches"
                ),
            },
        )


# =========================================================
# FORCE MATCH REFRESH
# =========================================================

@router.get("/matches/refresh")
def refresh_matches(
    request: Request,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        matches = (
            proexch_api.get_matches(
                force_refresh=True
            )
        )

        return {
            "success": True,
            "data": matches,
            "count": len(matches),
        }

    except Exception as exc:

        print(
            "[CRICKET] match refresh error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to refresh "
                    "cricket matches"
                ),
            },
        )


# =========================================================
# ODDS
# =========================================================

@router.get("/odds")
def cricket_odds(
    request: Request,

    gameId: Optional[str] = None,
    eventId: Optional[str] = None,
    marketId: Optional[str] = None,

    game_id: Optional[str] = None,
    event_id: Optional[str] = None,
    market_id: Optional[str] = None,

    refresh: bool = False,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    # -----------------------------------------------------
    # Accept both frontend naming styles
    # -----------------------------------------------------

    resolved_game_id = (
        gameId
        or game_id
    )

    resolved_event_id = (
        eventId
        or event_id
    )

    resolved_market_id = (
        marketId
        or market_id
    )

    if not resolved_game_id:

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": (
                    "gameId is required"
                ),
            },
        )

    try:

        # -------------------------------------------------
        # Resolve IDs from cached match data.
        # -------------------------------------------------

        ids = (
            proexch_api.get_match_ids(
                resolved_game_id
            )
        )

        if not resolved_market_id:

            resolved_market_id = (
                ids.get(
                    "market_id"
                )
            )

        if not resolved_event_id:

            resolved_event_id = (
                ids.get(
                    "event_id"
                )
            )

        if not resolved_market_id:

            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "detail": (
                        "marketId could not "
                        "be resolved for "
                        "this match"
                    ),
                    "game_id": str(
                        resolved_game_id
                    ),
                },
            )

        print(
            "[CRICKET] odds request:",
            "game_id=",
            resolved_game_id,
            "event_id=",
            resolved_event_id,
            "market_id=",
            resolved_market_id,
        )

        odds = (
            proexch_api.get_odds(
                game_id=resolved_game_id,
                event_id=resolved_event_id,
                market_id=resolved_market_id,
                force_refresh=refresh,
            )
        )

        counts = odds.get(
            "counts",
            {},
        )

        print(
            "[CRICKET] odds received:",
            "match_markets=",
            counts.get(
                "match_markets",
                0,
            ),
            "match_runners=",
            counts.get(
                "match_runners",
                0,
            ),
            "bookmaker_markets=",
            counts.get(
                "bookmaker_markets",
                0,
            ),
            "bookmaker_runners=",
            counts.get(
                "bookmaker_runners",
                0,
            ),
            "fancy_markets=",
            counts.get(
                "fancy_markets",
                0,
            ),
            "fancy_rows=",
            counts.get(
                "fancy_rows",
                0,
            ),
        )

        return {
            "success": True,

            "game_id": str(
                resolved_game_id
            ),

            "event_id": (
                str(resolved_event_id)
                if resolved_event_id
                else str(
                    resolved_game_id
                )
            ),

            "market_id": str(
                resolved_market_id
            ),

            "match_odds": odds.get(
                "match_odds",
                [],
            ),

            "bookmaker_odds": odds.get(
                "bookmaker_odds",
                [],
            ),

            "fancy_odds": odds.get(
                "fancy_odds",
                [],
            ),

            "other_market_odds":
                odds.get(
                    "other_market_odds",
                    [],
                ),

            "counts": counts,
        }

    except ValueError as exc:

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": str(exc),
            },
        )

    except Exception as exc:

        print(
            "[CRICKET] odds error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "cricket odds"
                ),
            },
        )


# =========================================================
# SCOREBOARD
# =========================================================

@router.get("/score/{score_id}")
def cricket_score(
    request: Request,
    score_id: str,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        data = (
            proexch_api.get_score(
                score_id
            )
        )

        return {
            "success": True,
            "score_id": str(
                score_id
            ),
            "data": data,
        }

    except ValueError as exc:

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": str(exc),
            },
        )

    except Exception as exc:

        print(
            "[CRICKET] score error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "scoreboard"
                ),
            },
        )


# =========================================================
# CRICKETBZ RESULT
# =========================================================

@router.get("/results/{result_id}")
def cricket_results(
    request: Request,
    result_id: str,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        data = (
            proexch_api.get_cricketbz_result(
                result_id
            )
        )

        return {
            "success": True,
            "result_id": str(
                result_id
            ),
            "data": data,
        }

    except ValueError as exc:

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": str(exc),
            },
        )

    except Exception as exc:

        print(
            "[CRICKET] result error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "match result"
                ),
            },
        )


# =========================================================
# PROEXCH RESULT / SETTLEMENT
# =========================================================
# Kept separately so the application can access the
# ProExch betfair-result endpoint when needed.

@router.get("/proexch-result/{market_id}")
def proexch_result(
    request: Request,
    market_id: str,
    result_type: str = "new_fancy",
):
  

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        data = (
            proexch_api.get_proexch_betfair_result(
                market_id=market_id,
                result_type=result_type,
            )
        )

        return {
            "success": True,
            "market_id": str(
                market_id
            ),
            "result_type": str(
                result_type
            ),
            "data": data,
        }

    except ValueError as exc:

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": str(exc),
            },
        )

    except Exception as exc:

        print(
            "[CRICKET] ProExch Betfair result error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "ProExch Betfair result"
                ),
            },
        )

# =========================================================
# SINGLE MATCH
# =========================================================

@router.get("/match/{game_id}")
def cricket_match(
    request: Request,
    game_id: str,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        match = (
            proexch_api.find_match(
                game_id
            )
        )

        if not match:

            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "detail": (
                        "Match not found"
                    ),
                },
            )

        market_id = (
            match.get(
                "market_id"
            )
        )

        event_id = (
            match.get(
                "event_id"
            )
        )

        score_id = (
            match.get(
                "score_id"
            )
            or game_id
        )

        result_id = (
            match.get(
                "result_id"
            )
            or game_id
        )

        odds = {
            "match_odds": [],
            "bookmaker_odds": [],
            "fancy_odds": [],
            "other_market_odds": [],
            "counts": {},
        }

        # -------------------------------------------------
        # Load ProExch odds only when market ID exists.
        # -------------------------------------------------

        if market_id:

            odds = (
                proexch_api.get_odds(
                    game_id=game_id,
                    event_id=event_id,
                    market_id=market_id,
                )
            )

        return {
            "success": True,

            "match": match,

            "ids": {
                "game_id": str(
                    game_id
                ),

                "event_id": (
                    str(event_id)
                    if event_id
                    else str(
                        game_id
                    )
                ),

                "market_id": (
                    str(market_id)
                    if market_id
                    else ""
                ),

                "score_id": str(
                    score_id
                ),

                "result_id": str(
                    result_id
                ),
            },

            "odds": odds,
        }

    except Exception as exc:

        print(
            "[CRICKET] single match error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "match"
                ),
            },
        )


# =========================================================
# CRICKETBZ SCORE FOR GAME
# =========================================================
# Convenience endpoint.
# Frontend can simply provide gameId.

@router.get("/match/{game_id}/score")
def cricket_match_score(
    request: Request,
    game_id: str,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        match = (
            proexch_api.find_match(
                game_id
            )
        )

        score_id = (
            match.get("score_id")
            if match
            else None
        )

        score_id = (
            score_id
            or game_id
        )

        data = (
            proexch_api.get_score(
                score_id
            )
        )

        return {
            "success": True,
            "game_id": str(
                game_id
            ),
            "score_id": str(
                score_id
            ),
            "data": data,
        }

    except ValueError as exc:

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": str(exc),
            },
        )

    except Exception as exc:

        print(
            "[CRICKET] match score error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "match score"
                ),
            },
        )


# =========================================================
# CRICKETBZ RESULT FOR GAME
# =========================================================
# Convenience endpoint.
# Frontend can simply provide gameId.

@router.get("/match/{game_id}/result")
def cricket_match_result(
    request: Request,
    game_id: str,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        match = (
            proexch_api.find_match(
                game_id
            )
        )

        result_id = (
            match.get("result_id")
            if match
            else None
        )

        result_id = (
            result_id
            or game_id
        )

        data = (
            proexch_api.get_cricketbz_result(
                result_id
            )
        )

        return {
            "success": True,
            "game_id": str(
                game_id
            ),
            "result_id": str(
                result_id
            ),
            "data": data,
        }

    except ValueError as exc:

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": str(exc),
            },
        )

    except Exception as exc:

        print(
            "[CRICKET] match result error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "match result"
                ),
            },
        )


# =========================================================
# CRICKETBZ / PROEXCH CRICKETBZ DATA
# =========================================================

@router.get("/cricketbz/{game_id}")
def cricketbz_data(
    request: Request,
    game_id: str,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        data = (
            proexch_api.get_cricketbz(
                game_id
            )
        )

        return {
            "success": True,
            "game_id": str(
                game_id
            ),
            "data": data,
        }

    except Exception as exc:

        print(
            "[CRICKET] cricketbz error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "CricketBZ data"
                ),
            },
        )


# =========================================================
# VIDEO
# =========================================================

@router.get("/video/{game_id}")
def cricket_video(
    request: Request,
    game_id: str,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    try:

        data = (
            proexch_api.get_video(
                game_id
            )
        )

        return {
            "success": True,
            "game_id": str(
                game_id
            ),
            "data": data,
        }

    except Exception as exc:

        print(
            "[CRICKET] video error:",
            exc,
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load "
                    "match video"
                ),
            },
        )


# =========================================================
# CLEAR CACHE
# =========================================================

@router.post("/cache/clear")
def clear_cricket_cache(
    request: Request,
):

    if not _is_logged_in(request):

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Login required"
            },
        )

    proexch_api.clear_cache()

    return {
        "success": True,
        "message": (
            "Cricket cache cleared"
        ),
    }

# =========================================================
# TEST PROEXCH BETFAIR RESULT - ANY MARKET ID
# =========================================================

@router.get("/test-result/{market_id}")
def test_proexch_result(
    request: Request,
    market_id: str,
    result_type: str = "new_fancy",
):
    """
    Test ProExch Betfair result for ANY market ID.

    Examples:

    Fancy:
    /api/cricket/test-result/36074941_55?result_type=new_fancy

    Match Odds:
    /api/cricket/test-result/36074941?result_type=match_odds

    Bookmaker:
    /api/cricket/test-result/36095117?result_type=bookmaker
    """

    if not _is_logged_in(request):
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "detail": "Login required",
            },
        )

    market_id = str(
        market_id or ""
    ).strip()

    result_type = str(
        result_type or "new_fancy"
    ).strip()

    if not market_id:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": "market_id is required",
            },
        )

    if not result_type:
        result_type = "new_fancy"

    try:

        data = proexch_api.get_proexch_betfair_result(
            market_id=market_id,
            result_type=result_type,
        )

        return {
            "success": True,
            "market_id": market_id,
            "result_type": result_type,
            "data": data,
        }

    except Exception as exc:

        print(
            "[CRICKET] test result error:",
            repr(exc),
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "market_id": market_id,
                "result_type": result_type,
                "detail": str(exc),
            },
        )