from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db

from models.employee import Employee
from models.deposit_request import DepositRequest
from models.withdrawal_request import WithdrawalRequest
from models.user import User
from models.transaction import Transaction

router = APIRouter(prefix="/employee")

templates = Jinja2Templates(directory="templates")


# =========================================================
# EMPLOYEE AUTH CHECK
# =========================================================

def get_logged_in_employee(
    request: Request,
    db: Session
):
    employee_id = request.session.get("employee_id")

    if not employee_id:
        return None

    employee = db.query(Employee).filter(
        Employee.id == employee_id
    ).first()

    if not employee:
        return None

    if employee.status != "Active":
        return None

    return employee


# =========================================================
# EMPLOYEE DASHBOARD
# =========================================================

@router.get("/dashboard")
async def employee_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):

    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )


    # =====================================================
    # DEPOSIT COUNTS
    # =====================================================

    pending_deposits = db.query(
        DepositRequest
    ).filter(
        DepositRequest.status == "Pending"
    ).count()


    completed_deposits = db.query(
        DepositRequest
    ).filter(
        DepositRequest.status == "Completed"
    ).count()


    # =====================================================
    # WITHDRAWAL COUNTS
    # =====================================================

    pending_withdrawals = db.query(
        WithdrawalRequest
    ).filter(
        WithdrawalRequest.status == "Pending"
    ).count()


    completed_withdrawals = db.query(
        WithdrawalRequest
    ).filter(
        WithdrawalRequest.status == "Completed"
    ).count()


    # =====================================================
    # DASHBOARD
    # =====================================================

    return templates.TemplateResponse(
        "employee/dashboard.html",
        {
            "request": request,

            "employee": employee,

            "pending_deposits": pending_deposits,
            "completed_deposits": completed_deposits,

            "pending_withdrawals": pending_withdrawals,
            "completed_withdrawals": completed_withdrawals,
        }
    )

# =========================================================
# PENDING DEPOSITS
# =========================================================

@router.get("/deposits")
async def employee_deposits(
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
            DepositRequest.created_at.asc()
        )
        .all()
    )

    return templates.TemplateResponse(
        "employee/deposits.html",
        {
            "request": request,
            "employee": employee,
            "deposits": deposits
        }
    )


# =========================================================
# COMPLETE DEPOSIT
# =========================================================

@router.post("/deposits/{deposit_id}/done")
async def complete_deposit(
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

    try:

        # -------------------------------------------------
        # LOCK DEPOSIT
        # -------------------------------------------------

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


        # -------------------------------------------------
        # PREVENT DOUBLE PROCESSING
        # -------------------------------------------------

        if deposit.status != "Pending":
            return RedirectResponse(
                "/employee/deposits",
                status_code=303
            )


        # -------------------------------------------------
        # LOCK USER
        # -------------------------------------------------

        user = (
            db.query(User)
            .filter(
                User.id == deposit.user_id
            )
            .with_for_update()
            .first()
        )

        if not user:
            db.rollback()

            return RedirectResponse(
                "/employee/deposits",
                status_code=303
            )


        # -------------------------------------------------
        # STORE OLD BALANCE
        # -------------------------------------------------

        balance_before = user.balance


        # -------------------------------------------------
        # ADD DEPOSIT TO USER BALANCE
        # -------------------------------------------------

        user.balance = (
            user.balance + deposit.amount
        )


        # -------------------------------------------------
        # MARK DEPOSIT COMPLETED
        # -------------------------------------------------

        deposit.status = "Completed"

        deposit.processed_by = employee.id

        deposit.completed_at = datetime.utcnow()


        # -------------------------------------------------
        # CREATE TRANSACTION RECORD
        # -------------------------------------------------

        transaction = Transaction(
            user_id=user.id,
            amount=deposit.amount,
            transaction_type="Deposit",
            status="Completed",
            reference_type="DepositRequest",
            reference_id=deposit.id,
            description=(
                f"Deposit approved - "
                f"UTR {deposit.utr_number}"
            )
        )

        db.add(transaction)


        # -------------------------------------------------
        # COMMIT
        # -------------------------------------------------

        db.commit()


        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )


    except Exception:

        db.rollback()

        return RedirectResponse(
            "/employee/deposits",
            status_code=303
        )


# =========================================================
# CREATE TEMPORARY TEST DEPOSIT
# =========================================================

@router.get("/test/create-deposit")
async def create_test_deposit(
    request: Request,
    db: Session = Depends(get_db)
):

    employee = get_logged_in_employee(request, db)

    if not employee:
        return RedirectResponse(
            "/employee/login",
            status_code=303
        )

    # Get the first existing user
    user = db.query(User).first()

    if not user:
        return RedirectResponse(
            "/employee/dashboard",
            status_code=303
        )

    # Create temporary pending deposit
    test_deposit = DepositRequest(
        user_id=user.id,
        amount=500.00,
        utr_number="TEST-DEPOSIT-001",
        payment_screenshot="test-payment.png",
        status="Pending"
    )

    db.add(test_deposit)
    db.commit()

    return RedirectResponse(
        "/employee/deposits",
        status_code=303
    )