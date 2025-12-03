"""Authentication API routes."""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import DbSessionDep, SettingsDep
from backend.api.schemas.auth import (
    MessageResponse,
    TokenRefresh,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from backend.models.user import User


router = APIRouter(prefix="/auth", tags=["Authentication"])

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


import hashlib
import bcrypt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    # Pre-hash with SHA-256 to bypass bcrypt's 72-byte limit
    password_hash = hashlib.sha256(plain_password.encode()).hexdigest()
    # bcrypt.checkpw requires bytes
    return bcrypt.checkpw(password_hash.encode(), hashed_password.encode())


def hash_password(password: str) -> str:
    """Hash a password."""
    # Pre-hash with SHA-256 to bypass bcrypt's 72-byte limit
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    # bcrypt.hashpw returns bytes, we need string for DB
    return bcrypt.hashpw(password_hash.encode(), bcrypt.gensalt()).decode()


def create_access_token(
    data: dict,
    settings: SettingsDep,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire, "type": "access"})
    
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(
    data: dict,
    settings: SettingsDep,
) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Get a user by email."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    """Get a user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSessionDep,
    settings: SettingsDep,
) -> User:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if user_id is None:
            raise credentials_exception
        if token_type != "access":
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception
    
    return user


# Dependency for current user
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: DbSessionDep,
) -> User:
    """Register a new user."""
    # Check if email already exists
    existing = await get_user_by_email(db, user_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Create user
    user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        name=user_data.name,
    )
    db.add(user)
    await db.flush()
    
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Login and get access/refresh tokens.
    
    Authenticates against the Upstream LLM service.
    """
    # 1. Authenticate with Upstream LLM
    from backend.translation.llm_client import UpstreamLLMClient
    llm_client = UpstreamLLMClient()
    
    try:
        auth_data = await llm_client.authenticate(form_data.username, form_data.password)
        upstream_token = auth_data.get("token")
        if not upstream_token:
            raise ValueError("No token returned from upstream")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Upstream authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Find or Create Local User
    user = await get_user_by_email(db, form_data.username)
    
    if not user:
        # Auto-register if not exists (since they passed upstream auth)
        user = User(
            email=form_data.username,
            password_hash=hash_password(form_data.password), # Store hash for local fallback/consistency
            name=form_data.username.split("@")[0],
            upstream_token=upstream_token,
            upstream_password=form_data.password # Store plain for re-auth (per requirements)
        )
        db.add(user)
    else:
        # Update existing user's upstream credentials
        user.upstream_token = upstream_token
        user.upstream_password = form_data.password
        # Also update local password hash to keep in sync
        user.password_hash = hash_password(form_data.password)
        db.add(user)
    
    await db.commit()
    await db.refresh(user)
    
    # 3. Issue Local Tokens
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        settings=settings,
    )
    refresh_token = create_refresh_token(
        data={"sub": user.id},
        settings=settings,
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    token_data: TokenRefresh,
    db: DbSessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Refresh access token using refresh token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
    )
    
    try:
        payload = jwt.decode(
            token_data.refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if user_id is None or token_type != "refresh":
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception
    
    # Create new tokens
    new_access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        settings=settings,
    )
    new_refresh_token = create_refresh_token(
        data={"sub": user.id},
        settings=settings,
    )
    
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: CurrentUserDep,
) -> User:
    """Get current user info."""
    return current_user

