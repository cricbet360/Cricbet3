import re
import secrets
import string

from fastapi import (
    APIRouter,
    Request,
    Form,
    Depends,
)

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from models.user import User
from models.wallet import Wallet

from auth.password import (
    hash_password,
    verify_password,
)


router = APIRouter()

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# REFERRAL CONFIGURATION
# ============================================================

REFERRAL_CODE_PREFIX = "CB"
REFERRAL_CODE_LENGTH = 8

REFERRAL_ALPHABET = (
    string.ascii_uppercase
    + string.digits
)


# ============================================================
# GENERATE UNIQUE REFERRAL CODE
# ============================================================

def generate_referral_code(
    db: Session
):
    while True:

        random_part = "".join(
            secrets.choice(
                REFERRAL_ALPHABET
            )
            for _ in range(
                REFERRAL_CODE_LENGTH
            )
        )

        code = (
            REFERRAL_CODE_PREFIX
            + random_part
        )

        exists = (
            db.query(User.id)
            .filter(
                User.referral_code == code
            )
            .first()
        )

        if not exists:
            return code


# ============================================================
# FIND REFERRER BY REFERRAL CODE
# ============================================================

def get_referrer_by_code(
    db: Session,
    referral_code: str
):

    if not referral_code:
        return None

    normalized_code = (
        referral_code.strip().upper()
    )

    if not normalized_code:
        return None

    return (
        db.query(User)
        .filter(
            User.referral_code == normalized_code
        )
        .first()
    )


# ============================================================
# COMMON REGISTER SESSION CLEANUP
# ============================================================

def clear_registration_session(
    request: Request
):

    session_keys = [
        "registration_username",
        "registration_email",
        "registration_phone",
        "registration_referrer_id",
        "registration_referral_code",
        "terms_accepted",

        # Remove any old OTP-related session values
        # left over from the previous system.
        "phone_verified",
        "phone_otp_session_id",
        "otp_expiry",

        # Old password-reset OTP values
        "password_reset_user_id",
        "password_reset_otp_session_id",
        "password_reset_expiry",
        "password_reset_verified",
    ]

    for key in session_keys:
        request.session.pop(
            key,
            None
        )


# ============================================================
# VALIDATION
# ============================================================

def validate_username(
    username: str
):

    if len(username) < 4:
        return (
            False,
            "Username must contain at least 4 characters."
        )

    if len(username) > 50:
        return (
            False,
            "Username is too long."
        )

    if not re.fullmatch(
        r"[A-Za-z0-9]+",
        username
    ):
        return (
            False,
            "Username can contain letters and numbers only."
        )

    return (
        True,
        ""
    )


def validate_email(
    email: str
):

    email_pattern = (
        r"^[A-Za-z0-9._%+-]+"
        r"@"
        r"[A-Za-z0-9.-]+"
        r"\."
        r"[A-Za-z]{2,}$"
    )

    return bool(
        re.fullmatch(
            email_pattern,
            email
        )
    )


def validate_phone(
    phone: str
):

    phone_pattern = r"^[6-9]\d{9}$"

    return bool(
        re.fullmatch(
            phone_pattern,
            phone
        )
    )


def validate_password(
    password: str
):

    if len(password) < 8:
        return (
            False,
            "Password must contain at least 8 characters."
        )

    if not re.search(
        r"[A-Z]",
        password
    ):
        return (
            False,
            "Password must contain at least one uppercase letter."
        )

    if not re.search(
        r"[a-z]",
        password
    ):
        return (
            False,
            "Password must contain at least one lowercase letter."
        )

    if not re.search(
        r"\d",
        password
    ):
        return (
            False,
            "Password must contain at least one number."
        )

    if not re.search(
        r"[^A-Za-z0-9]",
        password
    ):
        return (
            False,
            "Password must contain at least one special character."
        )

    return (
        True,
        ""
    )


# ============================================================
# REGISTER PAGE
# ============================================================

@router.get("/register")
async def register_page(
    request: Request
):

    referral_code = (
        request.query_params.get(
            "ref",
            ""
        )
        .strip()
        .upper()
    )

    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "referral_code": referral_code
        }
    )


# ============================================================
# REGISTER
#
# IMPORTANT:
# The old endpoint was /register/send-otp.
# We keep that URL so your existing register.html
# continues to work, but it NO LONGER sends OTP.
#
# Also support POST /register.
# ============================================================

