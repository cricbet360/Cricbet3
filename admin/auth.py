from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from models.admin import Admin
from auth.password import verify_password

router = APIRouter(prefix="/admin")

templates = Jinja2Templates(directory="templates")


@router.get("/login")
async def admin_login_page(request: Request):
    return templates.TemplateResponse(
        "admin/login.html",
        {
            "request": request
        }
    )


@router.post("/login")
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):

    admin = db.query(Admin).filter(
        Admin.username == username
    ).first()

    if not admin:
        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request,
                "message": "Invalid username or password."
            }
        )

    if not verify_password(password, admin.password):
        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request,
                "message": "Invalid username or password."
            }
        )

    request.session["admin_id"] = admin.id

    return RedirectResponse(
        "/admin/dashboard",
        status_code=303
    )