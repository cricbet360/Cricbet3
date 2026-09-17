"use strict";

/* =========================================================
   CRICKBET — FAST BET SLIP
   ========================================================= */

const betSlipState = [];


/* =========================================================
   ELEMENTS
   ========================================================= */

const overlay = document.getElementById("betslipOverlay");
const betslip = document.getElementById("betslip");
const closeButton = document.getElementById("closeBetslip");

const selectionsContainer =
    document.getElementById("betslipSelections");

const stakeInput =
    document.getElementById("stakeInput");

const potentialWinElement =
    document.getElementById("potentialWin");

const placeBetButton =
    document.getElementById("placeBetButton");

const betslipError =
    document.getElementById("betslipError");

const betslipCount =
    document.getElementById("betslipCount");

const mobileBetslipButton =
    document.getElementById("mobileBetslipButton");

const mobileBetslipCount =
    document.getElementById("mobileBetslipCount");


/* =========================================================
   OPEN BET SLIP
   ========================================================= */

function openBetSlip() {

    if (!overlay) {
        return;
    }

    overlay.classList.add("open");

    overlay.setAttribute(
        "aria-hidden",
        "false"
    );

    document.body.style.overflow = "hidden";
}


/* =========================================================
   CLOSE BET SLIP
   ========================================================= */

function closeBetSlip() {

    if (!overlay) {
        return;
    }

    overlay.classList.remove("open");

    overlay.setAttribute(
        "aria-hidden",
        "true"
    );

    document.body.style.overflow = "";
}


/* =========================================================
   ERROR
   ========================================================= */

function showError(message) {

    if (!betslipError) {
        return;
    }

    betslipError.textContent = message;
    betslipError.hidden = false;
}


function hideError() {

    if (!betslipError) {
        return;
    }

    betslipError.textContent = "";
    betslipError.hidden = true;
}


/* =========================================================
   FORMAT MONEY
   ========================================================= */

function formatMoney(value) {

    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "₹0.00";
    }

    return "₹" + number.toFixed(2);
}


/* =========================================================
   HTML ESCAPE
   ========================================================= */

