from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import (
    APIRouter,
    Request,
    Depends,
    Form,
)

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database.database import get_db

from models.employee import Employee
from models.deposit_request import DepositRequest
from models.withdrawal_request import WithdrawalRequest
from models.user import User
from models.wallet import Wallet
from models.transaction import Transaction


router = APIRouter()

templates = Jinja2Templates(
    directory="templates"
)


# =========================================================
# CONFIGURATION
# =========================================================

# ONLY referral bonus.
# There is NO separate deposit bonus.
REFERRAL_BONUS_RATE = Decimal("0.10")


# =========================================================
# EMPLOYEE AUTH
# =========================================================

def get_logged_in_employee(
    request: Request,
    db: Session
):
    employee_id = request.session.get("employee_id")

    if not employee_id:
        return None

    employee = (
        db.query(Employee)
        .filter(
            Employee.id == employee_id,
            Employee.status == "Active"
        )
        .first()
    )

    return employee


# =========================================================
# DASHBOARD COUNTS
# =========================================================

def get_dashboard_counts(
    db: Session
):
    pending_deposits = (
        db.query(DepositRequest)
        .filter(
            DepositRequest.status == "Pending"
        )
        .count()
    )

    completed_deposits = (
        db.query(DepositRequest)
        .filter(
            DepositRequest.status == "Completed"
        )
        .count()
    )

    pending_withdrawals = (
        db.query(WithdrawalRequest)
        .filter(
            WithdrawalRequest.status == "Pending"
        )
        .count()
    )

    completed_withdrawals = (
        db.query(WithdrawalRequest)
        .filter(
            WithdrawalRequest.status == "Completed"
        )
        .count()
    )

    return (
        pending_deposits,
        completed_deposits,
        pending_withdrawals,
        completed_withdrawals,
    )


# =========================================================
# DASHBOARD RENDER
# =========================================================

def render_dashboard(
    request: Request,
    db: Session,
    employee,
    searched_user=None,
    search_username="",
    search_phone="",
    balance_error=None,
    balance_success=None,
):
    (
        pending_deposits,
        completed_deposits,
        pending_withdrawals,
        completed_withdrawals,
    ) = get_dashboard_counts(db)

    return templates.TemplateResponse(
        "employee/dashboard.html",
        {
            "request": request,
            "employee": employee,

            "pending_deposits": pending_deposits,
            "completed_deposits": completed_deposits,

            "pending_withdrawals": pending_withdrawals,
            "completed_withdrawals": completed_withdrawals,

            "searched_user": searched_user,

            "search_username": search_username,
            "search_phone": search_phone,

            "balance_error": balance_error,
            "balance_success": balance_success,
        }
    )


# =========================================================
# EMPLOYEE DASHBOARD
# =========================================================

@router.get("/employee/dashboard")
def employee_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    return render_dashboard(
        request,
        db,
        employee
    )


# =========================================================
# DEPOSIT REQUESTS
# =========================================================

