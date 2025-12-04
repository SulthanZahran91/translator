"""FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import Settings, get_settings
from backend.core.database import get_db
from backend.core.storage import LocalStorage, get_storage

# Type aliases for dependency injection
SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]
StorageDep = Annotated[LocalStorage, Depends(get_storage)]

