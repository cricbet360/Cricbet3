import re
import requests

from datetime import datetime, timedelta

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
# 2FACTOR CONFIGURATION
# ============================================================

TWO_FACTOR_API_KEY = "41a40f18-a83d-11f1-9cb1-0200cd936042"

OTP_TEMPLATE_NAME = "OTP1"


# ============================================================
# 2FACTOR OTP FUNCTIONS
# ============================================================

def send_phone_otp_api(phone: str):

    # Add Indian country code
    formatted_phone = f"+91{phone}"

    url = (
        f"https://2factor.in/API/V1/"
        f"{TWO_FACTOR_API_KEY}/SMS/"
        f"{formatted_phone}/AUTOGEN2/"
        f"{OTP_TEMPLATE_NAME}"
    )

    try:

        response = requests.get(
            url,
            timeout=30
        )

        data = response.json()

        if data.get("Status") == "Success":

            return (
                True,
                data.get("Details")
            )

        return (
            False,
            data.get("Details", "Unable to send OTP.")
        )

    except requests.RequestException:

        return (
            False,
            "Unable to connect to OTP service."
        )

    except ValueError:

        return (
            False,
            "Invalid response from OTP service."
        )


def verify_phone_otp_api(
    otp_session_id: str,
    otp: str
):

    url = (
        f"https://2factor.in/API/V1/"
        f"{TWO_FACTOR_API_KEY}/SMS/VERIFY/"
        f"{otp_session_id}/"
        f"{otp}"
    )

    try:

        response = requests.get(
            url,
            timeout=15
        )

        data = response.json()

        status = data.get(
            "Status",
            ""
        )

        details = data.get(
            "Details",
            ""
        )

        # Different API responses may vary.
        # "Success" is normally treated as verified.
        if (
            status.lower() == "success"
            or details.lower() == "otp matched"
        ):

            return (
                True,
                details
            )

        return (
            False,
            details
            or "Invalid OTP."
        )

    except requests.RequestException:

        return (
            False,
            "Unable to connect to OTP verification service."
        )

    except ValueError:

        return (
            False,
            "Invalid response from OTP service."
        )


# ============================================================
# VALIDATION FUNCTIONS
# ============================================================

def validate_email(email: str):

    email_pattern = (
        r"^[A-Za-z0-9._%+-]+"
        r"@"
        r"[A-Za-z0-9.-]+"
        r"\."
        r"[A-Za-z]{2,}$"
    )

    return bool(
        re.match(
            email_pattern,
            email
        )
    )


def validate_phone(phone: str):

    phone_pattern = r"^[6-9]\d{9}$"

    return bool(
        re.match(
            phone_pattern,
            phone
        )
    )


def validate_password(password: str):

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

    return templates.TemplateResponse(

        request=request,

        name="register.html",

        context={}

    )


# ============================================================
# SEND PHONE OTP
# ============================================================

