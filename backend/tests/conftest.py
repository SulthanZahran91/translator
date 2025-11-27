"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api.main import app
from backend.core.config import Settings, get_settings
from backend.core.database import Base, get_db
from backend.core.storage import LocalStorage

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///./storage/db/test.db"


def get_test_settings() -> Settings:
    """Get settings configured for testing."""
    return Settings(
        database_url=TEST_DATABASE_URL,
        debug=True,
        secret_key="test-secret-key",
        storage_path=Path("./storage/test"),
    )


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Provide test settings."""
    settings = get_test_settings()
    settings.ensure_directories()
    return settings


@pytest_asyncio.fixture(scope="function")
async def test_engine(test_settings: Settings) -> Any:
    """Create a test database engine."""
    engine = create_async_engine(
        test_settings.database_url,
        echo=False,
        future=True,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine: Any) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for tests."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(
    test_settings: Settings,
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async test client."""
    
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session
    
    def override_get_settings() -> Settings:
        return test_settings
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
def sync_client(test_settings: Settings) -> Generator[TestClient, None, None]:
    """Provide a synchronous test client."""
    
    def override_get_settings() -> Settings:
        return test_settings
    
    app.dependency_overrides[get_settings] = override_get_settings
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear()


@pytest.fixture
def test_storage(test_settings: Settings) -> LocalStorage:
    """Provide a test storage instance."""
    storage = LocalStorage()
    storage.settings = test_settings
    return storage


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"

