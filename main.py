import os

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
from routers.bets import router as bets_router


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
from routers.password_reset import (
    router as password_reset_router
)

from routers.admin_users import router as admin_users_router

# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="CrickBet"
)


# ============================================================
# SESSION MIDDLEWARE
# ============================================================

#
# SESSION_SECRET      Long random string, set in the server's .env file.
#                     Anyone who knows it can forge login cookies, so it
#                     must never be committed to the code.
#
# SESSION_HTTPS_ONLY  "true" on the live site (HTTPS) so the cookie is
#                     only ever sent over an encrypted connection.
#                     Leave unset/"false" for local http://localhost use.

_INSECURE_DEFAULT_SECRET = "crickbet_super_secret_key_change_this"

SESSION_SECRET = os.getenv(
    "SESSION_SECRET",
    _INSECURE_DEFAULT_SECRET
)

if SESSION_SECRET == _INSECURE_DEFAULT_SECRET:
    print(
        "[SECURITY] SESSION_SECRET is not set - using the insecure "
        "default. Set it in .env before exposing this site publicly."
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=os.getenv(
        "SESSION_HTTPS_ONLY", "false"
    ).strip().lower() in ("1", "true", "yes"),
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

app.include_router(bets_router)

app.include_router(
    password_reset_router
)
app.include_router(admin_users_router)