@router.post("/register/send-otp")
async def send_registration_otp(

    request: Request,

    username: str = Form(...),

    email: str = Form(...),

    phone: str = Form(...),

    db: Session = Depends(get_db),

):

    username = username.strip()

    email = email.strip().lower()

    phone = phone.strip()


    # --------------------------------------------------------
    # USERNAME VALIDATION
    # --------------------------------------------------------

    if len(username) < 3:

        return templates.TemplateResponse(

            request=request,

            name="register.html",

            context={

                "message":
                    "Username must contain at least 3 characters."

            }

        )


    # --------------------------------------------------------
    # EMAIL VALIDATION
    #
    # Email is still collected, but NO OTP is sent to email.
    # --------------------------------------------------------

    if not validate_email(email):

        return templates.TemplateResponse(

            request=request,

            name="register.html",

            context={

                "message":
                    "Please enter a valid email address."

            }

        )


    # --------------------------------------------------------
    # PHONE VALIDATION
    # --------------------------------------------------------

    if not validate_phone(phone):

        return templates.TemplateResponse(

            request=request,

            name="register.html",

            context={

                "message":
                    "Please enter a valid 10-digit mobile number."

            }

        )


    # --------------------------------------------------------
    # CHECK EXISTING USERNAME
    # --------------------------------------------------------

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
                    "Username already exists."

            }

        )


    # --------------------------------------------------------
    # CHECK EXISTING EMAIL
    # --------------------------------------------------------

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
                    "Email address is already registered."

            }

        )


    # --------------------------------------------------------
    # CHECK EXISTING PHONE
    # --------------------------------------------------------

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
                    "Phone number is already registered."

            }

        )


    # --------------------------------------------------------
    # SEND OTP USING 2FACTOR
    # --------------------------------------------------------

    otp_sent, result = send_phone_otp_api(
        phone
    )


    if not otp_sent:

        return templates.TemplateResponse(

            request=request,

            name="register.html",

            context={

                "message":
                    f"Unable to send OTP: {result}"

            }

        )


    # --------------------------------------------------------
    # SAVE TEMPORARY REGISTRATION DATA
    # --------------------------------------------------------

    request.session[
        "registration_username"
    ] = username

    request.session[
        "registration_email"
    ] = email

    request.session[
        "registration_phone"
    ] = phone


    # Save the 2Factor OTP session ID.
    request.session[
        "phone_otp_session_id"
    ] = result


    # OTP expiry for your local session.
    expiry_time = (
        datetime.now()
        + timedelta(minutes=10)
    )


    request.session[
        "otp_expiry"
    ] = expiry_time.isoformat()


    return RedirectResponse(

        url="/register/verify-otp",

        status_code=303

    )


# ============================================================
# OTP VERIFICATION PAGE
# ============================================================

@router.get("/register/verify-otp")
async def verify_otp_page(

    request: Request

):

    registration_phone = request.session.get(

        "registration_phone"

    )


    otp_session_id = request.session.get(

        "phone_otp_session_id"

    )


    if (

        not registration_phone

        or not otp_session_id

    ):

        return RedirectResponse(

            url="/register",

            status_code=303

        )


    return templates.TemplateResponse(

        request=request,

        name="verify-otp.html",

        context={

            "phone":
                registration_phone

        }

    )


# ============================================================
# VERIFY PHONE OTP USING 2FACTOR
# ============================================================

@router.post("/register/verify-otp")
async def verify_registration_otp(

    request: Request,

    phone_otp: str = Form(...),

):

    otp_session_id = request.session.get(

        "phone_otp_session_id"

    )


    expiry_string = request.session.get(

        "otp_expiry"

    )


    if (

        not otp_session_id

        or not expiry_string

    ):

        return RedirectResponse(

            url="/register",

            status_code=303

        )


    # --------------------------------------------------------
    # CHECK EXPIRY
    # --------------------------------------------------------

    expiry_time = datetime.fromisoformat(

        expiry_string

    )


    if datetime.now() > expiry_time:

        request.session.pop(

            "phone_otp_session_id",

            None

        )


        return templates.TemplateResponse(

            request=request,

            name="verify-otp.html",

            context={

                "message":
                    "OTP has expired. Please register again.",

                "phone":
                    request.session.get(
                        "registration_phone"
                    )

            }

        )


    # --------------------------------------------------------
    # VERIFY WITH 2FACTOR
    # --------------------------------------------------------

    otp_verified, result = verify_phone_otp_api(

        otp_session_id,

        phone_otp.strip()

    )


    if not otp_verified:

        return templates.TemplateResponse(

            request=request,

            name="verify-otp.html",

            context={

                "message":
                    "Invalid OTP. Please try again.",

                "phone":
                    request.session.get(
                        "registration_phone"
                    )

            }

        )


    # --------------------------------------------------------
    # MARK PHONE AS VERIFIED
    # --------------------------------------------------------

    request.session[
        "phone_verified"
    ] = True


    # Remove OTP session information

    request.session.pop(

        "phone_otp_session_id",

        None

    )


    request.session.pop(

        "otp_expiry",

        None

    )


    # Continue to disclaimer

    return RedirectResponse(

        url="/register/disclaimer",

        status_code=303

    )


# ============================================================
# DISCLAIMER PAGE
# ============================================================

