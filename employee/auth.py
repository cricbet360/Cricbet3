from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from models.employee import Employee
from auth.password import verify_password


router = APIRouter(
    prefix="/employee"
)

templates = Jinja2Templates(
    directory="templates"
)


# =========================================================
# EMPLOYEE LOGIN PAGE
# =========================================================

@router.get("/login")
async def employee_login_page(
    request: Request
):

    # If already logged in, go directly to dashboard
    employee_id = request.session.get("employee_id")

    if employee_id:

        return RedirectResponse(
            "/employee/dashboard",
            status_code=303
        )

    return templates.TemplateResponse(
        "employee/login.html",
        {
            "request": request
        }
    )


# =========================================================
# EMPLOYEE LOGIN
# =========================================================

@router.post("/login")
async def employee_login(
    request: Request,
    employee_id: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):

    employee_id = employee_id.strip()

    employee = db.query(Employee).filter(
        Employee.employee_id == employee_id
    ).first()

    # Invalid employee ID
    if not employee:

        return templates.TemplateResponse(
            "employee/login.html",
            {
                "request": request,
                "message": "Invalid employee ID or password."
            }
        )

    # Inactive employee cannot login
    if employee.status != "Active":

        return templates.TemplateResponse(
            "employee/login.html",
            {
                "request": request,
                "message": "This employee account is inactive."
            }
        )

    # Verify password
    if not verify_password(
        password,
        employee.password
    ):

        return templates.TemplateResponse(
            "employee/login.html",
            {
                "request": request,
                "message": "Invalid employee ID or password."
            }
        )

    # Clear any previous session
    request.session.clear()

    # Store employee authentication
    request.session["employee_id"] = employee.id

    return RedirectResponse(
        "/employee/dashboard",
        status_code=303
    )


# =========================================================
# EMPLOYEE LOGOUT
# =========================================================

@router.get("/logout")
async def employee_logout(
    request: Request
):

    request.session.clear()

    return RedirectResponse(
        "/employee/login",
        status_code=303
    )