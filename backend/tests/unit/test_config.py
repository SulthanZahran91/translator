"""Tests for configuration module."""

from pathlib import Path

import pytest

from backend.core.config import Settings


def test_default_settings():
    """Test default settings values."""
    settings = Settings(
        storage_path=Path("./storage/test"),
    )
    
    assert settings.app_name == "Document Translator"
    assert settings.debug is False
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.max_upload_size_mb == 50
    assert settings.checkpoint_interval == 10


def test_settings_directories():
    """Test that directory properties work correctly."""
    settings = Settings(
        storage_path=Path("./storage/test"),
    )
    
    assert settings.uploads_dir == Path("./storage/test/uploads")
    assert settings.outputs_dir == Path("./storage/test/outputs")
    assert settings.checkpoints_dir == Path("./storage/test/checkpoints")
    assert settings.temp_dir == Path("./storage/test/temp")
    assert settings.db_dir == Path("./storage/test/db")


def test_ensure_directories(tmp_path: Path):
    """Test directory creation."""
    settings = Settings(
        storage_path=tmp_path / "storage",
    )
    
    settings.ensure_directories()
    
    assert settings.uploads_dir.exists()
    assert settings.outputs_dir.exists()
    assert settings.checkpoints_dir.exists()
    assert settings.temp_dir.exists()
    assert settings.db_dir.exists()


def test_llm_settings():
    """Test LLM configuration settings."""
    settings = Settings(
        llm_api_url="http://custom:8080/v1",
        llm_api_key="test-key",
        llm_model="custom-model",
    )
    
    assert settings.llm_api_url == "http://custom:8080/v1"
    assert settings.llm_api_key == "test-key"
    assert settings.llm_model == "custom-model"

