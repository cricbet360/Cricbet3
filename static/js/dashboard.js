"use strict";

/* =========================================================
   CONFIG
========================================================= */

const WHATSAPP_NUMBER = "918895898319";

const MATCH_REFRESH_MS = 30000;
const ODDS_REFRESH_MS = 5000;

let allMatches = [];
let currentFilter = "all";

const oddsCache = new Map();
const oddsLoading = new Set();


/* =========================================================
   HELPERS
========================================================= */

function escapeHtml(value) {
    if (value === null || value === undefined) {
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
    if (value === null || value === undefined || value === "") {
        return null;
    }

    const number = Number(value);

    return Number.isFinite(number)
        ? number
        : null;
}


function getGameId(match) {
    return String(
        match?.game_id ??
        match?.gameId ??
        ""
    ).trim();
}


function getEventId(match) {
    return String(
        match?.event_id ??
        match?.eventId ??
        ""
    ).trim();
}


function getMarketId(match) {
    return String(
        match?.market_id ??
        match?.marketId ??
        ""
    ).trim();
}


function getSelectionId(match, index) {
    return String(
        match?.[`selection_id${index}`] ??
        match?.[`selectionId${index}`] ??
        ""
    ).trim();
}


function isLive(match) {
    const value =
        match?.in_play ??
        match?.inPlay;

    return (
        value === true ||
        value === 1 ||
        value === "1" ||
        value === "true" ||
        value === "True"
    );
}


function formatDate(value) {
    if (!value) {
        return "";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleString("en-IN", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    });
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
   ODDS RESPONSE HELPERS
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
    const root = getOddsRoot(payload);

    if (!root || typeof root !== "object") {
        return [];
    }

    /* Raw ProExch */

    if (Array.isArray(root.matchOdds)) {
        return root.matchOdds;
    }

    /* Normalized backend */

    if (Array.isArray(root.match_odds)) {
        return root.match_odds;
    }

    if (Array.isArray(root.MATCH_ODDS)) {
        return root.MATCH_ODDS;
    }

    /* Case-insensitive fallback */

    for (const key of Object.keys(root)) {
        if (
            key.toLowerCase() === "matchodds" ||
            key.toLowerCase() === "match_odds"
        ) {
            if (Array.isArray(root[key])) {
                return root[key];
            }
        }
    }

    return [];
}


/* =========================================================
   RUNNER DETECTION
========================================================= */

function isProExchRunner(item) {
    if (!item || typeof item !== "object") {
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

    /* Direct array */

    if (Array.isArray(value)) {

        /*
         * IMPORTANT:
         * ProExch uses:
         *
         * sid
         * rname
         * b1
         * l1
         */

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

        for (const item of value) {
            const result =
                findRunners(item);

            if (result.length) {
                return result;
            }
        }

        return [];
    }

    if (typeof value !== "object") {
        return [];
    }


    /* Direct ProExch oddDatas */

    if (Array.isArray(value.oddDatas)) {

        const runners =
            value.oddDatas.filter(
                isProExchRunner
            );

        if (runners.length) {
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

    for (const key of keys) {

        if (
            value[key] === undefined ||
            value[key] === null
        ) {
            continue;
        }

        const result =
            findRunners(value[key]);

        if (result.length) {
            return result;
        }
    }

    return [];
}


/* =========================================================
   RUNNER FIELDS
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

    if (typeof value === "number") {
        return Number.isFinite(value)
            ? value
            : null;
    }

    if (typeof value === "string") {
        return toNumber(value);
    }

    if (typeof value === "object") {
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
        item?.backOdd,
        item?.back_odd,

        /* ProExch */
        item?.b1,

        item?.b2,
        item?.b3,

        item?.back1
    ];

    for (const value of values) {

        const price =
            extractPrice(value);

        if (price !== null) {
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
        item?.layOdd,
        item?.lay_odd,

        /* ProExch */
        item?.l1,

        item?.l2,
        item?.l3,

        item?.lay1
    ];

    for (const value of values) {

        const price =
            extractPrice(value);

        if (price !== null) {
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


/* =========================================================
   NORMALIZE RUNNERS
========================================================= */

function normalizeRunners(runners) {

    if (!Array.isArray(runners)) {
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
            back: null,
            lay: null,
            backSize: null,
            laySize: null
        },

        team2: {
            back: null,
            lay: null,
            backSize: null,
            laySize: null
        },

        team3: {
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

function normalizeMatchOdds(match, payload) {

    const markets =
        getMatchOddsMarkets(payload);

    if (!markets.length) {

        console.warn(
            "[CricBet] No matchOdds markets found:",
            payload
        );

        return emptyOdds();
    }


    /*
     * Usually first market is Match Odds.
     */

    let runners = [];

    for (const market of markets) {

        const found =
            findRunners(market);

        if (found.length) {
            runners = found;
            break;
        }
    }


    if (!runners.length) {

        console.warn(
            "[CricBet] No runners found in matchOdds:",
            markets
        );

        return emptyOdds();
    }


    const normalized =
        normalizeRunners(runners);


    const selectionIds = [
        getSelectionId(match, 1),
        getSelectionId(match, 2),
        getSelectionId(match, 3)
    ];


    const result =
        emptyOdds();


    const slots = [
        "team1",
        "team2",
        "team3"
    ];


    /*
     * First match by selection ID.
     */

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
                selectionIds.indexOf(
                    runnerId
                );


            if (index >= 0) {

                result[
                    slots[index]
                ] = {
                    back: runner.back,
                    lay: runner.lay,
                    backSize:
                        runner.backSize,
                    laySize:
                        runner.laySize
                };
            }
        }
    );


    /*
     * Fallback:
     * If selection IDs were not present
     * in /matches, use runner order.
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
                        back: runner.back,
                        lay: runner.lay,
                        backSize:
                            runner.backSize,
                        laySize:
                            runner.laySize
                    };
                }
            }
        );


    console.log(
        "[CricBet] Normalized odds:",
        getGameId(match),
        result
    );


    return result;
}


/* =========================================================
   CREATE ODDS BUTTON
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

    const disabled =
        numericPrice === null;


    return `
        <button
            type="button"
            class="odds-cell ${className}"
            data-game-id="${escapeHtml(gameId)}"
            data-event-id="${escapeHtml(eventId)}"
            data-market-id="${escapeHtml(marketId)}"
            data-selection-id="${escapeHtml(selectionId)}"
            data-team="${escapeHtml(team)}"
            data-side="${escapeHtml(side)}"
            data-price="${numericPrice ?? ""}"
            ${disabled ? "disabled" : ""}
        >
            <span class="odds-price">
                ${
                    numericPrice !== null
                        ? numericPrice.toFixed(2)
                        : "-"
                }
            </span>
        </button>
    `;
}


/* =========================================================
   CREATE MATCH ROW
========================================================= */

function createMatchRow(match) {

    const gameId =
        getGameId(match);

    const eventId =
        getEventId(match);

    const marketId =
        getMarketId(match);


    const eventName =
        match.event_name ??
        match.eventName ??
        "Cricket Match";


    const eventTime =
        match.event_time ??
        match.eventTime ??
        "";


    const team1 =
        match.team1 ??
        match.runnerName1 ??
        "Team 1";


    const team2 =
        match.team2 ??
        match.runnerName2 ??
        "Team 2";


    const team3 =
        match.team3 ??
        match.runnerName3 ??
        "";


    const odds =
        oddsCache.has(gameId)
            ? normalizeMatchOdds(
                match,
                oddsCache.get(gameId)
            )
            : emptyOdds();


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
                        isLive(match)
                            ? `
                                <span class="live-dot"></span>
                                <span class="match-status live-status">
                                    LIVE
                                </span>
                              `
                            : `
                                <span class="match-status upcoming-status">
                                    UPCOMING
                                </span>
                              `
                    }

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


            ${createOddsButton({
                gameId,
                eventId,
                marketId,
                selectionId:
                    getSelectionId(match, 1),
                team: team1,
                side: "back",
                price: odds.team1.back,
                className: "odds-team-1"
            })}


            ${createOddsButton({
                gameId,
                eventId,
                marketId,
                selectionId:
                    getSelectionId(match, 2),
                team: team2,
                side: "back",
                price: odds.team2.back,
                className: "odds-team-2"
            })}


            ${
                team3
                    ? createOddsButton({
                        gameId,
                        eventId,
                        marketId,
                        selectionId:
                            getSelectionId(
                                match,
                                3
                            ),
                        team: team3,
                        side: "back",
                        price:
                            odds.team3.back,
                        className:
                            "odds-draw"
                    })
                    : ""
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


    if (!allMatches.length) {

        container.innerHTML = `
            <div class="empty-state">

                <div class="empty-state-icon">
                    🏏
                </div>

                <div class="empty-state-title">
                    Loading cricket matches...
                </div>

                <div class="empty-state-text">
                    Fetching live cricket data.
                </div>

            </div>
        `;
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


        if (!response.ok) {

            throw new Error(
                payload?.error ||
                payload?.detail ||
                "Unable to load cricket matches."
            );
        }


        if (
            payload.success !== true
        ) {

            throw new Error(
                payload?.error ||
                "Cricket API request failed."
            );
        }


        if (
            !Array.isArray(
                payload.matches
            )
        ) {

            throw new Error(
                "Invalid matches response."
            );
        }


        allMatches =
            payload.matches;


        console.log(
            "[CricBet] Matches:",
            allMatches
        );


        renderMatches();


        loadAllOdds();


    } catch (error) {

        console.error(
            "CRICKET MATCH ERROR:",
            error
        );


        if (!allMatches.length) {

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
                        onclick="loadMatches()"
                    >
                        RETRY
                    </button>

                </div>
            `;
        }
    }
}


/* =========================================================
   LOAD ODDS FOR MATCH
========================================================= */

async function loadOddsForMatch(match) {

    const gameId =
        getGameId(match);

    const eventId =
        getEventId(match);

    const marketId =
        getMarketId(match);


    if (!gameId || !eventId) {

        console.warn(
            "[CricBet] Missing IDs:",
            {
                gameId,
                eventId,
                marketId
            }
        );

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

        params.set(
            "eventId",
            eventId
        );


        if (marketId) {

            params.set(
                "marketId",
                marketId
            );
        }


        const url =
            `/api/cricket/odds?${params.toString()}`;


        console.log(
            "[CricBet] Loading odds:",
            url
        );


        const response =
            await fetch(
                url,
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


        if (!response.ok) {

            throw new Error(
                payload?.error ||
                payload?.detail ||
                `Odds HTTP ${response.status}`
            );
        }


        if (
            payload.success !== true
        ) {

            throw new Error(
                payload?.error ||
                "Odds request failed."
            );
        }


        /*
         * Store the COMPLETE response.
         *
         * Do NOT strip payload.odds here.
         */

        oddsCache.set(
            gameId,
            payload
        );


        console.log(
            "[CricBet] Raw odds:",
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

    if (!allMatches.length) {
        return;
    }


    const batchSize = 5;


    for (
        let i = 0;
        i < allMatches.length;
        i += batchSize
    ) {

        const batch =
            allMatches.slice(
                i,
                i + batchSize
            );


        await Promise.all(
            batch.map(
                match =>
                    loadOddsForMatch(
                        match
                    )
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


    const row =
        document.querySelector(
            `.sportsbook-match-row[data-game-id="${CSS.escape(gameId)}"]`
        );


    if (!row) {
        return;
    }


    const odds =
        normalizeMatchOdds(
            match,
            oddsCache.get(gameId)
        );


    updateOddsButton(
        row.querySelector(
            ".odds-team-1"
        ),
        odds.team1.back
    );


    updateOddsButton(
        row.querySelector(
            ".odds-team-2"
        ),
        odds.team2.back
    );


    updateOddsButton(
        row.querySelector(
            ".odds-draw"
        ),
        odds.team3.back
    );
}


/* =========================================================
   UPDATE ODDS BUTTON
========================================================= */

function updateOddsButton(
    button,
    price
) {

    if (!button) {
        return;
    }


    const numericPrice =
        toNumber(price);


    const span =
        button.querySelector(
            ".odds-price"
        );


    if (
        numericPrice === null
    ) {

        button.disabled = true;

        button.dataset.price = "";


        if (span) {

            span.textContent = "-";
        }


        return;
    }


    button.disabled = false;


    button.dataset.price =
        String(numericPrice);


    if (span) {

        span.textContent =
            numericPrice.toFixed(2);
    }
}


/* =========================================================
   FILTER
========================================================= */

function setFilter(filter) {

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
                    button.dataset.filter ===
                        filter
                );
            }
        );


    renderMatches();
}


function renderMatches() {

    const container =
        document.getElementById(
            "matches"
        );


    if (!container) {
        return;
    }


    let matches =
        [...allMatches];


    if (
        currentFilter === "live"
    ) {

        matches =
            matches.filter(
                isLive
            );
    }


    if (
        currentFilter === "upcoming"
    ) {

        matches =
            matches.filter(
                match => !isLive(match)
            );
    }


    if (!matches.length) {

        container.innerHTML = `
            <div class="empty-state">

                <div class="empty-state-icon">
                    🏏
                </div>

                <div class="empty-state-title">
                    No cricket matches
                </div>

                <div class="empty-state-text">
                    No matches are currently available for this filter.
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


        if (!response.ok) {
            return;
        }


        const data =
            await response.json();


        if (
            data.balance === undefined
        ) {
            return;
        }


        const balance =
            Number(data.balance);


        const formatted =
            Number.isFinite(balance)
                ? balance.toLocaleString(
                    "en-IN",
                    {
                        minimumFractionDigits:
                            2,
                        maximumFractionDigits:
                            2
                    }
                )
                : "0.00";


        const balanceElement =
            document.getElementById(
                "balance"
            );


        const betslipBalance =
            document.getElementById(
                "betslipBalance"
            );


        if (balanceElement) {

            balanceElement.textContent =
                `₹${formatted}`;
        }


        if (betslipBalance) {

            betslipBalance.textContent =
                `₹${formatted}`;
        }


    } catch (error) {

        console.warn(
            "Balance loading failed:",
            error
        );
    }
}


/* =========================================================
   BETSLIP
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


    const mobileButton =
        document.getElementById(
            "mobileBetslipButton"
        );


    if (
        closeButton &&
        betslip
    ) {

        closeButton.addEventListener(
            "click",
            () => {

                betslip.classList.remove(
                    "open"
                );
            }
        );
    }


    if (
        mobileButton &&
        betslip
    ) {

        mobileButton.addEventListener(
            "click",
            () => {

                betslip.classList.toggle(
                    "open"
                );
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
            !Number.isFinite(price)
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
            "CRICBET ODDS SELECTED:",
            selection
        );


        document.dispatchEvent(
            new CustomEvent(
                "cricbet:oddsSelected",
                {
                    detail:
                        selection
                }
            )
        );
    }
);


/* =========================================================
   INITIALIZE
========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    () => {

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


        const depositButton =
            document.getElementById(
                "depositBtn"
            );


        if (depositButton) {

            depositButton.addEventListener(
                "click",
                openDepositWhatsApp
            );
        }


        const withdrawButton =
            document.getElementById(
                "withdrawBtn"
            );


        if (withdrawButton) {

            withdrawButton.addEventListener(
                "click",
                openWithdrawWhatsApp
            );
        }


        setupBetslip();


        loadBalance();


        loadMatches();


        setInterval(
            loadMatches,
            MATCH_REFRESH_MS
        );


        setInterval(
            () => {

                if (
                    allMatches.length
                ) {

                    allMatches.forEach(
                        loadOddsForMatch
                    );
                }

            },
            ODDS_REFRESH_MS
        );


        setInterval(
            loadBalance,
            15000
        );
    }
);