@router.get("/register/disclaimer")
async def disclaimer_page(

    request: Request

):

    phone_verified = request.session.get(

        "phone_verified"

    )


    if not phone_verified:

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

    phone_verified = request.session.get(

        "phone_verified"

    )


    if not phone_verified:

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

    phone_verified = request.session.get(

        "phone_verified"

    )


    terms_accepted = request.session.get(

        "terms_accepted"

    )


    if (

        not phone_verified

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
# CREATE FINAL USER ACCOUNT
# ============================================================

@router.post("/register/create-password")
async def create_user_account(

    request: Request,

    password: str = Form(...),

    confirm_password: str = Form(...),

    db: Session = Depends(get_db),

):

    phone_verified = request.session.get(

        "phone_verified"

    )


    terms_accepted = request.session.get(

        "terms_accepted"

    )


    if (

        not phone_verified

        or not terms_accepted

    ):

        return RedirectResponse(

            url="/register",

            status_code=303

        )


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


    # --------------------------------------------------------
    # CONFIRM PASSWORD
    # --------------------------------------------------------

    if password != confirm_password:

        return templates.TemplateResponse(

            request=request,

            name="create-password.html",

            context={

                "message":
                    "Passwords do not match."

            }

        )


    # --------------------------------------------------------
    # VALIDATE PASSWORD
    # --------------------------------------------------------

    password_valid, password_message = (

        validate_password(
            password
        )

    )


    if not password_valid:

        return templates.TemplateResponse(

            request=request,

            name="create-password.html",

            context={

                "message":
                    password_message

            }

        )


    # --------------------------------------------------------
    # FINAL DUPLICATE CHECK
    # --------------------------------------------------------

    existing_user = (

        db.query(User)

        .filter(
            User.username == username
        )

        .first()

    )


    if existing_user:

        return RedirectResponse(

            url="/register",

            status_code=303

        )


    existing_email = (

        db.query(User)

        .filter(
            User.email == email
        )

        .first()

    )


    if existing_email:

        return RedirectResponse(

            url="/register",

            status_code=303

        )


    existing_phone = (

        db.query(User)

        .filter(
            User.phone == phone
        )

        .first()

    )


    if existing_phone:

        return RedirectResponse(

            url="/register",

            status_code=303

        )


    # --------------------------------------------------------
    # CREATE USER
    # --------------------------------------------------------

    new_user = User(

        username=username,

        email=email,

        phone=phone,

        password=hash_password(
            password
        ),

    )


    db.add(
        new_user
    )


    db.commit()


    db.refresh(
        new_user
    )


    # --------------------------------------------------------
    # CREATE WALLET
    # --------------------------------------------------------

    wallet = Wallet(

        user_id=new_user.id,

        balance=0.0,

        exposure=0.0,

    )


    db.add(
        wallet
    )


    db.commit()


    # --------------------------------------------------------
    # CLEAR REGISTRATION SESSION
    # --------------------------------------------------------

    session_keys = [

        "registration_username",

        "registration_email",

        "registration_phone",

        "phone_verified",

        "terms_accepted",

        "phone_otp_session_id",

        "otp_expiry",

    ]


    for key in session_keys:

        request.session.pop(

            key,

            None

        )


    return RedirectResponse(

        url="/login",

        status_code=303

    )


# ============================================================
# LOGIN PAGE
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


# ============================================================
# LOGIN USER
# ============================================================

@router.post("/login")
async def login_user(

    request: Request,

    username: str = Form(...),

    password: str = Form(...),

    db: Session = Depends(get_db),

):

    user = (

        db.query(User)

        .filter(

            User.username == username.strip()

        )

        .first()

    )


    if user is None:

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

        user.password,

    ):

        return templates.TemplateResponse(

            request=request,

            name="login.html",

            context={

                "message":
                    "Invalid username or password."

            }

        )


    request.session[
        "user_id"
    ] = user.id


    return RedirectResponse(

        url="/dashboard",

        status_code=303

    )


# ============================================================
# FORGOT PASSWORD
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


