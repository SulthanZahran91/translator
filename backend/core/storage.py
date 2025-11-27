"""Local file storage abstraction (upgradeable to S3/MinIO)."""

import shutil
import uuid
from pathlib import Path

import aiofiles

from backend.core.config import get_settings


class LocalStorage:
    """Local filesystem storage implementation."""
    
    def __init__(self) -> None:
        self.settings = get_settings()
    
    def _resolve_path(self, category: str, filename: str) -> Path:
        """Get full path for a file in a category."""
        base_dirs = {
            "uploads": self.settings.uploads_dir,
            "outputs": self.settings.outputs_dir,
            "checkpoints": self.settings.checkpoints_dir,
            "temp": self.settings.temp_dir,
        }
        base = base_dirs.get(category, self.settings.storage_path / category)
        base.mkdir(parents=True, exist_ok=True)
        return base / filename
    
    def generate_filename(self, original_name: str, prefix: str = "") -> str:
        """Generate a unique filename preserving the original extension."""
        ext = Path(original_name).suffix
        unique_id = uuid.uuid4().hex[:12]
        if prefix:
            return f"{prefix}_{unique_id}{ext}"
        return f"{unique_id}{ext}"
    
    async def save_file(
        self,
        content: bytes,
        category: str,
        filename: str,
    ) -> Path:
        """Save file content to storage."""
        path = self._resolve_path(category, filename)
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path
    
    async def save_upload(
        self,
        content: bytes,
        original_filename: str,
        job_id: str,
    ) -> Path:
        """Save an uploaded file with job-specific naming."""
        filename = self.generate_filename(original_filename, prefix=job_id)
        return await self.save_file(content, "uploads", filename)
    
    async def read_file(self, category: str, filename: str) -> bytes:
        """Read file content from storage."""
        path = self._resolve_path(category, filename)
        async with aiofiles.open(path, "rb") as f:
            return await f.read()
    
    async def read_path(self, path: Path) -> bytes:
        """Read file content from a full path."""
        async with aiofiles.open(path, "rb") as f:
            return await f.read()
    
    def get_path(self, category: str, filename: str) -> Path:
        """Get the full path for a file."""
        return self._resolve_path(category, filename)
    
    async def delete_file(self, category: str, filename: str) -> bool:
        """Delete a file from storage."""
        path = self._resolve_path(category, filename)
        if path.exists():
            path.unlink()
            return True
        return False
    
    async def delete_path(self, path: Path) -> bool:
        """Delete a file by its full path."""
        if path.exists():
            path.unlink()
            return True
        return False
    
    def create_job_checkpoint_dir(self, job_id: str) -> Path:
        """Create and return a checkpoint directory for a job."""
        checkpoint_dir = self.settings.checkpoints_dir / job_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        return checkpoint_dir
    
    async def save_checkpoint(
        self,
        job_id: str,
        checkpoint_name: str,
        content: bytes,
    ) -> Path:
        """Save a checkpoint file for a job."""
        checkpoint_dir = self.create_job_checkpoint_dir(job_id)
        path = checkpoint_dir / checkpoint_name
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path
    
    async def load_checkpoint(
        self,
        job_id: str,
        checkpoint_name: str,
    ) -> bytes | None:
        """Load a checkpoint file for a job."""
        path = self.settings.checkpoints_dir / job_id / checkpoint_name
        if not path.exists():
            return None
        async with aiofiles.open(path, "rb") as f:
            return await f.read()
    
    def list_checkpoints(self, job_id: str) -> list[str]:
        """List all checkpoint files for a job."""
        checkpoint_dir = self.settings.checkpoints_dir / job_id
        if not checkpoint_dir.exists():
            return []
        return sorted([f.name for f in checkpoint_dir.iterdir() if f.is_file()])
    
    async def cleanup_job(self, job_id: str) -> None:
        """Clean up all files associated with a job."""
        # Clean checkpoints directory
        checkpoint_dir = self.settings.checkpoints_dir / job_id
        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)
        
        # Clean temp files (pattern matching)
        for temp_file in self.settings.temp_dir.glob(f"{job_id}*"):
            temp_file.unlink()


# Singleton instance
_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    """Get storage instance."""
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage

