"""Tests for storage module."""

from pathlib import Path

import pytest

from backend.core.config import Settings
from backend.core.storage import LocalStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    """Create a storage instance with temporary directory."""
    storage = LocalStorage()
    storage.settings = Settings(storage_path=tmp_path / "storage")
    storage.settings.ensure_directories()
    return storage


def test_generate_filename(storage: LocalStorage):
    """Test unique filename generation."""
    filename1 = storage.generate_filename("document.pdf")
    filename2 = storage.generate_filename("document.pdf")
    
    # Should be unique
    assert filename1 != filename2
    # Should preserve extension
    assert filename1.endswith(".pdf")
    assert filename2.endswith(".pdf")


def test_generate_filename_with_prefix(storage: LocalStorage):
    """Test filename generation with prefix."""
    filename = storage.generate_filename("document.docx", prefix="job123")
    
    assert filename.startswith("job123_")
    assert filename.endswith(".docx")


@pytest.mark.asyncio
async def test_save_and_read_file(storage: LocalStorage):
    """Test saving and reading file content."""
    content = b"Hello, World!"
    
    path = await storage.save_file(content, "uploads", "test.txt")
    
    assert path.exists()
    
    read_content = await storage.read_file("uploads", "test.txt")
    assert read_content == content


@pytest.mark.asyncio
async def test_save_upload(storage: LocalStorage):
    """Test saving an uploaded file."""
    content = b"PDF content here"
    
    path = await storage.save_upload(content, "document.pdf", "job123")
    
    assert path.exists()
    assert "job123" in path.name
    assert path.suffix == ".pdf"


@pytest.mark.asyncio
async def test_delete_file(storage: LocalStorage):
    """Test file deletion."""
    content = b"To be deleted"
    await storage.save_file(content, "temp", "delete_me.txt")
    
    result = await storage.delete_file("temp", "delete_me.txt")
    
    assert result is True
    assert not storage.get_path("temp", "delete_me.txt").exists()


@pytest.mark.asyncio
async def test_delete_nonexistent_file(storage: LocalStorage):
    """Test deletion of non-existent file."""
    result = await storage.delete_file("temp", "nonexistent.txt")
    assert result is False


@pytest.mark.asyncio
async def test_checkpoint_operations(storage: LocalStorage):
    """Test checkpoint save, load, and list operations."""
    job_id = "test-job-123"
    checkpoint_data = b'{"unit": 5, "glossary": {}}'
    
    # Save checkpoint
    path = await storage.save_checkpoint(job_id, "checkpoint_5.json", checkpoint_data)
    assert path.exists()
    
    # Load checkpoint
    loaded = await storage.load_checkpoint(job_id, "checkpoint_5.json")
    assert loaded == checkpoint_data
    
    # List checkpoints
    checkpoints = storage.list_checkpoints(job_id)
    assert "checkpoint_5.json" in checkpoints


@pytest.mark.asyncio
async def test_load_nonexistent_checkpoint(storage: LocalStorage):
    """Test loading non-existent checkpoint."""
    result = await storage.load_checkpoint("fake-job", "fake.json")
    assert result is None


@pytest.mark.asyncio
async def test_cleanup_job(storage: LocalStorage):
    """Test job cleanup removes all associated files."""
    job_id = "cleanup-test"
    
    # Create some files
    await storage.save_checkpoint(job_id, "checkpoint.json", b"{}")
    await storage.save_file(b"temp", "temp", f"{job_id}_temp.txt")
    
    checkpoint_dir = storage.settings.checkpoints_dir / job_id
    assert checkpoint_dir.exists()
    
    # Cleanup
    await storage.cleanup_job(job_id)
    
    assert not checkpoint_dir.exists()