@router.post("/register")
@router.post("/register/send-otp")
async def process_registration(

    request: Request,

    username: str = Form(...),

    email: str = Form(...),

    phone: str = Form(...),

    referral_code: str = Form(""),

    db: Session = Depends(get_db),
):

    username = username.strip()

    email = (
        email
        .strip()
        .lower()
    )

    phone = phone.strip()

    referral_code = (
        referral_code
        .strip()
        .upper()
    )


    # ========================================================
    # CLEAR OLD REGISTRATION STATE
    # ========================================================

    request.session.pop(
        "terms_accepted",
        None
    )

    request.session.pop(
        "registration_referrer_id",
        None
    )

    request.session.pop(
        "registration_referral_code",
        None
    )


    # ========================================================
    # USERNAME
    # ========================================================

    valid_username, username_message = (
        validate_username(username)
    )

    if not valid_username:

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "message": username_message,
                "referral_code": referral_code,
            }
        )


    # ========================================================
    # EMAIL
    # ========================================================

    if not validate_email(email):

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "message":
                    "Please enter a valid email address.",
                "referral_code":
                    referral_code,
            }
        )


    # ========================================================
    # PHONE
    # ========================================================

    if not validate_phone(phone):

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "message":
                    "Please enter a valid 10-digit mobile number.",
                "referral_code":
                    referral_code,
            }
        )


    # ========================================================
    # CHECK EXISTING USERNAME
    # ========================================================

    existing_username = (
        db.query(User)
        .filter(
            User.username == username
        )
        .first()
    )

    if existing_username:

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "message":
                    "Username already exists.",
                "referral_code":
                    referral_code,
            }
        )


    # ========================================================
    # CHECK EXISTING EMAIL
    # ========================================================

    existing_email = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if existing_email:

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "message":
                    "Email address is already registered.",
                "referral_code":
                    referral_code,
            }
        )


    # ========================================================
    # CHECK EXISTING PHONE
    # ========================================================

    existing_phone = (
        db.query(User)
        .filter(
            User.phone == phone
        )
        .first()
    )

    if existing_phone:

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "message":
                    "Phone number is already registered.",
                "referral_code":
                    referral_code,
            }
        )


    # ========================================================
    # OPTIONAL REFERRAL CODE
    #
    # Blank referral code:
    #     Continue normally.
    #
    # Entered referral code:
    #     It MUST exist.
    # ========================================================

    referrer = None

    if referral_code:

        if not re.fullmatch(
            r"[A-Z0-9]{4,20}",
            referral_code
        ):

            return templates.TemplateResponse(
                request=request,
                name="register.html",
                context={
                    "message":
                        "Invalid referral code.",
                    "referral_code":
                        referral_code,
                }
            )


        referrer = get_referrer_by_code(
            db,
            referral_code
        )

        if not referrer:

            return templates.TemplateResponse(
                request=request,
                name="register.html",
                context={
                    "message":
                        "Referral code does not exist.",
                    "referral_code":
                        referral_code,
                }
            )


        # Save the referrer temporarily until
        # password creation is completed.

        request.session[
            "registration_referrer_id"
        ] = referrer.id

        request.session[
            "registration_referral_code"
        ] = referrer.referral_code


    # ========================================================
    # SAVE REGISTRATION DATA
    #
    # NO OTP IS SENT HERE.
    # NO PHONE VERIFICATION IS REQUIRED.
    # ========================================================

    request.session[
        "registration_username"
    ] = username

    request.session[
        "registration_email"
    ] = email

    request.session[
        "registration_phone"
    ] = phone


    # ========================================================
    # GO DIRECTLY TO TERMS/DISCLAIMER
    # ========================================================

    return RedirectResponse(
        url="/register/disclaimer",
        status_code=303
    )


# ============================================================
# DISCLAIMER
# ============================================================

@router.get("/register/disclaimer")
async def disclaimer_page(
    request: Request
):

    username = request.session.get(
        "registration_username"
    )

    email = request.session.get(
        "registration_email"
    )

    phone = request.session.get(
        "registration_phone"
    )

    if (
        not username
        or not email
        or not phone
    ):

        return RedirectResponse(
            url="/register",
            status_code=303
        )


    return templates.TemplateResponse(
        request=request,
        name="disclaimer.html",
        context={}
    )


# ============================================================
# ACCEPT DISCLAIMER
# ============================================================

@router.post("/register/disclaimer")
async def accept_disclaimer(

    request: Request,

    accept_terms: str = Form(None),

):

    username = request.session.get(
        "registration_username"
    )

    email = request.session.get(
        "registration_email"
    )

    phone = request.session.get(
        "registration_phone"
    )

    if (
        not username
        or not email
        or not phone
    ):

        return RedirectResponse(
            url="/register",
            status_code=303
        )


    if accept_terms != "yes":

        return templates.TemplateResponse(
            request=request,
            name="disclaimer.html",
            context={
                "message":
                    "You must accept the Terms and Conditions to continue."
            }
        )


    request.session[
        "terms_accepted"
    ] = True


    return RedirectResponse(
        url="/register/create-password",
        status_code=303
    )


# ============================================================
# CREATE PASSWORD PAGE
# ============================================================

@router.get("/register/create-password")
async def create_password_page(
    request: Request
):

    username = request.session.get(
        "registration_username"
    )

    email = request.session.get(
        "registration_email"
    )

    phone = request.session.get(
        "registration_phone"
    )

    terms_accepted = request.session.get(
        "terms_accepted"
    )


    if (
        not username
        or not email
        or not phone
        or not terms_accepted
    ):

        return RedirectResponse(
            url="/register",
            status_code=303
        )


    return templates.TemplateResponse(
        request=request,
        name="create-password.html",
        context={}
    )


# ============================================================
# CREATE USER ACCOUNT
# ============================================================