@router.post("/forgot-password")
async def send_password_reset_otp(

    request: Request,

    phone: str = Form(...),

    db: Session = Depends(get_db)

):

    phone = phone.strip()


    user = (

        db.query(User)

        .filter(

            User.phone == phone

        )

        .first()

    )


    if not user:

        return templates.TemplateResponse(

            request=request,

            name="forgot-password.html",

            context={

                "message":
                    "No account was found with this phone number.",

                "phone":
                    phone,

            }

        )


    otp_sent, result = send_phone_otp_api(

        phone

    )


    if not otp_sent:

        return templates.TemplateResponse(

            request=request,

            name="forgot-password.html",

            context={

                "message":
                    f"Unable to send OTP: {result}",

                "phone":
                    phone,

            }

        )


    request.session[
        "password_reset_user_id"
    ] = user.id


    request.session[
        "password_reset_otp_session_id"
    ] = result


    expiry = (

        datetime.now()

        + timedelta(minutes=10)

    )


    request.session[
        "password_reset_expiry"
    ] = expiry.isoformat()


    return RedirectResponse(

        url="/verify-reset-otp",

        status_code=303

    )


# ============================================================
# VERIFY RESET OTP PAGE
# ============================================================

@router.get("/verify-reset-otp")
async def verify_reset_otp_page(

    request: Request

):

    user_id = request.session.get(

        "password_reset_user_id"

    )


    if not user_id:

        return RedirectResponse(

            url="/forgot-password",

            status_code=303

        )


    return templates.TemplateResponse(

        request=request,

        name="verify-reset-otp.html",

        context={}

    )


# ============================================================
# VERIFY PASSWORD RESET OTP
# ============================================================

@router.post("/verify-reset-otp")
async def verify_reset_otp(

    request: Request,

    otp: str = Form(...)

):

    otp_session_id = request.session.get(

        "password_reset_otp_session_id"

    )


    expiry_string = request.session.get(

        "password_reset_expiry"

    )


    user_id = request.session.get(

        "password_reset_user_id"

    )


    if (

        not otp_session_id

        or not expiry_string

        or not user_id

    ):

        return RedirectResponse(

            url="/forgot-password",

            status_code=303

        )


    expiry = datetime.fromisoformat(

        expiry_string

    )


    if datetime.now() > expiry:

        return templates.TemplateResponse(

            request=request,

            name="verify-reset-otp.html",

            context={

                "message":
                    "OTP has expired. Please request a new OTP."

            }

        )


    otp_verified, result = verify_phone_otp_api(

        otp_session_id,

        otp.strip()

    )


    if not otp_verified:

        return templates.TemplateResponse(

            request=request,

            name="verify-reset-otp.html",

            context={

                "message":
                    "Invalid OTP. Please try again."

            }

        )


    request.session[
        "password_reset_verified"
    ] = True


    request.session.pop(

        "password_reset_otp_session_id",

        None

    )


    request.session.pop(

        "password_reset_expiry",

        None

    )


    return RedirectResponse(

        url="/reset-password",

        status_code=303

    )


# ============================================================
# RESET PASSWORD PAGE
# ============================================================

@router.get("/reset-password")
async def reset_password_page(

    request: Request

):

    verified = request.session.get(

        "password_reset_verified"

    )


    if not verified:

        return RedirectResponse(

            url="/forgot-password",

            status_code=303

        )


    return templates.TemplateResponse(

        request=request,

        name="reset-password.html",

        context={}

    )


# ============================================================
# RESET PASSWORD
# ============================================================

@router.post("/reset-password")
async def reset_password(

    request: Request,

    password: str = Form(...),

    confirm_password: str = Form(...),

    db: Session = Depends(get_db)

):

    verified = request.session.get(

        "password_reset_verified"

    )


    user_id = request.session.get(

        "password_reset_user_id"

    )


    if not verified or not user_id:

        return RedirectResponse(

            url="/forgot-password",

            status_code=303

        )


    valid, message = validate_password(

        password

    )


    if not valid:

        return templates.TemplateResponse(

            request=request,

            name="reset-password.html",

            context={

                "message":
                    message

            }

        )


    if password != confirm_password:

        return templates.TemplateResponse(

            request=request,

            name="reset-password.html",

            context={

                "message":
                    "Passwords do not match."

            }

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

            url="/forgot-password",

            status_code=303

        )


    user.password = hash_password(

        password

    )


    db.commit()


    request.session.pop(

        "password_reset_user_id",

        None

    )


    request.session.pop(

        "password_reset_verified",

        None

    )


    return RedirectResponse(

        url="/login",

        status_code=303

    )