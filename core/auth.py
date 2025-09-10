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
import mysql.connector
from .config import get_db_config
from dataclasses import dataclass
import logging
import os

logger = logging.getLogger(__name__)

# Security configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production-vocab-app-2024")  # TODO: Move to environment variable
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
        self.config = get_db_config()
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at, last_login_at "
                "FROM users WHERE username = %s AND is_active = TRUE",
                (username,)
            )
            result = cursor.fetchone()
            
            if result:
                return User(
                    id=result[0],
                    username=result[1],
                    email=result[2],
                    full_name=result[3],
                    role=result[4],
                    is_active=result[5],
                    created_at=result[6],
                    last_login_at=result[7]
                )
            return None
        finally:
            cursor.close()
            conn.close()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at, last_login_at "
                "FROM users WHERE email = %s AND is_active = TRUE",
                (email,)
            )
            result = cursor.fetchone()
            
            if result:
                return User(
                    id=result[0],
                    username=result[1],
                    email=result[2],
                    full_name=result[3],
                    role=result[4],
                    is_active=result[5],
                    created_at=result[6],
                    last_login_at=result[7]
                )
            return None
        finally:
            cursor.close()
            conn.close()
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at, last_login_at "
                "FROM users WHERE id = %s AND is_active = TRUE",
                (user_id,)
            )
            result = cursor.fetchone()
            
            if result:
                return User(
                    id=result[0],
                    username=result[1],
                    email=result[2],
                    full_name=result[3],
                    role=result[4],
                    is_active=result[5],
                    created_at=result[6],
                    last_login_at=result[7]
                )
            return None
        finally:
            cursor.close()
            conn.close()
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username/password"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get user with password hash
            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at, "
                "last_login_at, password_hash FROM users WHERE username = %s AND is_active = TRUE",
                (username,)
            )
            result = cursor.fetchone()
            
            if not result:
                return None
            
            # Verify password
            if not self.verify_password(password, result[8]):  # result[8] is password_hash
                return None
            
            # Update last login
            cursor.execute(
                "UPDATE users SET last_login_at = %s WHERE id = %s",
                (datetime.now(), result[0])
            )
            conn.commit()
            
            return User(
                id=result[0],
                username=result[1],
                email=result[2],
                full_name=result[3],
                role=result[4],
                is_active=result[5],
                created_at=result[6],
                last_login_at=datetime.now()
            )
        finally:
            cursor.close()
            conn.close()
    
    def create_user(self, username: str, email: str, password: str, 
                   full_name: Optional[str] = None, role: str = "user") -> User:
        """Create a new user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if username or email already exists
            cursor.execute(
                "SELECT username FROM users WHERE username = %s OR email = %s",
                (username, email)
            )
            if cursor.fetchone():
                raise ValueError("Username or email already exists")
            
            # Hash password and create user
            password_hash = self.get_password_hash(password)
            
            cursor.execute(
                """INSERT INTO users (username, email, full_name, password_hash, role) 
                   VALUES (%s, %s, %s, %s, %s)""",
                (username, email, full_name, password_hash, role)
            )
            conn.commit()
            
            # Get the created user
            user_id = cursor.lastrowid
            return self.get_user_by_id(user_id)
        finally:
            cursor.close()
            conn.close()
    
    def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Build dynamic update query
            updates = []
            values = []
            
            for field in ['full_name', 'email']:
                if field in kwargs and kwargs[field] is not None:
                    updates.append(f"{field} = %s")
                    values.append(kwargs[field])
            
            if 'password' in kwargs and kwargs['password']:
                updates.append("password_hash = %s")
                values.append(self.get_password_hash(kwargs['password']))
            
            if not updates:
                return self.get_user_by_id(user_id)
            
            updates.append("updated_at = %s")
            values.append(datetime.now())
            values.append(user_id)
            
            cursor.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
                values
            )
            conn.commit()
            
            return self.get_user_by_id(user_id)
        finally:
            cursor.close()
            conn.close()

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