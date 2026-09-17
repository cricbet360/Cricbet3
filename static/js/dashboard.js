"use strict";


/* =========================================================
   CONFIGURATION
========================================================= */

const WHATSAPP_NUMBER = "918895898319";

const MATCH_REFRESH_MS = 30000;
const ODDS_REFRESH_MS = 5000;
const BET_REFRESH_MS = 10000;
const BALANCE_REFRESH_MS = 15000;

const ODDS_BATCH_SIZE = 5;

let allMatches = [];
let currentFilter = "all";

const oddsCache = new Map();
const oddsLoading = new Set();

let userBets = [];


/* =========================================================
   HTML HELPERS
========================================================= */

function escapeHtml(value) {

    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function toNumber(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return null;
    }

    const number = Number(value);

    return Number.isFinite(number)
        ? number
        : null;
}


function money(value) {

    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "₹0.00";
    }

    return `₹${number.toLocaleString(
        "en-IN",
        {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }
    )}`;
}


/* =========================================================
   MATCH FIELD HELPERS
========================================================= */

function getGameId(match) {

    return String(
        match?.game_id ??
        match?.gameId ??
        match?.id ??
        ""
    ).trim();
}


function getEventId(match) {

    return String(
        match?.event_id ??
        match?.eventId ??
        getGameId(match)
    ).trim();
}


function getMarketId(match) {

    return String(
        match?.market_id ??
        match?.marketId ??
        ""
    ).trim();
}


function getEventName(match) {

    return (
        match?.event_name ??
        match?.eventName ??
        match?.name ??
        "Cricket Match"
    );
}


function getTeam1(match) {

    return (
        match?.team1 ??
        match?.runnerName1 ??
        match?.runner_name1 ??
        "Team 1"
    );
}


function getTeam2(match) {

    return (
        match?.team2 ??
        match?.runnerName2 ??
        match?.runner_name2 ??
        "Team 2"
    );
}


function getTeam3(match) {

    return (
        match?.team3 ??
        match?.runnerName3 ??
        match?.runner_name3 ??
        ""
    );
}


function getEventTime(match) {

    return (
        match?.event_time ??
        match?.eventTime ??
        match?.start_time ??
        match?.startTime ??
        ""
    );
}


function getSelectionId(match, index) {

    const value =
        match?.[`selection_id${index}`] ??
        match?.[`selectionId${index}`] ??
        match?.[`sid${index}`] ??
        "";

    return String(value).trim();
}


/* =========================================================
   DATE / TIME
========================================================= */

function getTimestamp(value) {

    if (!value) {
        return NaN;
    }

    const timestamp =
        new Date(value).getTime();

    return Number.isFinite(timestamp)
        ? timestamp
        : NaN;
}


function formatDate(value) {

    if (!value) {
        return "";
    }

    const date =
        new Date(value);

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return String(value);
    }

    return date.toLocaleString(
        "en-IN",
        {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        }
    );
}


/* =========================================================
   MATCH STATUS
========================================================= */

function getBooleanValue(value) {

    if (
        value === true ||
        value === 1
    ) {
        return true;
    }

    if (
        typeof value === "string"
    ) {

        return [
            "true",
            "1",
            "yes",
            "live",
            "inplay",
            "in-play"
        ].includes(
            value.trim().toLowerCase()
        );
    }

    return false;
}


function getProviderStatus(match) {

    const values = [

        match?.status,
        match?.match_status,
        match?.matchStatus,
        match?.event_status,
        match?.eventStatus,
        match?.mstatus,
        match?.market_status,
        match?.marketStatus

    ];

    for (
        const value of values
    ) {

        if (
            value === null ||
            value === undefined ||
            value === ""
        ) {
            continue;
        }

        const status =
            String(value)
                .trim()
                .toLowerCase();

        if (
            [
                "finished",
                "finish",
                "completed",
                "complete",
                "closed",
                "ended",
                "result",
                "settled"
            ].includes(status)
        ) {

            return "finished";
        }

        if (
            [
                "live",
                "inplay",
                "in-play",
                "in_play",
                "started"
            ].includes(status)
        ) {

            return "live";
        }
    }

    return null;
}


function getMatchStatus(match) {

    /*
     * Provider live flag takes highest priority.
     */

    const liveValue =
        match?.in_play ??
        match?.inPlay;

    if (
        getBooleanValue(liveValue)
    ) {

        return {
            type: "live",
            label: "LIVE"
        };
    }


    /*
     * Explicit provider status.
     */

    const providerStatus =
        getProviderStatus(match);

    if (
        providerStatus === "live"
    ) {

        return {
            type: "live",
            label: "LIVE"
        };
    }


    if (
        providerStatus === "finished"
    ) {

        return {
            type: "finished",
            label: "FINISHED"
        };
    }


    /*
     * Determine remaining status from event time.
     */

    const timestamp =
        getTimestamp(
            getEventTime(match)
        );


    /*
     * No usable event time.
     *
     * Do not manufacture a live status.
     */
    if (
        !Number.isFinite(timestamp)
    ) {

        return {
            type: "unknown",
            label: "STATUS"
        };
    }


    const now =
        Date.now();


    /*
     * Future event.
     */
    if (
        timestamp > now
    ) {

        return {
            type: "upcoming",
            label: "UPCOMING"
        };
    }


    /*
     * If the provider has not marked the match
     * live and the scheduled time has passed,
     * don't incorrectly show UPCOMING.
     */
    return {
        type: "started",
        label: "STARTED"
    };
}


function isLive(match) {

    return (
        getMatchStatus(match).type === "live"
    );
}


/* =========================================================
   MATCH SORTING
========================================================= */

function sortMatchesByTime(matches) {

    return [...matches].sort(
        (a, b) => {

            const aTime =
                getTimestamp(
                    getEventTime(a)
                );

            const bTime =
                getTimestamp(
                    getEventTime(b)
                );


            if (
                !Number.isFinite(aTime) &&
                !Number.isFinite(bTime)
            ) {
                return 0;
            }


            if (
                !Number.isFinite(aTime)
            ) {
                return 1;
            }


            if (
                !Number.isFinite(bTime)
            ) {
                return -1;
            }


            return aTime - bTime;
        }
    );
}


/* =========================================================
   WHATSAPP
========================================================= */

function openWhatsApp(message) {

    if (!WHATSAPP_NUMBER) {
        return;
    }

    const url =
        `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;

    window.open(
        url,
        "_blank",
        "noopener,noreferrer"
    );
}


function openDepositWhatsApp() {

    openWhatsApp(
        "Hello, I want to make a deposit in CricBet."
    );
}


function openWithdrawWhatsApp() {

    openWhatsApp(
        "Hello, I want to make a withdrawal from CricBet."
    );
}


/* =========================================================
   ODDS RESPONSE
========================================================= */

function getOddsRoot(payload) {

    if (!payload) {
        return null;
    }


    if (
        payload.odds &&
        typeof payload.odds === "object"
    ) {

        return payload.odds;
    }


    if (
        payload.data &&
        typeof payload.data === "object"
    ) {

        if (
            payload.data.data &&
            typeof payload.data.data === "object"
        ) {

            return payload.data.data;
        }

        return payload.data;
    }


    return payload;
}


function getMatchOddsMarkets(payload) {

    const root =
        getOddsRoot(payload);

    if (
        !root ||
        typeof root !== "object"
    ) {
        return [];
    }


    if (
        Array.isArray(root.match_odds)
    ) {
        return root.match_odds;
    }


    if (
        Array.isArray(root.matchOdds)
    ) {
        return root.matchOdds;
    }


    if (
        Array.isArray(root.MATCH_ODDS)
    ) {
        return root.MATCH_ODDS;
    }


    return [];
}


/* =========================================================
   RUNNER DETECTION
========================================================= */

function isProExchRunner(item) {

    if (
        !item ||
        typeof item !== "object"
    ) {
        return false;
    }


    return (

        item.sid !== undefined ||

        item.rname !== undefined ||

        item.b1 !== undefined ||

        item.l1 !== undefined ||

        item.selectionId !== undefined ||

        item.selection_id !== undefined ||

        item.runnerId !== undefined ||

        item.runnerName !== undefined ||

        item.runner_name !== undefined ||

        item.back !== undefined ||

        item.lay !== undefined

    );
}


function findRunners(value) {

    if (!value) {
        return [];
    }


    if (
        Array.isArray(value)
    ) {

        if (
            value.length &&
            value.some(isProExchRunner)
        ) {

            return value.filter(
                item =>
                    item &&
                    typeof item === "object"
            );
        }


        for (
            const item of value
        ) {

            const result =
                findRunners(item);

            if (
                result.length
            ) {

                return result;
            }
        }


        return [];
    }


    if (
        typeof value !== "object"
    ) {
        return [];
    }


    if (
        Array.isArray(value.oddDatas)
    ) {

        const runners =
            value.oddDatas.filter(
                isProExchRunner
            );

        if (
            runners.length
        ) {

            return runners;
        }
    }


    const keys = [

        "runners",
        "runner",
        "selections",
        "selection",
        "oddDatas",
        "odds",
        "data",
        "matchOdds",
        "match_odds"

    ];


    for (
        const key of keys
    ) {

        if (
            value[key] === undefined ||
            value[key] === null
        ) {
            continue;
        }


        const result =
            findRunners(
                value[key]
            );


        if (
            result.length
        ) {

            return result;
        }
    }


    return [];
}


/* =========================================================
   RUNNER HELPERS
========================================================= */

function getRunnerSelectionId(item) {

    return (
        item?.selectionId ??
        item?.selection_id ??
        item?.selectionID ??
        item?.sid ??
        item?.runnerId ??
        item?.runner_id ??
        null
    );
}


function getRunnerName(item) {

    return (
        item?.runnerName ??
        item?.runner_name ??
        item?.selectionName ??
        item?.selection_name ??
        item?.rname ??
        item?.name ??
        item?.teamName ??
        item?.team ??
        ""
    );
}


function extractPrice(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return null;
    }


    if (
        typeof value === "number"
    ) {

        return Number.isFinite(value)
            ? value
            : null;
    }


    if (
        typeof value === "string"
    ) {

        return toNumber(value);
    }


    if (
        typeof value === "object"
    ) {

        return (
            toNumber(value.price) ??
            toNumber(value.odds) ??
            toNumber(value.rate) ??
            toNumber(value.value)
        );
    }


    return null;
}


function getBackPrice(item) {

    const values = [

        item?.back,
        item?.Back,
        item?.backPrice,
        item?.back_price,
        item?.backOdds,
        item?.back_odds,
        item?.backRate,
        item?.back_rate,

        item?.b1,
        item?.b2,
        item?.b3

    ];


    for (
        const value of values
    ) {

        const price =
            extractPrice(value);

        if (
            price !== null
        ) {

            return price;
        }
    }


    return null;
}


function getLayPrice(item) {

    const values = [

        item?.lay,
        item?.Lay,
        item?.layPrice,
        item?.lay_price,
        item?.layOdds,
        item?.lay_odds,
        item?.layRate,
        item?.lay_rate,

        item?.l1,
        item?.l2,
        item?.l3

    ];


    for (
        const value of values
    ) {

        const price =
            extractPrice(value);

        if (
            price !== null
        ) {

            return price;
        }
    }


    return null;
}


function getBackSize(item) {

    return (
        item?.back_size ??
        item?.backSize ??
        item?.bs1 ??
        item?.bs2 ??
        item?.bs3 ??
        null
    );
}


function getLaySize(item) {

    return (
        item?.lay_size ??
        item?.laySize ??
        item?.ls1 ??
        item?.ls2 ??
        item?.ls3 ??
        null
    );
}


function normalizeRunners(runners) {

    if (
        !Array.isArray(runners)
    ) {
        return [];
    }


    return runners
        .map(item => {

            if (
                !item ||
                typeof item !== "object"
            ) {
                return null;
            }


            return {

                selectionId:
                    getRunnerSelectionId(item),

                name:
                    getRunnerName(item),

                back:
                    getBackPrice(item),

                lay:
                    getLayPrice(item),

                backSize:
                    getBackSize(item),

                laySize:
                    getLaySize(item)

            };
        })
        .filter(Boolean);
}


/* =========================================================
   EMPTY ODDS
========================================================= */

function emptyOdds() {

    return {

        team1: {
            selectionId: "",
            name: "",
            back: null,
            lay: null,
            backSize: null,
            laySize: null
        },

        team2: {
            selectionId: "",
            name: "",
            back: null,
            lay: null,
            backSize: null,
            laySize: null
        },

        team3: {
            selectionId: "",
            name: "",
            back: null,
            lay: null,
            backSize: null,
            laySize: null
        }

    };
}


/* =========================================================
   NORMALIZE MATCH ODDS
========================================================= */

function normalizeMatchOdds(
    match,
    payload
) {

    const markets =
        getMatchOddsMarkets(payload);


    if (
        !markets.length
    ) {
        return emptyOdds();
    }


    let runners = [];


    for (
        const market of markets
    ) {

        const found =
            findRunners(market);


        if (
            found.length
        ) {

            runners = found;

            break;
        }
    }


    if (
        !runners.length
    ) {

        return emptyOdds();
    }


    const normalized =
        normalizeRunners(runners);


    const result =
        emptyOdds();


    const slots = [
        "team1",
        "team2",
        "team3"
    ];


    /*
     * First try matching by known selection IDs.
     */

    const knownSelectionIds = [

        getSelectionId(match, 1),
        getSelectionId(match, 2),
        getSelectionId(match, 3)

    ];


    normalized.forEach(
        runner => {

            const runnerId =
                runner.selectionId === null ||
                runner.selectionId === undefined
                    ? ""
                    : String(
                        runner.selectionId
                    );


            const index =
                knownSelectionIds.indexOf(
                    runnerId
                );


            if (
                index >= 0
            ) {

                result[
                    slots[index]
                ] = {

                    selectionId:
                        runner.selectionId,

                    name:
                        runner.name,

                    back:
                        runner.back,

                    lay:
                        runner.lay,

                    backSize:
                        runner.backSize,

                    laySize:
                        runner.laySize

                };
            }
        }
    );


    /*
     * Fill any unmatched slots using provider
     * runner order.
     */

    normalized
        .slice(0, 3)
        .forEach(
            (runner, index) => {

                const slot =
                    slots[index];


                if (
                    result[slot].back === null &&
                    result[slot].lay === null
                ) {

                    result[slot] = {

                        selectionId:
                            runner.selectionId,

                        name:
                            runner.name,

                        back:
                            runner.back,

                        lay:
                            runner.lay,

                        backSize:
                            runner.backSize,

                        laySize:
                            runner.laySize

                    };
                }
            }
        );


    return result;
}


/* =========================================================
   ODDS BUTTON
========================================================= */

function createOddsButton({
    gameId,
    eventId,
    marketId,
    selectionId,
    team,
    side,
    price,
    className
}) {

    const numericPrice =
        toNumber(price);


    /*
     * ProExch can return 0 when a side is unavailable.
     * Odds below/equal to 1 are not valid bet odds.
     */

    const disabled =
        numericPrice === null ||
        numericPrice <= 1;


    return `
        <button
            type="button"
            class="odds-cell ${escapeHtml(className)}"
            data-game-id="${escapeHtml(gameId)}"
            data-event-id="${escapeHtml(eventId)}"
            data-market-id="${escapeHtml(marketId)}"
            data-selection-id="${escapeHtml(selectionId || "")}"
            data-team="${escapeHtml(team)}"
            data-side="${escapeHtml(side)}"
            data-price="${
                numericPrice !== null
                    ? numericPrice
                    : ""
            }"
            ${disabled ? "disabled" : ""}
        >
            <span class="odds-price">
                ${
                    !disabled
                        ? numericPrice.toFixed(2)
                        : "-"
                }
            </span>
        </button>
    `;
}


/* =========================================================
   MATCH ROW
========================================================= */

function createMatchRow(match) {

    const gameId =
        getGameId(match);

    const eventId =
        getEventId(match);

    const marketId =
        getMarketId(match);

    const eventName =
        getEventName(match);

    const eventTime =
        getEventTime(match);

    const team1 =
        getTeam1(match);

    const team2 =
        getTeam2(match);

    const team3 =
        getTeam3(match);


    const status =
        getMatchStatus(match);


    const odds =
        oddsCache.has(gameId)
            ? normalizeMatchOdds(
                match,
                oddsCache.get(gameId)
            )
            : emptyOdds();


    let statusClass =
        "upcoming-status";


    if (
        status.type === "live"
    ) {

        statusClass =
            "live-status";

    } else if (
        status.type === "started"
    ) {

        statusClass =
            "started-status";

    } else if (
        status.type === "finished"
    ) {

        statusClass =
            "finished-status";
    }


    /*
     * The dashboard has three odds columns.
     *
     * We preserve the existing layout:
     *
     * Column 1 = Match
     * Column 2 = Back
     * Column 3 = Lay
     * Column 4 = Draw
     *
     * The BACK/ LAY cells show the first available
     * team selection. The detailed Match page contains
     * the complete market.
     *
     * To avoid misleading the user, we use the first
     * team's BACK, second team's LAY, and draw/team3
     * BACK in the existing compact table.
     */


    const team1Back =
        odds.team1.back;

    const team2Lay =
        odds.team2.lay;

    const drawBack =
        team3
            ? odds.team3.back
            : null;


    return `
        <div
            class="sportsbook-match-row"
            data-game-id="${escapeHtml(gameId)}"
            data-event-id="${escapeHtml(eventId)}"
            data-market-id="${escapeHtml(marketId)}"
        >


            <div class="match-information">


                <div class="match-status-line">

                    ${
                        status.type === "live"
                            ? `
                                <span class="live-dot"></span>
                            `
                            : ""
                    }


                    <span
                        class="match-status ${statusClass}"
                    >
                        ${escapeHtml(status.label)}
                    </span>


                    <span class="match-time">
                        ${escapeHtml(
                            formatDate(eventTime)
                        )}
                    </span>

                </div>


                <div class="match-name">
                    ${escapeHtml(eventName)}
                </div>


                <div class="team-names">

                    <div class="team-name">
                        ${escapeHtml(team1)}
                    </div>


                    <div class="team-name">
                        ${escapeHtml(team2)}
                    </div>


                    ${
                        team3
                            ? `
                                <div class="team-name">
                                    ${escapeHtml(team3)}
                                </div>
                            `
                            : ""
                    }

                </div>


                <div class="match-league">
                    Cricket
                </div>

            </div>


            <!-- BACK -->

            ${createOddsButton({

                gameId,
                eventId,
                marketId,

                selectionId:
                    odds.team1.selectionId ||
                    getSelectionId(match, 1),

                team:
                    odds.team1.name ||
                    team1,

                side:
                    "back",

                price:
                    team1Back,

                className:
                    "odds-team-1"

            })}


            <!-- LAY -->

            ${createOddsButton({

                gameId,
                eventId,
                marketId,

                selectionId:
                    odds.team2.selectionId ||
                    getSelectionId(match, 2),

                team:
                    odds.team2.name ||
                    team2,

                side:
                    "lay",

                price:
                    team2Lay,

                className:
                    "odds-team-2"

            })}


            <!-- DRAW / THIRD RUNNER -->

            ${
                team3
                    ? createOddsButton({

                        gameId,
                        eventId,
                        marketId,

                        selectionId:
                            odds.team3.selectionId ||
                            getSelectionId(
                                match,
                                3
                            ),

                        team:
                            odds.team3.name ||
                            team3,

                        side:
                            "back",

                        price:
                            drawBack,

                        className:
                            "odds-draw"

                    })
                    : `
                        <div
                            class="odds-cell odds-empty"
                            aria-disabled="true"
                        >
                            <span class="odds-price">
                                -
                            </span>
                        </div>
                    `
            }


            <div class="match-action">

                <a
                    class="view-match-button"
                    href="/match/${encodeURIComponent(gameId)}"
                >
                    <span>→</span>
                    VIEW MATCH
                </a>

            </div>


        </div>
    `;
}


/* =========================================================
   LOAD MATCHES
========================================================= */

async function loadMatches() {

    const container =
        document.getElementById(
            "matches"
        );


    if (!container) {
        return;
    }


    try {

        const response =
            await fetch(
                "/api/cricket/matches",
                {
                    method: "GET",

                    credentials:
                        "same-origin",

                    cache:
                        "no-store",

                    headers: {
                        Accept:
                            "application/json"
                    }
                }
            );


        const payload =
            await response.json();


        if (
            !response.ok
        ) {

            throw new Error(
                payload?.detail ||
                payload?.error ||
                `HTTP ${response.status}`
            );
        }


        if (
            payload.success !== true
        ) {

            throw new Error(
                payload?.detail ||
                payload?.error ||
                "Cricket API request failed."
            );
        }


        let matches =
            Array.isArray(payload.data)
                ? payload.data
                : Array.isArray(payload.matches)
                    ? payload.matches
                    : [];


        /*
         * Remove duplicate game IDs.
         */

        const uniqueMatches =
            new Map();


        matches.forEach(
            match => {

                const gameId =
                    getGameId(match);


                if (
                    gameId
                ) {

                    uniqueMatches.set(
                        gameId,
                        match
                    );
                }
            }
        );


        matches =
            Array.from(
                uniqueMatches.values()
            );


        /*
         * Always sort the COMPLETE API response
         * before applying the current filter.
         */

        allMatches =
            sortMatchesByTime(
                matches
            );


        console.log(
            "[CricBet] Matches loaded:",
            allMatches.length
        );


        console.log(
            "[CricBet] Sorted matches:",
            allMatches
        );


        renderMatches();


        await loadAllOdds();


    } catch (error) {

        console.error(
            "[CricBet] MATCH ERROR:",
            error
        );


        if (
            !allMatches.length
        ) {

            container.innerHTML = `

                <div class="empty-state">

                    <div class="empty-state-icon">
                        ⚠️
                    </div>

                    <div class="empty-state-title">
                        Unable to load cricket data
                    </div>

                    <div class="empty-state-text">
                        ${escapeHtml(
                            error.message
                        )}
                    </div>

                    <button
                        type="button"
                        class="retry-matches-button"
                        id="retryMatchesButton"
                    >
                        RETRY
                    </button>

                </div>

            `;


            const retryButton =
                document.getElementById(
                    "retryMatchesButton"
                );


            if (
                retryButton
            ) {

                retryButton.addEventListener(
                    "click",
                    loadMatches
                );
            }
        }
    }
}


/* =========================================================
   LOAD ODDS FOR ONE MATCH
========================================================= */

async function loadOddsForMatch(match) {

    const gameId =
        getGameId(match);

    const eventId =
        getEventId(match);

    const marketId =
        getMarketId(match);


    if (
        !gameId
    ) {
        return;
    }


    if (
        oddsLoading.has(gameId)
    ) {
        return;
    }


    oddsLoading.add(gameId);


    try {

        const params =
            new URLSearchParams();


        params.set(
            "gameId",
            gameId
        );


        if (
            eventId
        ) {

            params.set(
                "eventId",
                eventId
            );
        }


        if (
            marketId
        ) {

            params.set(
                "marketId",
                marketId
            );
        }


        const response =
            await fetch(
                `/api/cricket/odds?${params.toString()}`,
                {
                    method: "GET",

                    credentials:
                        "same-origin",

                    cache:
                        "no-store",

                    headers: {
                        Accept:
                            "application/json"
                    }
                }
            );


        const payload =
            await response.json();


        if (
            !response.ok
        ) {

            throw new Error(
                payload?.detail ||
                payload?.error ||
                `Odds HTTP ${response.status}`
            );
        }


        if (
            payload.success !== true
        ) {

            throw new Error(
                payload?.detail ||
                payload?.error ||
                "Odds request failed."
            );
        }


        oddsCache.set(
            gameId,
            payload
        );


        updateMatchOdds(match);


    } catch (error) {

        console.warn(
            "[CricBet] ODDS ERROR:",
            gameId,
            error.message
        );


    } finally {

        oddsLoading.delete(
            gameId
        );
    }
}


/* =========================================================
   LOAD ALL ODDS
========================================================= */

async function loadAllOdds() {

    if (
        !allMatches.length
    ) {
        return;
    }


    for (
        let i = 0;
        i < allMatches.length;
        i += ODDS_BATCH_SIZE
    ) {

        const batch =
            allMatches.slice(
                i,
                i + ODDS_BATCH_SIZE
            );


        await Promise.all(
            batch.map(
                loadOddsForMatch
            )
        );
    }
}


/* =========================================================
   UPDATE MATCH ODDS
========================================================= */

function updateMatchOdds(match) {

    const gameId =
        getGameId(match);


    if (
        !gameId ||
        !oddsCache.has(gameId)
    ) {
        return;
    }


    const escapedGameId =
        typeof CSS !== "undefined" &&
        CSS.escape
            ? CSS.escape(gameId)
            : gameId.replaceAll(
                '"',
                '\\"'
            );


    const row =
        document.querySelector(
            `.sportsbook-match-row[data-game-id="${escapedGameId}"]`
        );


    if (
        !row
    ) {
        return;
    }


    const odds =
        normalizeMatchOdds(
            match,
            oddsCache.get(gameId)
        );


    const backButton =
        row.querySelector(
            ".odds-team-1"
        );


    const layButton =
        row.querySelector(
            ".odds-team-2"
        );


    const drawButton =
        row.querySelector(
            ".odds-draw"
        );


    updateOddsButton(
        backButton,
        odds.team1.back
    );


    updateOddsButton(
        layButton,
        odds.team2.lay
    );


    updateOddsButton(
        drawButton,
        odds.team3.back
    );


    /*
     * Keep actual ProExch selection IDs on the
     * clickable dashboard buttons.
     */

    if (
        backButton &&
        odds.team1.selectionId !== null &&
        odds.team1.selectionId !== undefined
    ) {

        backButton.dataset.selectionId =
            String(
                odds.team1.selectionId
            );
    }


    if (
        layButton &&
        odds.team2.selectionId !== null &&
        odds.team2.selectionId !== undefined
    ) {

        layButton.dataset.selectionId =
            String(
                odds.team2.selectionId
            );
    }


    if (
        drawButton &&
        odds.team3.selectionId !== null &&
        odds.team3.selectionId !== undefined
    ) {

        drawButton.dataset.selectionId =
            String(
                odds.team3.selectionId
            );
    }
}


/* =========================================================
   UPDATE ODDS BUTTON
========================================================= */

function updateOddsButton(
    button,
    price
) {

    if (
        !button
    ) {
        return;
    }


    const numericPrice =
        toNumber(price);


    const span =
        button.querySelector(
            ".odds-price"
        );


    /*
     * Odds <= 1 are treated as unavailable.
     */

    if (
        numericPrice === null ||
        numericPrice <= 1
    ) {

        button.disabled = true;

        button.dataset.price = "";


        if (
            span
        ) {

            span.textContent =
                "-";
        }


        return;
    }


    button.disabled = false;


    button.dataset.price =
        String(
            numericPrice
        );


    if (
        span
    ) {

        span.textContent =
            numericPrice.toFixed(2);
    }
}


/* =========================================================
   FILTER
========================================================= */

function setFilter(filter) {

    const validFilters = [
        "all",
        "live",
        "upcoming"
    ];


    if (
        !validFilters.includes(filter)
    ) {

        filter = "all";
    }


    currentFilter =
        filter;


    document
        .querySelectorAll(
            ".sport-filter"
        )
        .forEach(
            button => {

                button.classList.toggle(
                    "active",
                    button.dataset.filter === filter
                );
            }
        );


    renderMatches();
}


/* =========================================================
   RENDER MATCHES
========================================================= */

function renderMatches() {

    const container =
        document.getElementById(
            "matches"
        );


    if (
        !container
    ) {
        return;
    }


    let matches =
        [...allMatches];


    /*
     * LIVE FILTER
     */

    if (
        currentFilter === "live"
    ) {

        matches =
            matches.filter(
                match =>
                    getMatchStatus(match).type ===
                    "live"
            );
    }


    /*
     * UPCOMING FILTER
     *
     * Only genuinely future matches.
     */

    if (
        currentFilter === "upcoming"
    ) {

        matches =
            matches.filter(
                match =>
                    getMatchStatus(match).type ===
                    "upcoming"
            );
    }


    /*
     * Always preserve chronological order.
     */

    matches =
        sortMatchesByTime(
            matches
        );


    if (
        !matches.length
    ) {

        let message =
            "No matches are currently available for this filter.";


        if (
            currentFilter === "live"
        ) {

            message =
                "There are no live cricket matches right now.";
        }


        if (
            currentFilter === "upcoming"
        ) {

            message =
                "There are no upcoming cricket matches currently available.";
        }


        container.innerHTML = `

            <div class="empty-state">

                <div class="empty-state-icon">
                    🏏
                </div>

                <div class="empty-state-title">
                    No cricket matches
                </div>

                <div class="empty-state-text">
                    ${escapeHtml(message)}
                </div>

            </div>

        `;


        return;
    }


    container.innerHTML =
        matches
            .map(
                createMatchRow
            )
            .join("");


    /*
     * Apply already-loaded odds immediately.
     */

    matches.forEach(
        updateMatchOdds
    );
}


/* =========================================================
   BALANCE
========================================================= */

async function loadBalance() {

    try {

        const response =
            await fetch(
                "/api/user/balance",
                {
                    method: "GET",

                    credentials:
                        "same-origin",

                    cache:
                        "no-store",

                    headers: {
                        Accept:
                            "application/json"
                    }
                }
            );


        if (
            !response.ok
        ) {
            return;
        }


        const data =
            await response.json();


        if (
            data.balance === undefined
        ) {
            return;
        }


        const number =
            Number(
                data.balance
            );


        if (
            !Number.isFinite(number)
        ) {
            return;
        }


        const formatted =
            number.toLocaleString(
                "en-IN",
                {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                }
            );


        const balanceElement =
            document.getElementById(
                "balance"
            );


        const betslipBalance =
            document.getElementById(
                "betslipBalance"
            );


        if (
            balanceElement
        ) {

            balanceElement.textContent =
                `₹${formatted}`;
        }


        if (
            betslipBalance
        ) {

            betslipBalance.textContent =
                `₹${formatted}`;
        }


    } catch (error) {

        console.warn(
            "[CricBet] Balance loading failed:",
            error
        );
    }
}


/* =========================================================
   MY BETS
========================================================= */

async function loadMyBets() {

    try {

        const response =
            await fetch(
                "/bets/my-bets",
                {
                    method: "GET",

                    credentials:
                        "same-origin",

                    cache:
                        "no-store",

                    headers: {
                        Accept:
                            "application/json"
                    }
                }
            );


        const payload =
            await response.json();


        if (
            !response.ok
        ) {

            throw new Error(
                payload?.message ||
                payload?.detail ||
                `HTTP ${response.status}`
            );
        }


        if (
            payload.success !== true
        ) {

            throw new Error(
                payload?.message ||
                "Unable to load bets."
            );
        }


        userBets =
            Array.isArray(
                payload.bets
            )
                ? payload.bets
                : [];


        renderBetslip();


    } catch (error) {

        console.warn(
            "[CricBet] MY BETS ERROR:",
            error
        );


        renderBetslipError(
            error.message
        );
    }
}


/* =========================================================
   BETSLIP
========================================================= */

function renderBetslip() {

    const content =
        document.getElementById(
            "betslipContent"
        );


    const count =
        document.getElementById(
            "betslipCount"
        );


    if (
        !content
    ) {
        return;
    }


    if (
        count
    ) {

        count.textContent =
            String(
                userBets.length
            );
    }


    if (
        !userBets.length
    ) {

        content.innerHTML = `

            <div class="betslip-empty">

                <div class="betslip-empty-icon">
                    🎟️
                </div>

                <h3>
                    Your bet slip is empty
                </h3>

                <p>
                    Select odds from a match to add a bet.
                </p>

            </div>

        `;


        return;
    }


    /*
     * Newest bets first.
     */

    const sortedBets =
        [...userBets].sort(
            (a, b) => {

                const aTime =
                    getTimestamp(
                        a.created_at
                    );


                const bTime =
                    getTimestamp(
                        b.created_at
                    );


                if (
                    !Number.isFinite(aTime) &&
                    !Number.isFinite(bTime)
                ) {
                    return 0;
                }


                if (
                    !Number.isFinite(aTime)
                ) {
                    return 1;
                }


                if (
                    !Number.isFinite(bTime)
                ) {
                    return -1;
                }


                return bTime - aTime;
            }
        );


    content.innerHTML =
        sortedBets
            .slice(0, 10)
            .map(
                renderPlacedBet
            )
            .join("");
}


/* =========================================================
   RENDER INDIVIDUAL BET
========================================================= */

function renderPlacedBet(bet) {

    const selection =
        Array.isArray(
            bet.selections
        ) &&
        bet.selections.length
            ? bet.selections[0]
            : null;


    const side =
        String(
            selection?.side || "-"
        ).toUpperCase();


    const status =
        String(
            bet.status || "pending"
        );


    const statusClass =
        status
            .toLowerCase()
            .replaceAll(
                " ",
                "-"
            );


    const statusText =
        status.charAt(0).toUpperCase() +
        status.slice(1);


    const odds =
        Number(
            bet.total_odds
        );


    const stake =
        Number(
            bet.stake
        );


    const potentialWin =
        Number(
            bet.potential_win
        );


    const marketName =
        selection?.market_name ||
        "Match Odds";


    const selectionName =
        selection?.runner_name ||
        "Selection";


    const eventName =
        selection?.event_name ||
        "Cricket Match";


    return `

        <article
            class="betslip-bet-card"
        >


            <div class="betslip-bet-header">


                <div class="betslip-bet-title">

                    <span class="betslip-sport-icon">
                        🏏
                    </span>


                    <div>

                        <strong>
                            ${escapeHtml(
                                selectionName
                            )}
                        </strong>


                        <small>
                            ${escapeHtml(
                                marketName
                            )}
                        </small>

                    </div>

                </div>


                <span
                    class="betslip-status ${escapeHtml(
                        statusClass
                    )}"
                >
                    ${escapeHtml(
                        statusText
                    )}
                </span>

            </div>


            <div class="betslip-match-name">

                ${escapeHtml(
                    eventName
                )}

            </div>


            <div class="betslip-details-grid">


                <div class="betslip-detail">

                    <span>
                        SIDE
                    </span>


                    <strong
                        class="${
                            side === "BACK"
                                ? "bet-back"
                                : side === "LAY"
                                    ? "bet-lay"
                                    : ""
                        }"
                    >
                        ${escapeHtml(side)}
                    </strong>

                </div>


                <div class="betslip-detail">

                    <span>
                        ODDS
                    </span>


                    <strong>
                        ${
                            Number.isFinite(odds)
                                ? odds.toFixed(2)
                                : "-"
                        }
                    </strong>

                </div>


                <div class="betslip-detail">

                    <span>
                        STAKE
                    </span>


                    <strong>
                        ${money(stake)}
                    </strong>

                </div>


                <div class="betslip-detail">

                    <span>
                        POTENTIAL WIN
                    </span>


                    <strong>
                        ${money(potentialWin)}
                    </strong>

                </div>


            </div>


            <div class="betslip-bet-footer">

                <span>
                    Bet #${escapeHtml(
                        bet.id
                    )}
                </span>


                <span>
                    ${escapeHtml(
                        formatDate(
                            bet.created_at
                        )
                    )}
                </span>

            </div>


        </article>

    `;
}


/* =========================================================
   BETSLIP ERROR
========================================================= */

function renderBetslipError(message) {

    const content =
        document.getElementById(
            "betslipContent"
        );


    if (
        !content
    ) {
        return;
    }


    content.innerHTML = `

        <div class="betslip-empty">

            <div class="betslip-empty-icon">
                ⚠️
            </div>

            <h3>
                Unable to load bets
            </h3>

            <p>
                ${escapeHtml(
                    message ||
                    "Please refresh the page."
                )}
            </p>

        </div>

    `;
}


/* =========================================================
   OPEN BETSLIP
========================================================= */

function openBetslip() {

    const betslip =
        document.getElementById(
            "betslip"
        );


    if (
        !betslip
    ) {
        return;
    }


    /*
     * Remove HTML hidden state.
     */

    betslip.hidden = false;


    /*
     * Accessibility state.
     */

    betslip.setAttribute(
        "aria-hidden",
        "false"
    );


    /*
     * Remove minimized state.
     */

    betslip.classList.remove(
        "minimized"
    );


    /*
     * Add open state.
     */

    betslip.classList.add(
        "open"
    );


    /*
     * Explicit display prevents
     * old CSS from hiding the panel.
     */

    betslip.style.setProperty(
        "display",
        "flex",
        "important"
    );


    /*
     * Refresh bets whenever the user opens
     * the panel so the displayed list is current.
     */

    loadMyBets();
}


/* =========================================================
   MINIMIZE BETSLIP
========================================================= */

function minimizeBetslip() {

    const betslip =
        document.getElementById(
            "betslip"
        );


    if (
        !betslip
    ) {
        return;
    }


    betslip.classList.remove(
        "open"
    );


    betslip.classList.add(
        "minimized"
    );


    betslip.setAttribute(
        "aria-hidden",
        "true"
    );


    /*
     * Completely hide the panel.
     *
     * The floating BET SLIP button remains visible.
     */

    betslip.style.setProperty(
        "display",
        "none",
        "important"
    );


    betslip.hidden = true;
}


/* =========================================================
   SETUP BETSLIP
========================================================= */

function setupBetslip() {

    const betslip =
        document.getElementById(
            "betslip"
        );


    const closeButton =
        document.getElementById(
            "betslipClose"
        );


    const openButton =
        document.getElementById(
            "mobileBetslipButton"
        );


    /*
     * Start minimized.
     *
     * User opens it by tapping BET SLIP.
     */

    if (
        betslip
    ) {

        betslip.hidden = true;

        betslip.classList.remove(
            "open"
        );

        betslip.classList.add(
            "minimized"
        );

        betslip.setAttribute(
            "aria-hidden",
            "true"
        );

        betslip.style.setProperty(
            "display",
            "none",
            "important"
        );
    }


    /*
     * MINIMIZE button.
     */

    if (
        closeButton
    ) {

        closeButton.addEventListener(
            "click",
            event => {

                event.preventDefault();

                event.stopPropagation();

                minimizeBetslip();
            }
        );
    }


    /*
     * OPEN button.
     */

    if (
        openButton
    ) {

        openButton.addEventListener(
            "click",
            event => {

                event.preventDefault();

                event.stopPropagation();

                openBetslip();
            }
        );
    }
}


/* =========================================================
   ODDS CLICK
========================================================= */

document.addEventListener(
    "click",
    event => {

        const button =
            event.target.closest(
                ".odds-cell"
            );


        if (
            !button ||
            button.disabled
        ) {
            return;
        }


        const price =
            Number(
                button.dataset.price
            );


        if (
            !Number.isFinite(price) ||
            price <= 1
        ) {
            return;
        }


        const selection = {

            gameId:
                button.dataset.gameId,

            eventId:
                button.dataset.eventId,

            marketId:
                button.dataset.marketId,

            selectionId:
                button.dataset.selectionId,

            team:
                button.dataset.team,

            side:
                button.dataset.side,

            price

        };


        console.log(
            "[CricBet] Odds selected:",
            selection
        );


        /*
         * Keep compatibility with existing
         * dashboard bet selection handlers.
         */

        document.dispatchEvent(
            new CustomEvent(
                "cricbet:oddsSelected",
                {
                    detail:
                        selection
                }
            )
        );


        /*
         * Dashboard compact odds are not the full
         * bet placement interface.
         *
         * Open the detailed match page where the
         * complete market/betslip is available.
         */

        if (
            selection.gameId
        ) {

            window.location.href =
                `/match/${encodeURIComponent(
                    selection.gameId
                )}`;
        }

    }
);


/* =========================================================
   FILTER BUTTON SETUP
========================================================= */

function setupFilters() {

    document
        .querySelectorAll(
            ".sport-filter"
        )
        .forEach(
            button => {

                button.addEventListener(
                    "click",
                    () => {

                        setFilter(
                            button.dataset.filter
                        );
                    }
                );
            }
        );
}


/* =========================================================
   TOP BAR SETUP
========================================================= */

function setupTopbar() {

    const depositButton =
        document.getElementById(
            "depositBtn"
        );


    if (
        depositButton
    ) {

        depositButton.addEventListener(
            "click",
            openDepositWhatsApp
        );
    }


    const withdrawButton =
        document.getElementById(
            "withdrawBtn"
        );


    if (
        withdrawButton
    ) {

        withdrawButton.addEventListener(
            "click",
            openWithdrawWhatsApp
        );
    }
}


/* =========================================================
   INITIALIZE
========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    () => {

        console.log(
            "[CricBet] Dashboard initializing..."
        );


        setupFilters();


        setupTopbar();


        setupBetslip();


        loadBalance();


        loadMyBets();


        loadMatches();


        /*
         * Refresh matches every 30 seconds.
         */

        setInterval(
            loadMatches,
            MATCH_REFRESH_MS
        );


        /*
         * Refresh odds every 5 seconds.
         */

        setInterval(
            () => {

                if (
                    allMatches.length
                ) {

                    allMatches.forEach(
                        match => {
                            loadOddsForMatch(
                                match
                            );
                        }
                    );
                }

            },
            ODDS_REFRESH_MS
        );


        /*
         * Refresh balance.
         */

        setInterval(
            loadBalance,
            BALANCE_REFRESH_MS
        );


        /*
         * Refresh My Bets.
         */

        setInterval(
            loadMyBets,
            BET_REFRESH_MS
        );

    }
);