@router.get("/employee/deposits")
def employee_deposits(
    request: Request,
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    deposits = (
        db.query(DepositRequest)
        .filter(
            DepositRequest.status == "Pending"
        )
        .order_by(
            DepositRequest.id.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        "employee/deposits.html",
        {
            "request": request,
            "employee": employee,
            "deposits": deposits,
        }
    )


@router.get("/employee/deposits/done")
def employee_completed_deposits(
    request: Request,
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    deposits = (
        db.query(DepositRequest)
        .filter(
            DepositRequest.status == "Completed"
        )
        .order_by(
            DepositRequest.id.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        "employee/deposits_done.html",
        {
            "request": request,
            "employee": employee,
            "deposits": deposits,
        }
    )


# =========================================================
# REFERRAL BONUS HELPER
# =========================================================

def process_referral_bonus(
    db: Session,
    user: User,
    qualifying_amount: Decimal,
):
    """
    Referral rules:

    1. Only the FIRST qualifying deposit/add-balance
       of a referred user can trigger referral bonuses.

    2. Referred NEW user receives 10%.

    3. The OLD user who referred them receives 10%.

    4. The same old referrer can receive bonuses from
       unlimited different referred users.

    5. The referral event is marked on the referred user,
       not globally on the referrer.
    """

    # -----------------------------------------------------
    # Already processed?
    # -----------------------------------------------------

    first_deposit_completed = bool(
        getattr(
            user,
            "first_deposit_completed",
            False
        )
    )

    referral_bonus_paid = bool(
        getattr(
            user,
            "referral_bonus_paid",
            False
        )
    )

    # If this user already completed the first deposit,
    # there is nothing more to do.
    if first_deposit_completed:
        return Decimal("0.00")

    # -----------------------------------------------------
    # Mark first qualifying deposit
    # -----------------------------------------------------

    user.first_deposit_completed = True

    # -----------------------------------------------------
    # Check whether this user was referred
    # -----------------------------------------------------

    referred_by_user_id = getattr(
        user,
        "referred_by_user_id",
        None
    )

    if not referred_by_user_id:
        return Decimal("0.00")

    # Safety: referral event already paid
    if referral_bonus_paid:
        return Decimal("0.00")

    # -----------------------------------------------------
    # Find old referrer
    # -----------------------------------------------------

    referrer = (
        db.query(User)
        .filter(
            User.id == referred_by_user_id
        )
        .with_for_update()
        .first()
    )

    if not referrer:
        return Decimal("0.00")

    # A user cannot refer themselves.
    if referrer.id == user.id:
        return Decimal("0.00")

    # -----------------------------------------------------
    # Calculate ONLY referral bonus
    # -----------------------------------------------------

    referral_bonus = (
        qualifying_amount *
        REFERRAL_BONUS_RATE
    ).quantize(
        Decimal("0.01")
    )

    if referral_bonus <= Decimal("0.00"):
        return Decimal("0.00")

    # =====================================================
    # 1. BONUS TO NEW REFERRED USER
    # =====================================================

    current_user_balance = Decimal(
        str(user.balance or 0)
    )

    user.balance = float(
        current_user_balance +
        referral_bonus
    )

    # Wallet
    user_wallet = (
        db.query(Wallet)
        .filter(
            Wallet.user_id == user.id
        )
        .with_for_update()
        .first()
    )

    if not user_wallet:
        user_wallet = Wallet(
            user_id=user.id,
            balance=0
        )

        db.add(user_wallet)
        db.flush()

    current_wallet_balance = Decimal(
        str(user_wallet.balance or 0)
    )

    user_wallet.balance = float(
        current_wallet_balance +
        referral_bonus
    )

    # Transaction for NEW referred user
    db.add(
        Transaction(
            user_id=user.id,
            amount=referral_bonus,
            transaction_type="REFERRAL_BONUS",
            status="Completed",
            reference_type="User",
            reference_id=referrer.id,
            description=(
                f"10% referral bonus from "
                f"{getattr(referrer, 'username', 'referrer')}"
            ),
        )
    )

    # =====================================================
    # 2. BONUS TO OLD REFERRER
    # =====================================================

    referrer_balance = Decimal(
        str(referrer.balance or 0)
    )

    referrer.balance = float(
        referrer_balance +
        referral_bonus
    )

    # Referrer wallet
    referrer_wallet = (
        db.query(Wallet)
        .filter(
            Wallet.user_id == referrer.id
        )
        .with_for_update()
        .first()
    )

    if not referrer_wallet:
        referrer_wallet = Wallet(
            user_id=referrer.id,
            balance=0
        )

        db.add(referrer_wallet)
        db.flush()

    referrer_wallet_balance = Decimal(
        str(referrer_wallet.balance or 0)
    )

    referrer_wallet.balance = float(
        referrer_wallet_balance +
        referral_bonus
    )

    # Transaction for OLD referrer
    db.add(
        Transaction(
            user_id=referrer.id,
            amount=referral_bonus,
            transaction_type="REFERRAL_BONUS",
            status="Completed",
            reference_type="User",
            reference_id=user.id,
            description=(
                f"10% referral bonus from "
                f"{getattr(user, 'username', 'new user')}"
            ),
        )
    )

    # -----------------------------------------------------
    # VERY IMPORTANT
    #
    # This flag belongs to the NEW REFERRED USER.
    #
    # It does NOT belong to the old referrer.
    #
    # Therefore the same old referrer can earn again
    # when another new user is referred.
    # -----------------------------------------------------

    user.referral_bonus_paid = True

    return referral_bonus


# =========================================================
# COMPLETE DEPOSIT REQUEST
# =========================================================

@router.post("/employee/deposits/{deposit_id}/done")
def complete_deposit(
    deposit_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    # -----------------------------------------------------
    # Lock deposit request
    # -----------------------------------------------------

    deposit = (
        db.query(DepositRequest)
        .filter(
            DepositRequest.id == deposit_id
        )
        .with_for_update()
        .first()
    )

    if not deposit:
        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )

    # -----------------------------------------------------
    # Already completed
    # -----------------------------------------------------

    if deposit.status == "Completed":
        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )

    # -----------------------------------------------------
    # Lock user
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.id == deposit.user_id
        )
        .with_for_update()
        .first()
    )

    if not user:
        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )

    try:
        deposit_amount = Decimal(
            str(deposit.amount)
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )

    if deposit_amount <= Decimal("0.00"):
        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )

    # -----------------------------------------------------
    # Duplicate transaction protection
    # -----------------------------------------------------

    existing_transaction = (
        db.query(Transaction)
        .filter(
            Transaction.reference_type == "DepositRequest",
            Transaction.reference_id == deposit.id,
            Transaction.transaction_type.in_(
                [
                    "DEPOSIT",
                    "Deposit",
                ]
            ),
        )
        .first()
    )

    if existing_transaction:
        deposit.status = "Completed"

        if hasattr(deposit, "processed_by_employee_id"):
            deposit.processed_by_employee_id = employee.id

        if hasattr(deposit, "processed_by"):
            deposit.processed_by = employee.employee_id

        if hasattr(deposit, "completed_at"):
            deposit.completed_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )

    # -----------------------------------------------------
    # User balance
    # -----------------------------------------------------

    current_balance = Decimal(
        str(user.balance or 0)
    )

    user.balance = float(
        current_balance +
        deposit_amount
    )

    # -----------------------------------------------------
    # Wallet
    # -----------------------------------------------------

    wallet = (
        db.query(Wallet)
        .filter(
            Wallet.user_id == user.id
        )
        .with_for_update()
        .first()
    )

    if not wallet:
        wallet = Wallet(
            user_id=user.id,
            balance=0
        )

        db.add(wallet)
        db.flush()

    wallet_balance = Decimal(
        str(wallet.balance or 0)
    )

    wallet.balance = float(
        wallet_balance +
        deposit_amount
    )

    # -----------------------------------------------------
    # Deposit transaction
    # -----------------------------------------------------

    db.add(
        Transaction(
            user_id=user.id,
            amount=deposit_amount,
            transaction_type="DEPOSIT",
            status="Completed",
            reference_type="DepositRequest",
            reference_id=deposit.id,
            description=(
                f"Deposit approved by employee "
                f"{employee.employee_id}"
            ),
        )
    )

    # -----------------------------------------------------
    # ONLY REFERRAL BONUS
    # -----------------------------------------------------

    process_referral_bonus(
        db=db,
        user=user,
        qualifying_amount=deposit_amount,
    )

    # -----------------------------------------------------
    # Mark deposit completed
    # -----------------------------------------------------

    deposit.status = "Completed"

    if hasattr(deposit, "processed_by_employee_id"):
        deposit.processed_by_employee_id = employee.id

    if hasattr(deposit, "processed_by"):
        deposit.processed_by = employee.employee_id

    if hasattr(deposit, "completed_at"):
        deposit.completed_at = datetime.utcnow()

    db.commit()

    return RedirectResponse(
        "/employee/deposits",
        status_code=303
    )


