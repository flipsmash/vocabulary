#!/usr/bin/env python3
"""
Authentication and User Management System
Handles user authentication, session management, and role-based access control
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from core.database_manager import db_manager
from dataclasses import dataclass
import logging
import os

logger = logging.getLogger(__name__)

# Security configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production-vocab-app-2024")  # TODO: Move to environment variable
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# JWT token bearer
security = HTTPBearer()

@dataclass
class User:
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

class AuthenticationError(Exception):
    """Custom authentication error"""
    pass

class UserManager:
    """Handles user operations and authentication"""

    def __init__(self):
        pass

    def _cursor(self, autocommit: bool = False, dictionary: bool = False):
        return db_manager.get_cursor(autocommit=autocommit, dictionary=dictionary)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        plain_password = plain_password[:72]
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        password = password[:72]
        return pwd_context.hash(password)

    @staticmethod
    def _row_to_user(row: Optional[Dict[str, Any]]) -> Optional[User]:
        if not row:
            return None
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            full_name=row.get("full_name"),
            role=row["role"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login_at=row.get("last_login_at"),
        )

    def get_user_by_username(self, username: str) -> Optional[User]:
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id, username, email, full_name, role, is_active, created_at, last_login_at
                FROM users
                WHERE username = %s AND is_active = TRUE
                """,
                (username,),
            )
            return self._row_to_user(cursor.fetchone())

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id, username, email, full_name, role, is_active, created_at, last_login_at
                FROM users
                WHERE email = %s AND is_active = TRUE
                """,
                (email,),
            )
            return self._row_to_user(cursor.fetchone())

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id, username, email, full_name, role, is_active, created_at, last_login_at
                FROM users
                WHERE id = %s AND is_active = TRUE
                """,
                (user_id,),
            )
            return self._row_to_user(cursor.fetchone())

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id, username, email, full_name, role, is_active, created_at,
                       last_login_at, password_hash
                FROM users
                WHERE username = %s AND is_active = TRUE
                """,
                (username,),
            )
            row = cursor.fetchone()
            if not row or not self.verify_password(password, row["password_hash"]):
                return None

        with self._cursor(autocommit=True) as cursor:
            cursor.execute(
                "UPDATE users SET last_login_at = %s WHERE id = %s",
                (datetime.now(), row["id"]),
            )
        row["last_login_at"] = datetime.now()
        return self._row_to_user(row)

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "user",
    ) -> User:
        password_hash = self.get_password_hash(password)
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT 1 FROM users WHERE username = %s OR email = %s",
                (username, email),
            )
            if cursor.fetchone():
                raise ValueError("Username or email already exists")

        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                INSERT INTO users (username, email, full_name, password_hash, role, is_active, created_at, last_login_at)
                VALUES (%s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id, username, email, full_name, role, is_active, created_at, last_login_at
                """,
                (username, email, full_name, password_hash, role),
            )
            return self._row_to_user(cursor.fetchone())

    def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        updates = []
        values: list[Any] = []

        for field in ["full_name", "email"]:
            if field in kwargs and kwargs[field] is not None:
                updates.append(f"{field} = %s")
                values.append(kwargs[field])

        if kwargs.get("password"):
            updates.append("password_hash = %s")
            values.append(self.get_password_hash(kwargs["password"]))

        if not updates:
            return self.get_user_by_id(user_id)

        updates.append("updated_at = %s")
        values.append(datetime.now())
        values.append(user_id)

        with self._cursor(dictionary=True, autocommit=True) as cursor:
            cursor.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
                values,
            )

        return self.get_user_by_id(user_id)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Dict[str, Any]:
    """Decode JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Initialize user manager
user_manager = UserManager()

# Dependency functions for FastAPI
async def get_current_user(request: Request) -> User:
    """Get current user from JWT token (cookie or header)"""
    token = None
    
    # Try to get token from cookie first
    cookie_token = request.cookies.get("access_token")
    if cookie_token and cookie_token.startswith("Bearer "):
        token = cookie_token[7:]  # Remove "Bearer " prefix
    
    # If no cookie token, try Authorization header
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    user = user_manager.get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user

async def get_current_active_user(request: Request) -> User:
    """Get current active user"""
    current_user = await get_current_user(request)
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_admin_user(request: Request) -> User:
    """Get current admin user - requires admin role"""
    current_user = await get_current_active_user(request)
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

# Optional dependency - returns None if not authenticated
async def get_optional_current_user(request: Request) -> Optional[User]:
    """Get current user if authenticated, None otherwise"""
    try:
        token = None
        
        # Try to get token from cookie first
        cookie_token = request.cookies.get("access_token")
        if cookie_token and cookie_token.startswith("Bearer "):
            token = cookie_token[7:]  # Remove "Bearer " prefix
        
        # If no cookie token, try Authorization header
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]
        
        if not token:
            return None
        
        payload = decode_token(token)
        username: str = payload.get("sub")
        if username is None:
            return None
        
        user = user_manager.get_user_by_username(username)
        return user if user and user.is_active else None
    except:
        return None