function escapeHtml(value) {

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


/* =========================================================
   ADD / UPDATE SELECTION
   ========================================================= */

function addSelection(button) {

    if (!button || button.disabled) {
        return;
    }

    const marketId =
        button.dataset.marketId;

    const selectionId =
        button.dataset.selectionId;

    const runnerName =
        button.dataset.runnerName || "Selection";

    const side =
        String(button.dataset.side || "")
            .toUpperCase();

    const price =
        Number(button.dataset.price);


    if (!marketId) {

        showError("Market ID is missing.");
        openBetSlip();

        return;
    }


    if (!selectionId) {

        showError("Selection ID is missing.");
        openBetSlip();

        return;
    }


    if (!["BACK", "LAY"].includes(side)) {

        showError("Invalid bet side.");
        openBetSlip();

        return;
    }


    if (!Number.isFinite(price) || price <= 0) {

        showError("Selected odds are unavailable.");
        openBetSlip();

        return;
    }


    hideError();


    /*
       One selection can only exist once.

       Same side:
       remove it.

       Different side:
       change BACK ↔ LAY.
    */

    const existingIndex =
        betSlipState.findIndex(
            item =>
                String(item.marketId) === String(marketId) &&
                String(item.selectionId) === String(selectionId)
        );


    if (existingIndex !== -1) {

        const existing =
            betSlipState[existingIndex];


        if (existing.side === side) {

            betSlipState.splice(
                existingIndex,
                1
            );

        } else {

            betSlipState[existingIndex] = {

                marketId,
                selectionId,
                runnerName,
                side,
                price

            };

        }

    } else {

        betSlipState.push({

            marketId,
            selectionId,
            runnerName,
            side,
            price

        });

    }


    renderBetSlip();

    openBetSlip();
}


/* =========================================================
   REMOVE SELECTION
   ========================================================= */

function removeSelection(
    marketId,
    selectionId
) {

    const index =
        betSlipState.findIndex(
            item =>
                String(item.marketId) === String(marketId) &&
                String(item.selectionId) === String(selectionId)
        );


    if (index !== -1) {

        betSlipState.splice(
            index,
            1
        );

    }


    renderBetSlip();
}


/* =========================================================
   TOTAL ODDS
   ========================================================= */

function calculateTotalOdds() {

    if (betSlipState.length === 0) {
        return 1;
    }


    return betSlipState.reduce(
        (total, selection) => {

            const price =
                Number(selection.price);

            if (
                !Number.isFinite(price) ||
                price <= 0
            ) {
                return total;
            }

            return total * price;

        },
        1
    );
}


/* =========================================================
   POTENTIAL WIN
   ========================================================= */

function calculatePotentialWin() {

    const stake =
        Number(
            stakeInput
                ? stakeInput.value
                : 0
        );


    if (
        !Number.isFinite(stake) ||
        stake <= 0 ||
        betSlipState.length === 0
    ) {

        return 0;
    }


    return (
        stake *
        calculateTotalOdds()
    );
}


/* =========================================================
   UPDATE POTENTIAL WIN
   ========================================================= */

function updatePotentialWin() {

    const totalOdds =
        calculateTotalOdds();

    const potentialWin =
        calculatePotentialWin();


    if (potentialWinElement) {

        potentialWinElement.textContent =
            formatMoney(potentialWin);
    }


    if (placeBetButton) {

        placeBetButton.disabled =
            betSlipState.length === 0 ||
            potentialWin <= 0;
    }


    return {
        totalOdds,
        potentialWin
    };
}


/* =========================================================
   RENDER BET SLIP
   ========================================================= */

function renderBetSlip() {

    if (!selectionsContainer) {
        return;
    }


    const count =
        betSlipState.length;


    /* Desktop count */

    if (betslipCount) {

        if (count === 0) {

            betslipCount.textContent =
                "No selections";

        } else {

            betslipCount.textContent =
                count +
                (
                    count === 1
                        ? " selection"
                        : " selections"
                );
        }
    }


    /* Mobile count */

    if (mobileBetslipCount) {

        mobileBetslipCount.textContent =
            String(count);
    }


    /* Empty */

    if (count === 0) {

        selectionsContainer.innerHTML = `

            <div class="no-selections">

                <div class="no-selection-icon">
                    🎟️
                </div>

                <p>
                    Select a BACK or LAY price
                    to add a bet.
                </p>

            </div>

        `;

        updatePotentialWin();

        return;
    }


    let html = "";


    betSlipState.forEach(
        selection => {

            const sideClass =
                selection.side === "BACK"
                    ? "back"
                    : "lay";


            html += `

                <div
                    class="slip-item"
                    data-market-id="${escapeHtml(selection.marketId)}"
                    data-selection-id="${escapeHtml(selection.selectionId)}"
                >

                    <div class="slip-item-top">

                        <div class="slip-item-name">
                            ${escapeHtml(selection.runnerName)}
                        </div>

                        <button
                            type="button"
                            class="slip-item-remove"
                            data-remove-market="${escapeHtml(selection.marketId)}"
                            data-remove-selection="${escapeHtml(selection.selectionId)}"
                            aria-label="Remove selection"
                        >
                            ×
                        </button>

                    </div>


                    <div class="slip-item-meta">

                        <span class="slip-side ${sideClass}">
                            ${escapeHtml(selection.side)}
                        </span>

                        <span class="slip-price">
                            ${Number(selection.price).toFixed(2)}
                        </span>

                    </div>


                    <div class="slip-market">
                        ${escapeHtml(selection.marketId)}
                    </div>

                </div>

            `;
        }
    );


    selectionsContainer.innerHTML =
        html;


    updatePotentialWin();
}


/* =========================================================
   UPDATE BALANCE WITHOUT PAGE RELOAD
   ========================================================= */

function updateDisplayedBalance(balance) {

    if (balance === undefined || balance === null) {
        return;
    }


    const number =
        Number(balance);


    if (!Number.isFinite(number)) {
        return;
    }


    /*
       Your dashboard currently has:

       <span class="balance">
           ₹...
       </span>
    */

    const balanceElements =
        document.querySelectorAll(
            ".balance"
        );


    balanceElements.forEach(
        element => {

            element.textContent =
                formatMoney(number);

        }
    );
}


/* =========================================================
   ODDS CLICK
   ========================================================= */

document.addEventListener(
    "click",
    function(event) {

        const button =
            event.target.closest(
                ".odd-button"
            );


        if (!button) {
            return;
        }


        if (button.disabled) {
            return;
        }


        addSelection(button);
    }
);


/* =========================================================
   REMOVE CLICK
   ========================================================= */

document.addEventListener(
    "click",
    function(event) {

        const button =
            event.target.closest(
                ".slip-item-remove"
            );


        if (!button) {
            return;
        }


        removeSelection(
            button.dataset.removeMarket,
            button.dataset.removeSelection
        );
    }
);


/* =========================================================
   CLOSE BUTTON
   ========================================================= */

if (closeButton) {

    closeButton.addEventListener(
        "click",
        closeBetSlip
    );
}


/* =========================================================
   CLICK OUTSIDE
   ========================================================= */

if (overlay) {

    overlay.addEventListener(
        "click",
        function(event) {

            if (
                event.target === overlay
            ) {

                closeBetSlip();
            }
        }
    );
}


/* =========================================================
   MOBILE BET SLIP
   ========================================================= */

if (mobileBetslipButton) {

    mobileBetslipButton.addEventListener(
        "click",
        openBetSlip
    );
}


/* =========================================================
   STAKE INPUT
   ========================================================= */

if (stakeInput) {

    stakeInput.addEventListener(
        "input",
        function() {

            hideError();

            updatePotentialWin();
        }
    );
}


/* =========================================================
   ESCAPE
   ========================================================= */

document.addEventListener(
    "keydown",
    function(event) {

        if (event.key === "Escape") {

            closeBetSlip();
        }
    }
);


/* =========================================================
   PLACE BET
   ========================================================= */

if (placeBetButton) {

    placeBetButton.addEventListener(
        "click",
        async function() {

            hideError();


            if (betSlipState.length === 0) {

                showError(
                    "Please select a bet first."
                );

                return;
            }


            const stake =
                Number(
                    stakeInput
                        ? stakeInput.value
                        : 0
                );


            if (
                !Number.isFinite(stake) ||
                stake <= 0
            ) {

                showError(
                    "Please enter a valid stake."
                );

                if (stakeInput) {
                    stakeInput.focus();
                }

                return;
            }


            /*
               Snapshot the selections.

               This prevents the user from
               changing the original request
               while the request is being sent.
            */

            const selectionsToPlace =
                betSlipState.map(
                    selection => ({

                        marketId:
                            selection.marketId,

                        selectionId:
                            selection.selectionId,

                        side:
                            selection.side

                    })
                );


            placeBetButton.disabled =
                true;

            placeBetButton.textContent =
                "Placing...";


            try {

                const response =
                    await fetch(
                        "/bets/place",
                        {

                            method: "POST",

                            headers: {

                                "Content-Type":
                                    "application/json",

                                "Accept":
                                    "application/json"

                            },

                            credentials:
                                "same-origin",

                            body:
                                JSON.stringify({

                                    selections:
                                        selectionsToPlace,

                                    stake:
                                        stake

                                })

                        }
                    );


                const result =
                    await response
                        .json()
                        .catch(
                            () => ({})
                        );


                if (!response.ok) {

                    throw new Error(
                        result.message ||
                        "Could not place bet."
                    );
                }


                if (!result.success) {

                    throw new Error(
                        result.message ||
                        "Could not place bet."
                    );
                }


                /*
                   ==========================================
                   SUCCESS
                   ==========================================
                */


                /*
                   Update balance immediately.
                   NO PAGE RELOAD.
                */

                if (
                    result.balance !== undefined
                ) {

                    updateDisplayedBalance(
                        result.balance
                    );
                }


                /*
                   Remove only the selections
                   that were successfully placed.
                */

                selectionsToPlace.forEach(
                    placed => {

                        const index =
                            betSlipState.findIndex(
                                item =>
                                    String(
                                        item.marketId
                                    ) === String(
                                        placed.marketId
                                    ) &&
                                    String(
                                        item.selectionId
                                    ) === String(
                                        placed.selectionId
                                    ) &&
                                    item.side ===
                                        placed.side
                            );


                        if (index !== -1) {

                            betSlipState.splice(
                                index,
                                1
                            );
                        }
                    }
                );


                /*
                   Clear stake so the user can
                   immediately enter the next stake.
                */

                if (stakeInput) {

                    stakeInput.value = "";
                }


                renderBetSlip();


                /*
                   Keep the betslip OPEN.

                   This is important for fast
                   2nd / 3rd / 4th betting.
                */

                openBetSlip();


                /*
                   Small success message instead
                   of blocking alert().
                */

                showSuccessMessage(
                    "Bet placed successfully • Bet #" +
                    result.bet_id
                );


                /*
                   Dispatch event so other
                   frontend components can react.
                */

                document.dispatchEvent(
                    new CustomEvent(
                        "crickbet:betPlaced",
                        {
                            detail: result
                        }
                    )
                );


            } catch (error) {

                console.error(
                    "Place bet error:",
                    error
                );


                showError(
                    error.message ||
                    "Could not place bet."
                );


            } finally {

                placeBetButton.textContent =
                    "Place Bet";


                updatePotentialWin();
            }
        }
    );
}


/* =========================================================
   SUCCESS MESSAGE
   ========================================================= */

function showSuccessMessage(message) {

    if (!betslipError) {
        return;
    }


    betslipError.textContent =
        message;


    betslipError.hidden =
        false;


    betslipError.classList.add(
        "success"
    );


    setTimeout(
        function() {

            if (!betslipError) {
                return;
            }

            betslipError.classList.remove(
                "success"
            );

            betslipError.textContent =
                "";

            betslipError.hidden =
                true;

        },
        3000
    );
}


/* =========================================================
   INITIAL RENDER
   ========================================================= */

renderBetSlip();