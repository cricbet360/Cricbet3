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

        matches = proexch_api.get_matches()

        return {
            "success": True,
            "data": matches,
            "count": len(matches),
        }

    except Exception as exc:

        print(
            f"[CRICKET] matches error: {exc}"
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load cricket matches"
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

        matches = proexch_api.get_matches(
            force_refresh=True
        )

        return {
            "success": True,
            "data": matches,
            "count": len(matches),
        }

    except Exception as exc:

        print(
            f"[CRICKET] match refresh error: {exc}"
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to refresh cricket matches"
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

    game_id = (
        gameId
        or game_id
    )

    event_id = (
        eventId
        or event_id
    )

    market_id = (
        marketId
        or market_id
    )

    if not game_id:

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "detail": "gameId is required",
            },
        )

    try:

        # -------------------------------------------------
        # If marketId wasn't supplied, resolve it from
        # the short-lived matches cache.
        # -------------------------------------------------

        if not market_id:

            ids = proexch_api.get_match_ids(
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

            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "detail": (
                        "marketId could not be "
                        "resolved for this match"
                    ),
                    "game_id": str(game_id),
                },
            )

        print(
            "[CRICKET] odds request:",
            "game_id=", game_id,
            "event_id=", event_id,
            "market_id=", market_id,
        )

        odds = proexch_api.get_odds(
            game_id=game_id,
            event_id=event_id,
            market_id=market_id,
            force_refresh=refresh,
        )

        counts = odds.get(
            "counts",
            {}
        )

        print(
            "[CRICKET] odds received:",
            "match_markets=",
            counts.get("match_markets", 0),
            "match_runners=",
            counts.get("match_runners", 0),
            "bookmaker_markets=",
            counts.get("bookmaker_markets", 0),
            "fancy_markets=",
            counts.get("fancy_markets", 0),
            "fancy_rows=",
            counts.get("fancy_rows", 0),
        )

        return {
            "success": True,

            "game_id": str(game_id),
            "event_id": (
                str(event_id)
                if event_id
                else str(game_id)
            ),
            "market_id": str(market_id),

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

            "other_market_odds": odds.get(
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
            f"[CRICKET] odds error: {exc}"
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load cricket odds"
                ),
            },
        )


# =========================================================
# SCOREBOARD / RESULTS
# =========================================================

@router.get("/score/{score_id}")
def cricket_score(
    request: Request,
    score_id: str,
):
    """Backend proxy for the cricket scoreboard."""
    if not _is_logged_in(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "Login required"},
        )

    try:
        data = proexch_api.get_score(score_id)
        return {
            "success": True,
            "score_id": str(score_id),
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
        print(f"[CRICKET] score error: {exc}")
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": "Unable to load scoreboard",
            },
        )


@router.get("/results/{result_id}")
def cricket_results(
    request: Request,
    result_id: str,
):
    """Backend proxy for match/result data."""
    if not _is_logged_in(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "Login required"},
        )

    try:
        data = proexch_api.get_result(result_id)
        return {
            "success": True,
            "result_id": str(result_id),
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
        print(f"[CRICKET] result error: {exc}")
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": "Unable to load match result",
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

        match = proexch_api.find_match(
            game_id
        )

        if not match:

            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "detail": "Match not found",
                },
            )

        market_id = match.get(
            "market_id"
        )

        event_id = match.get(
            "event_id"
        )

        odds = {
            "match_odds": [],
            "bookmaker_odds": [],
            "fancy_odds": [],
            "other_market_odds": [],
            "counts": {},
        }

        # -------------------------------------------------
        # Only call odds if a market ID exists.
        # -------------------------------------------------

        if market_id:

            odds = proexch_api.get_odds(
                game_id=game_id,
                event_id=event_id,
                market_id=market_id,
            )

        return {
            "success": True,
            "match": match,
            "odds": odds,
        }

    except Exception as exc:

        print(
            f"[CRICKET] single match error: {exc}"
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "detail": (
                    "Unable to load match"
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
        "message": "Cricket cache cleared",
    }