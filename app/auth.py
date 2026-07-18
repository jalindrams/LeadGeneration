from datetime import datetime, timedelta
from typing import Optional
import uuid
import bcrypt

from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

# --- Helper Functions ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

# Simple in-memory session store for this internal tool
SESSION_STORE = {}

def create_session(user_id: int) -> str:
    session_id = str(uuid.uuid4())
    SESSION_STORE[session_id] = {
        "user_id": user_id,
        "expires_at": datetime.now() + timedelta(days=7)
    }
    return session_id

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in SESSION_STORE:
        return None
    
    session_data = SESSION_STORE[session_id]
    if datetime.now() > session_data["expires_at"]:
        del SESSION_STORE[session_id]
        return None
        
    user = db.query(User).filter(User.id == session_data["user_id"]).first()
    return user

def require_auth(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        # If accessing API, return 401. 
        # For pages, we handle redirecting in the route itself usually,
        # but throwing 401 here is standard API behavior.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user

def require_admin(user: User = Depends(require_auth)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
