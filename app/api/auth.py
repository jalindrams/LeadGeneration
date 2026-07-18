from fastapi import APIRouter, Depends, Form, HTTPException, Response, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.models import User
from app.auth import verify_password, create_session, SESSION_STORE

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
def login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/login?error=invalid", status_code=status.HTTP_303_SEE_OTHER)
    
    if not user.is_active:
        return RedirectResponse(url="/login?error=inactive", status_code=status.HTTP_303_SEE_OTHER)

    session_id = create_session(user.id)
    
    # Redirect to calling UI or admin dashboard based on role
    redirect_url = "/calling/admin" if user.role == "admin" else "/calling/"
    
    resp = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(key="session_id", value=session_id, httponly=True, max_age=7*24*60*60)
    return resp

@router.get("/logout")
def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in SESSION_STORE:
        del SESSION_STORE[session_id]
        
    resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie("session_id")
    return resp
