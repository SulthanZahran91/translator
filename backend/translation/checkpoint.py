"""Checkpoint manager for saving and restoring translation state.

Enables resuming translation jobs from where they left off after
interruptions or failures.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.core.storage import get_storage
from backend.translation.glossary.manager import GlossaryManager
from backend.translation.ir import TranslationUnit


@dataclass
class Checkpoint:
    """A saved translation checkpoint."""
    job_id: str
    unit_index: int
    translated_units: list[TranslationUnit]
    glossary_state: dict[str, Any]
    previous_tail: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "unit_index": self.unit_index,
            "translated_units": [u.to_dict() for u in self.translated_units],
            "glossary_state": self.glossary_state,
            "previous_tail": self.previous_tail,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Checkpoint":
        """Create from dictionary."""
        translated_units = [
            TranslationUnit.from_dict(u) for u in data.pop("translated_units", [])
        ]
        return cls(translated_units=translated_units, **data)
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Checkpoint":
        """Deserialize from JSON."""
        return cls.from_dict(json.loads(json_str))


class CheckpointManager:
    """Manages checkpoints for translation jobs."""
    
    def __init__(self, job_id: str) -> None:
        """Initialize checkpoint manager.
        
        Args:
            job_id: The job ID to manage checkpoints for
        """
        self._job_id = job_id
        self._storage = get_storage()
        self._checkpoint_interval = 10
    
    async def save(
        self,
        unit_index: int,
        translated_units: list[TranslationUnit],
        glossary_manager: GlossaryManager,
        previous_tail: str,
        total_input_tokens: int = 0,
        total_output_tokens: int = 0,
    ) -> Path:
        """Save a checkpoint.
        
        Args:
            unit_index: Index of the last completed unit
            translated_units: List of translated units so far
            glossary_manager: Current glossary state
            previous_tail: Previous context tail
            total_input_tokens: Total input tokens used
            total_output_tokens: Total output tokens used
            
        Returns:
            Path to the saved checkpoint file
        """
        checkpoint = Checkpoint(
            job_id=self._job_id,
            unit_index=unit_index,
            translated_units=translated_units,
            glossary_state=glossary_manager.to_dict(),
            previous_tail=previous_tail,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )
        
        filename = f"checkpoint_{unit_index:05d}.json"
        content = checkpoint.to_json().encode("utf-8")
        
        return await self._storage.save_checkpoint(
            self._job_id,
            filename,
            content,
        )
    
    async def load_latest(self) -> Checkpoint | None:
        """Load the most recent checkpoint.
        
        Returns:
            The latest checkpoint, or None if no checkpoints exist
        """
        checkpoints = self._storage.list_checkpoints(self._job_id)
        
        if not checkpoints:
            return None
        
        # Get the latest checkpoint (highest unit index)
        latest = sorted(checkpoints)[-1]
        
        content = await self._storage.load_checkpoint(self._job_id, latest)
        if content is None:
            return None
        
        return Checkpoint.from_json(content.decode("utf-8"))
    
    async def load_checkpoint(self, unit_index: int) -> Checkpoint | None:
        """Load a specific checkpoint.
        
        Args:
            unit_index: The unit index of the checkpoint
            
        Returns:
            The checkpoint, or None if not found
        """
        filename = f"checkpoint_{unit_index:05d}.json"
        content = await self._storage.load_checkpoint(self._job_id, filename)
        
        if content is None:
            return None
        
        return Checkpoint.from_json(content.decode("utf-8"))
    
    def should_checkpoint(self, unit_index: int) -> bool:
        """Check if we should create a checkpoint at this unit.
        
        Args:
            unit_index: Current unit index
            
        Returns:
            True if a checkpoint should be created
        """
        return (unit_index + 1) % self._checkpoint_interval == 0
    
    async def cleanup(self) -> None:
        """Remove all checkpoints for this job."""
        await self._storage.cleanup_job(self._job_id)


async def save_checkpoint(
    job_id: str,
    unit_index: int,
    translated_units: list[TranslationUnit],
    glossary_manager: GlossaryManager,
    previous_tail: str,
    total_input_tokens: int = 0,
    total_output_tokens: int = 0,
) -> Path:
    """Convenience function to save a checkpoint.
    
    Args:
        job_id: The job ID
        unit_index: Index of the last completed unit
        translated_units: List of translated units so far
        glossary_manager: Current glossary state
        previous_tail: Previous context tail
        total_input_tokens: Total input tokens used
        total_output_tokens: Total output tokens used
        
    Returns:
        Path to the saved checkpoint file
    """
    manager = CheckpointManager(job_id)
    return await manager.save(
        unit_index,
        translated_units,
        glossary_manager,
        previous_tail,
        total_input_tokens,
        total_output_tokens,
    )


async def load_latest_checkpoint(job_id: str) -> Checkpoint | None:
    """Convenience function to load the latest checkpoint.
    
    Args:
        job_id: The job ID
        
    Returns:
        The latest checkpoint, or None if no checkpoints exist
    """
    manager = CheckpointManager(job_id)
    return await manager.load_latest()

