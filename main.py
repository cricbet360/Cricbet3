from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


# ============================================================
# DATABASE
# ============================================================

from database.database import Base, engine


# ============================================================
# MODELS
# ============================================================

from models.user import User
from models.wallet import Wallet
from models.transaction import Transaction
from models.match import Match
from models.bet import Bet
from models.employee import Employee
from models.admin import Admin
from models.deposit_request import DepositRequest
from models.withdrawal_request import WithdrawalRequest


# ============================================================
# AUTH ROUTERS
# ============================================================

from auth.session import router as session_router
from auth.routes import router as auth_router


# ============================================================
# MAIN USER ROUTERS
# ============================================================

from routers.dashboard import router as dashboard_router
from routers.wallet import router as wallet_router
from routers.profile import router as profile_router
from routers.account import router as account_router
from routers.staff_balance import router as staff_balance_router
from routers.wallet_transactions import (
    router as wallet_transactions_router
)


# ============================================================
# CRICKET / PROEXCH ROUTERS
# ============================================================

from routers.proexch import router as proexch_router
from routers.cricket_api import router as cricket_api_router


# ============================================================
# ADMIN ROUTERS
# ============================================================

from admin.auth import router as admin_auth_router
from admin.routes import router as admin_router


# ============================================================
# EMPLOYEE ROUTERS
# ============================================================

from employee.auth import (
    router as employee_auth_router
)

from employee.routes import (
    router as employee_router
)


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="CrickBet"
)


# ============================================================
# SESSION MIDDLEWARE
# ============================================================

app.add_middleware(
    SessionMiddleware,
    secret_key="crickbet_super_secret_key_change_this"
)


# ============================================================
# STATIC FILES
# ============================================================

app.mount(
    "/static",
    StaticFiles(
        directory="static"
    ),
    name="static"
)


# ============================================================
# JINJA TEMPLATES
# ============================================================

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# HOME
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
async def home(
    request: Request
):

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "user": None
        }
    )


# ============================================================
# CREATE DATABASE TABLES
# ============================================================

Base.metadata.create_all(
    bind=engine
)


# ============================================================
# AUTH ROUTERS
# ============================================================

app.include_router(
    auth_router
)

app.include_router(
    session_router
)


# ============================================================
# USER DASHBOARD / WALLET
# ============================================================

app.include_router(
    dashboard_router
)

app.include_router(
    wallet_router
)

app.include_router(
    profile_router
)

app.include_router(
    account_router
)

app.include_router(
    staff_balance_router
)

app.include_router(
    wallet_transactions_router
)


# ============================================================
# ADMIN
# ============================================================

app.include_router(
    admin_auth_router
)

app.include_router(
    admin_router
)


# ============================================================
# EMPLOYEE
# ============================================================

app.include_router(
    employee_auth_router
)

app.include_router(
    employee_router
)


# ============================================================
# OLD / EXISTING PROEXCH ROUTER
# ============================================================

app.include_router(
    proexch_router
)


# ============================================================
# NEW CRICKET API ROUTER
#
# Provides:
#
# GET /api/cricket/matches
#
# ============================================================

app.include_router(
    cricket_api_router
)