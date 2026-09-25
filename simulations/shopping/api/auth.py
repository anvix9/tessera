"""
Subway Shopping Simulation - Authentication Module

Adds:
- User registration (email + password)
- Login with JWT token
- Token validation middleware
- User-specific carts and order history
- Password hashing with bcrypt
"""
import jwt
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field


# ── Config ──

JWT_SECRET = "subway-demo-secret-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24


# Simple password hashing (SHA-256 with salt — fine for demo, use bcrypt in production)
def _hash_password(password: str) -> str:
    salt = "subway-salt-demo"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def _verify_password(password: str, password_hash: str) -> bool:
    return _hash_password(password) == password_hash


# ── Config ──

JWT_SECRET = "subway-demo-secret-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24


# ── Models ──

class User(BaseModel):
    id: str
    email: str
    name: str
    password_hash: str
    cart_id: Optional[str] = None
    created_at: str = ""


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    name: str
    email: str
    message: str = ""


class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    cart_id: Optional[str] = None
    order_count: int = 0
    created_at: str = ""


# ── In-Memory User Store ──

USERS: dict[str, User] = {}           # user_id -> User
EMAIL_INDEX: dict[str, str] = {}      # email -> user_id


def seed_users():
    """Create some test users."""
    test_users = [
        ("alice@example.com", "password123", "Alice Johnson"),
        ("bob@example.com", "securepass", "Bob Smith"),
        ("carlos@startup.mx", "hola1234", "Carlos Mendez"),
    ]
    for email, password, name in test_users:
        register_user(email, password, name)


def register_user(email: str, password: str, name: str) -> User:
    """Register a new user."""
    if email.lower() in EMAIL_INDEX:
        raise ValueError(f"Email '{email}' already registered")

    user_id = f"user_{uuid.uuid4().hex[:8]}"
    user = User(
        id=user_id,
        email=email.lower(),
        name=name,
        password_hash=_hash_password(password),
        created_at=datetime.utcnow().isoformat(),
    )
    USERS[user_id] = user
    EMAIL_INDEX[email.lower()] = user_id
    return user


def authenticate_user(email: str, password: str) -> Optional[User]:
    """Verify email and password, return user if valid."""
    email = email.lower()
    user_id = EMAIL_INDEX.get(email)
    if not user_id:
        return None
    user = USERS.get(user_id)
    if not user:
        return None
    if not _verify_password(password, user.password_hash):
        return None
    return user


def get_user_by_id(user_id: str) -> Optional[User]:
    """Get user by ID."""
    return USERS.get(user_id)


# ── JWT Token Management ──

def create_token(user: User) -> str:
    """Create a JWT token for a user."""
    payload = {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_user_from_token(token: str) -> Optional[User]:
    """Extract user from a JWT token."""
    payload = verify_token(token)
    if not payload:
        return None
    return USERS.get(payload.get("user_id"))