# =========================================================
# SEARCH USER FOR BALANCE
# =========================================================

# =========================================================
# SEARCH USER FOR BALANCE - GET
# =========================================================

@router.get("/employee/balance/search")
def search_user_balance_get(
    request: Request,
    username: str = "",
    phone: str = "",
    balance_success: str = "",
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    username = username.strip()
    phone = phone.strip()

    searched_user = None

    # Search by username OR phone
    if username or phone:

        filters = []

        if username:
            filters.append(
                User.username == username
            )

        if phone:
            filters.append(
                User.phone == phone
            )

        searched_user = (
            db.query(User)
            .filter(or_(*filters))
            .first()
        )

    return render_dashboard(
        request=request,
        db=db,
        employee=employee,
        searched_user=searched_user,
        search_username=username,
        search_phone=phone,
        balance_success=balance_success,
    )


# =========================================================
# SEARCH USER FOR BALANCE - POST
# =========================================================

@router.post("/employee/balance/search")
def search_user_balance_post(
    request: Request,
    username: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    username = username.strip()
    phone = phone.strip()

    searched_user = None

    # -----------------------------------------------------
    # Search by username OR phone
    # -----------------------------------------------------

    if username or phone:

        filters = []

        if username:
            filters.append(
                User.username == username
            )

        if phone:
            filters.append(
                User.phone == phone
            )

        searched_user = (
            db.query(User)
            .filter(or_(*filters))
            .first()
        )

    # -----------------------------------------------------
    # User not found
    # -----------------------------------------------------

    if not searched_user:
        return render_dashboard(
            request=request,
            db=db,
            employee=employee,
            searched_user=None,
            search_username=username,
            search_phone=phone,
            balance_error="User not found.",
        )

    # -----------------------------------------------------
    # User found
    # -----------------------------------------------------

    return render_dashboard(
        request=request,
        db=db,
        employee=employee,
        searched_user=searched_user,
        search_username=username,
        search_phone=phone,
    )

# =========================================================
# EMPLOYEE ADD BALANCE
# =========================================================

@router.post("/employee/balance/add")
def employee_add_balance(
    request: Request,
    user_id: int = Form(...),
    amount: str = Form(...),
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    # -----------------------------------------------------
    # Parse amount
    # -----------------------------------------------------

    try:
        add_amount = Decimal(
            amount.strip()
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return render_dashboard(
            request,
            db,
            employee,
            balance_error="Invalid amount."
        )

    if add_amount <= Decimal("0.00"):
        return render_dashboard(
            request,
            db,
            employee,
            balance_error="Amount must be greater than 0."
        )

    # -----------------------------------------------------
    # Lock user
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .with_for_update()
        .first()
    )

    if not user:
        return render_dashboard(
            request,
            db,
            employee,
            balance_error="User not found."
        )

    # -----------------------------------------------------
    # Add actual balance
    #
    # NO deposit bonus here.
    # -----------------------------------------------------

    current_balance = Decimal(
        str(user.balance or 0)
    )

    user.balance = float(
        current_balance +
        add_amount
    )

    # -----------------------------------------------------
    # Wallet
    # -----------------------------------------------------

    wallet = (
        db.query(Wallet)
        .filter(
            Wallet.user_id == user.id
        )
        .with_for_update()
        .first()
    )

    if not wallet:
        wallet = Wallet(
            user_id=user.id,
            balance=0
        )

        db.add(wallet)
        db.flush()

    current_wallet_balance = Decimal(
        str(wallet.balance or 0)
    )

    wallet.balance = float(
        current_wallet_balance +
        add_amount
    )

    # -----------------------------------------------------
    # Employee Add Balance transaction
    # -----------------------------------------------------

    db.add(
        Transaction(
            user_id=user.id,
            amount=add_amount,
            transaction_type="DEPOSIT",
            status="Completed",
            reference_type="Employee",
            reference_id=employee.id,
            description=(
                f"Balance added by employee "
                f"{employee.employee_id}"
            ),
        )
    )

    # -----------------------------------------------------
    # ONLY REFERRAL BONUS
    #
    # If this is the user's first qualifying balance add
    # and the user was referred:
    #
    # NEW USER -> 10%
    # OLD REFERRER -> 10%
    # -----------------------------------------------------

    referral_bonus = process_referral_bonus(
        db=db,
        user=user,
        qualifying_amount=add_amount,
    )

    db.commit()

    # -----------------------------------------------------
    # Success
    # -----------------------------------------------------

    return RedirectResponse(
        (
            "/employee/balance/search"
            f"?username={user.username}"
            f"&balance_success=add"
        ),
        status_code=303
    )


# =========================================================
# EMPLOYEE WITHDRAW BALANCE
# =========================================================

@router.post("/employee/balance/withdraw")
def employee_withdraw_balance(
    request: Request,
    user_id: int = Form(...),
    amount: str = Form(...),
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    # -----------------------------------------------------
    # Parse amount
    # -----------------------------------------------------

    try:
        withdraw_amount = Decimal(
            amount.strip()
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return render_dashboard(
            request,
            db,
            employee,
            balance_error="Invalid amount."
        )

    if withdraw_amount <= Decimal("0.00"):
        return render_dashboard(
            request,
            db,
            employee,
            balance_error="Amount must be greater than 0."
        )

    # -----------------------------------------------------
    # Lock user
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .with_for_update()
        .first()
    )

    if not user:
        return render_dashboard(
            request,
            db,
            employee,
            balance_error="User not found."
        )

    current_balance = Decimal(
        str(user.balance or 0)
    )

    # -----------------------------------------------------
    # Insufficient balance
    # -----------------------------------------------------

    if withdraw_amount > current_balance:
        return render_dashboard(
            request,
            db,
            employee,
            searched_user=user,
            balance_error=(
                f"Insufficient balance. "
                f"Available balance: ₹{current_balance:.2f}"
            )
        )

    # -----------------------------------------------------
    # Wallet
    # -----------------------------------------------------

    wallet = (
        db.query(Wallet)
        .filter(
            Wallet.user_id == user.id
        )
        .with_for_update()
        .first()
    )

    if not wallet:
        wallet = Wallet(
            user_id=user.id,
            balance=float(current_balance)
        )

        db.add(wallet)
        db.flush()

    wallet_balance = Decimal(
        str(wallet.balance or 0)
    )

    # Keep wallet aligned with user's current balance
    # before deducting.
    if wallet_balance < withdraw_amount:
        wallet_balance = current_balance

    # -----------------------------------------------------
    # Deduct balance
    # -----------------------------------------------------

    user.balance = float(
        current_balance -
        withdraw_amount
    )

    wallet.balance = float(
        wallet_balance -
        withdraw_amount
    )

    # -----------------------------------------------------
    # Transaction
    # -----------------------------------------------------

    db.add(
        Transaction(
            user_id=user.id,
            amount=withdraw_amount,
            transaction_type="WITHDRAWAL",
            status="Completed",
            reference_type="Employee",
            reference_id=employee.id,
            description=(
                f"Balance withdrawn by employee "
                f"{employee.employee_id}"
            ),
        )
    )

    db.commit()

    return RedirectResponse(
        (
            "/employee/balance/search"
            f"?username={user.username}"
            f"&balance_success=withdraw"
        ),
        status_code=303
    )


# =========================================================
# WITHDRAWAL REQUESTS
# =========================================================

@router.get("/employee/withdrawals")
def employee_withdrawals(
    request: Request,
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    withdrawals = (
        db.query(WithdrawalRequest)
        .filter(
            WithdrawalRequest.status == "Pending"
        )
        .order_by(
            WithdrawalRequest.id.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        "employee/withdrawals.html",
        {
            "request": request,
            "employee": employee,
            "withdrawals": withdrawals,
        }
    )


@router.get("/employee/withdrawals/done")
def employee_completed_withdrawals(
    request: Request,
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    withdrawals = (
        db.query(WithdrawalRequest)
        .filter(
            WithdrawalRequest.status == "Completed"
        )
        .order_by(
            WithdrawalRequest.id.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        "employee/withdrawals_done.html",
        {
            "request": request,
            "employee": employee,
            "withdrawals": withdrawals,
        }
    )


# =========================================================
# COMPLETE WITHDRAWAL REQUEST
# =========================================================

@router.post("/employee/withdrawals/{withdrawal_id}/done")
def complete_withdrawal(
    withdrawal_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    # -----------------------------------------------------
    # Lock withdrawal
    # -----------------------------------------------------

    withdrawal = (
        db.query(WithdrawalRequest)
        .filter(
            WithdrawalRequest.id == withdrawal_id
        )
        .with_for_update()
        .first()
    )

    if not withdrawal:
        return RedirectResponse(
            "/employee/withdrawals",
            status_code=303
        )

    if withdrawal.status == "Completed":
        return RedirectResponse(
            "/employee/withdrawals",
            status_code=303
        )

    # -----------------------------------------------------
    # Lock user
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.id == withdrawal.user_id
        )
        .with_for_update()
        .first()
    )

    if not user:
        return RedirectResponse(
            "/employee/withdrawals",
            status_code=303
        )

    try:
        withdrawal_amount = Decimal(
            str(withdrawal.amount)
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return RedirectResponse(
            "/employee/withdrawals",
            status_code=303
        )

    if withdrawal_amount <= Decimal("0.00"):
        return RedirectResponse(
            "/employee/withdrawals",
            status_code=303
        )

    # -----------------------------------------------------
    # Check balance
    # -----------------------------------------------------

    current_balance = Decimal(
        str(user.balance or 0)
    )

    if withdrawal_amount > current_balance:
        return RedirectResponse(
            "/employee/withdrawals",
            status_code=303
        )

    # -----------------------------------------------------
    # Wallet
    # -----------------------------------------------------

    wallet = (
        db.query(Wallet)
        .filter(
            Wallet.user_id == user.id
        )
        .with_for_update()
        .first()
    )

    if not wallet:
        wallet = Wallet(
            user_id=user.id,
            balance=float(current_balance)
        )

        db.add(wallet)
        db.flush()

    wallet_balance = Decimal(
        str(wallet.balance or 0)
    )

    if wallet_balance < withdrawal_amount:
        wallet_balance = current_balance

    # -----------------------------------------------------
    # Deduct
    # -----------------------------------------------------

    user.balance = float(
        current_balance -
        withdrawal_amount
    )

    wallet.balance = float(
        wallet_balance -
        withdrawal_amount
    )

    # -----------------------------------------------------
    # Transaction
    # -----------------------------------------------------

    db.add(
        Transaction(
            user_id=user.id,
            amount=withdrawal_amount,
            transaction_type="WITHDRAWAL",
            status="Completed",
            reference_type="WithdrawalRequest",
            reference_id=withdrawal.id,
            description=(
                f"Withdrawal approved by employee "
                f"{employee.employee_id}"
            ),
        )
    )

    # -----------------------------------------------------
    # Mark completed
    # -----------------------------------------------------

    withdrawal.status = "Completed"

    if hasattr(withdrawal, "processed_by_employee_id"):
        withdrawal.processed_by_employee_id = employee.id

    if hasattr(withdrawal, "processed_by"):
        withdrawal.processed_by = employee.employee_id

    if hasattr(withdrawal, "completed_at"):
        withdrawal.completed_at = datetime.utcnow()

    db.commit()

    return RedirectResponse(
        "/employee/withdrawals",
        status_code=303
    )


# =========================================================
# TEST DEPOSIT REQUEST
# =========================================================

@router.post("/employee/test/create-deposit")
def create_test_deposit(
    request: Request,
    user_id: int = Form(...),
    amount: str = Form(...),
    db: Session = Depends(get_db)
):
    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    try:
        deposit_amount = Decimal(
            amount.strip()
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )

    if deposit_amount <= Decimal("0.00"):
        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:
        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )

    test_deposit = DepositRequest(
        user_id=user.id,
        amount=deposit_amount,
        status="Pending",
    )

    # Add optional fields only if they exist
    if hasattr(test_deposit, "utr_number"):
        test_deposit.utr_number = (
            "TEST-"
            + str(int(datetime.utcnow().timestamp()))
        )

    if hasattr(test_deposit, "payment_screenshot"):
        test_deposit.payment_screenshot = None

    db.add(test_deposit)
    db.commit()

    return RedirectResponse(
        "/employee/deposits",
        status_code=303
    )