@router.post("/register/create-password")
async def create_user_account(

    request: Request,

    password: str = Form(...),

    confirm_password: str = Form(...),

    db: Session = Depends(get_db),

):

    # ========================================================
    # REGISTRATION SESSION
    # ========================================================

    username = request.session.get(
        "registration_username"
    )

    email = request.session.get(
        "registration_email"
    )

    phone = request.session.get(
        "registration_phone"
    )

    terms_accepted = request.session.get(
        "terms_accepted"
    )

    referrer_id = request.session.get(
        "registration_referrer_id"
    )

    stored_referral_code = request.session.get(
        "registration_referral_code"
    )


    if (
        not username
        or not email
        or not phone
        or not terms_accepted
    ):

        return RedirectResponse(
            url="/register",
            status_code=303
        )


    # ========================================================
    # PASSWORD MATCH
    # ========================================================

    if password != confirm_password:

        return templates.TemplateResponse(
            request=request,
            name="create-password.html",
            context={
                "message":
                    "Passwords do not match."
            }
        )


    # ========================================================
    # PASSWORD VALIDATION
    # ========================================================

    valid, message = validate_password(
        password
    )

    if not valid:

        return templates.TemplateResponse(
            request=request,
            name="create-password.html",
            context={
                "message": message
            }
        )


    # ========================================================
    # FINAL DUPLICATE CHECKS
    # ========================================================

    if db.query(User).filter(
        User.username == username
    ).first():

        return RedirectResponse(
            url="/register",
            status_code=303
        )


    if db.query(User).filter(
        User.email == email
    ).first():

        return RedirectResponse(
            url="/register",
            status_code=303
        )


    if db.query(User).filter(
        User.phone == phone
    ).first():

        return RedirectResponse(
            url="/register",
            status_code=303
        )


    # ========================================================
    # RE-CHECK REFERRER
    #
    # This prevents a referral relationship from becoming
    # invalid between signup and final account creation.
    # ========================================================

    referrer = None

    if referrer_id:

        referrer = (
            db.query(User)
            .filter(
                User.id == referrer_id
            )
            .first()
        )


        if not referrer:

            return templates.TemplateResponse(
                request=request,
                name="create-password.html",
                context={
                    "message":
                        "The referral code is no longer valid. Please register again."
                }
            )


        if (
            stored_referral_code
            and referrer.referral_code != stored_referral_code
        ):

            return templates.TemplateResponse(
                request=request,
                name="create-password.html",
                context={
                    "message":
                        "The referral code is no longer valid. Please register again."
                }
            )


    # ========================================================
    # GENERATE NEW USER'S OWN REFERRAL CODE
    # ========================================================

    new_referral_code = generate_referral_code(
        db
    )


    # ========================================================
    # CREATE USER
    # ========================================================

    new_user = User(
        username=username,
        email=email,
        phone=phone,
        password=hash_password(
            password
        ),
        referral_code=new_referral_code,

        referred_by_user_id=(
            referrer.id
            if referrer
            else None
        ),

        first_deposit_completed=False,
        referral_bonus_paid=False,
    )


    try:

        db.add(
            new_user
        )

        # Get new_user.id before creating wallet
        db.flush()


        # ====================================================
        # CREATE WALLET
        # ====================================================

        wallet = Wallet(
            user_id=new_user.id,
            balance=0.0,
            exposure=0.0,
        )

        db.add(
            wallet
        )


        # ====================================================
        # COMMIT BOTH USER + WALLET TOGETHER
        # ====================================================

        db.commit()

        db.refresh(
            new_user
        )


    except Exception:

        db.rollback()

        return templates.TemplateResponse(
            request=request,
            name="create-password.html",
            context={
                "message":
                    "Unable to create your account. Please try again."
            }
        )


    # ========================================================
    # CLEAR REGISTRATION SESSION
    # ========================================================

    clear_registration_session(
        request
    )


    # ========================================================
    # LOGIN PAGE
    # ========================================================

    return RedirectResponse(
        url="/login",
        status_code=303
    )


# ============================================================
# LOGIN
# ============================================================

@router.get("/login")
async def login_page(
    request: Request
):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )


@router.post("/login")
async def login_user(

    request: Request,

    username: str = Form(...),

    password: str = Form(...),

    db: Session = Depends(get_db),

):

    username = username.strip()


    user = (
        db.query(User)
        .filter(
            User.username == username
        )
        .first()
    )


    if not user:

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "message":
                    "Invalid username or password."
            }
        )


    if not verify_password(
        password,
        user.password
    ):

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "message":
                    "Invalid username or password."
            }
        )


    # ========================================================
    # LOGIN SESSION
    # ========================================================

    request.session[
        "user_id"
    ] = user.id


    return RedirectResponse(
        url="/dashboard",
        status_code=303
    )


# ============================================================
# FORGOT PASSWORD
#
# NO OTP
# NO PHONE VERIFICATION
# NO PASSWORD RESET FORM
#
# The user is instructed to contact Admin through WhatsApp.
# ============================================================

@router.get("/forgot-password")
async def forgot_password_page(
    request: Request
):

    return templates.TemplateResponse(
        request=request,
        name="forgot-password.html",
        context={}
    )