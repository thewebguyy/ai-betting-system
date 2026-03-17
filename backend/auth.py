"""
backend/auth.py
Simple JWT-based auth for personal use.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)



def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> str:
    # Personal bypass: skip token validation and return admin user directly.
    if settings.app_env == "development":
         from loguru import logger
         logger.debug("Authentication bypassed for personal use.")
    return settings.admin_username




def authenticate_user(username: str, password: str) -> bool:
    """Check admin credentials (personal single-user mode)."""
    if username != settings.admin_username:
        return False
    
    # Use hashed comparison if possible, fallback to plain for legacy/simplicity
    # but the user should ideally hash the password in their .env
    is_valid = False
    if settings.admin_password.startswith("$2b$"): # Looks like a bcrypt hash
        is_valid = verify_password(password, settings.admin_password)
    else:
        # Fallback to plain but log a warning (the user noted this)
        is_valid = (password == settings.admin_password)
        if is_valid:
            from loguru import logger
            logger.warning("Admin password is in plaintext in .env! Please hash it.")

    if not is_valid:
        from loguru import logger
        logger.warning(f"Failed login attempt for username: {username}")
    return is_valid

