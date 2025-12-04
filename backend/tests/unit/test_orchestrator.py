"""Tests for translation orchestrator."""

import pytest

from backend.translation.ir import TranslationUnit
from backend.translation.orchestrator import (
    MockTranslationOrchestrator,
    TranslationPhase,
    TranslationProgress,
)


class TestTranslationProgress:
    """Tests for TranslationProgress class."""

    def test_initial_progress(self):
        """Test initial progress state."""
        progress = TranslationProgress()

        assert progress.total_units == 0
        assert progress.completed_units == 0
        assert progress.phase == TranslationPhase.PENDING
        assert progress.percent_complete == 0.0

    def test_percent_complete(self):
        """Test percentage calculation."""
        progress = TranslationProgress(total_units=10, completed_units=5)

        assert progress.percent_complete == 50.0

    def test_percent_complete_empty(self):
        """Test percentage with zero total."""
        progress = TranslationProgress(total_units=0, completed_units=0)

        assert progress.percent_complete == 0.0


class TestMockTranslationOrchestrator:
    """Tests for MockTranslationOrchestrator."""

    @pytest.mark.asyncio
    async def test_translate_single_unit(self):
        """Test translating a single unit."""
        orchestrator = MockTranslationOrchestrator()

        units = [
            TranslationUnit(
                source_text='<p id="p1">안녕하세요</p>',
                sequence_number=0,
            )
        ]

        result = await orchestrator.translate_units(units)

        assert len(result) == 1
        assert result[0].translated_text is not None
        assert "안녕하세요" in result[0].translated_text or "Translated" in result[0].translated_text

    @pytest.mark.asyncio
    async def test_translate_multiple_units(self):
        """Test translating multiple units."""
        orchestrator = MockTranslationOrchestrator()

        units = [
            TranslationUnit(
                source_text=f'<p id="p{i}">텍스트 {i}</p>',
                sequence_number=i,
            )
            for i in range(3)
        ]

        result = await orchestrator.translate_units(units)

        assert len(result) == 3
        for unit in result:
            assert unit.translated_text is not None

    @pytest.mark.asyncio
    async def test_progress_tracking(self):
        """Test that progress is tracked correctly."""
        progress_updates = []

        def track_progress(progress: TranslationProgress):
            progress_updates.append({
                "completed": progress.completed_units,
                "total": progress.total_units,
                "phase": progress.phase,
            })

        orchestrator = MockTranslationOrchestrator(progress_callback=track_progress)

        units = [
            TranslationUnit(source_text=f"Unit {i}", sequence_number=i)
            for i in range(2)
        ]

        await orchestrator.translate_units(units)

        # Should have multiple progress updates
        assert len(progress_updates) > 0

        # Final update should show completed
        final = progress_updates[-1]
        assert final["phase"] == TranslationPhase.COMPLETED

    @pytest.mark.asyncio
    async def test_mock_responses(self):
        """Test custom mock responses."""
        mock_responses = {
            0: '<p id="p0">Hello, World!</p>',
            1: '<p id="p1">This is a test.</p>',
        }

        orchestrator = MockTranslationOrchestrator(mock_responses=mock_responses)

        units = [
            TranslationUnit(
                source_text='<p id="p0">안녕하세요</p>',
                sequence_number=0,
            ),
            TranslationUnit(
                source_text='<p id="p1">테스트입니다</p>',
                sequence_number=1,
            ),
        ]

        result = await orchestrator.translate_units(units)

        assert "Hello, World!" in result[0].translated_text
        assert "This is a test." in result[1].translated_text

    @pytest.mark.asyncio
    async def test_glossary_extraction(self):
        """Test that glossary terms are extracted from responses."""
        mock_responses = {
            0: 'Hello <glossary>테스트|test</glossary> world',
        }

        orchestrator = MockTranslationOrchestrator(mock_responses=mock_responses)

        units = [
            TranslationUnit(source_text="Source", sequence_number=0),
        ]

        await orchestrator.translate_units(units)

        # Check glossary manager has the extracted term
        job_glossary = orchestrator.glossary_manager.get_job_glossary()
        assert job_glossary.has_term("테스트")
        assert job_glossary.get_term("테스트").target_term == "test"

    @pytest.mark.asyncio
    async def test_pause_and_resume(self):
        """Test pausing translation."""
        orchestrator = MockTranslationOrchestrator()

        units = [
            TranslationUnit(source_text=f"Unit {i}", sequence_number=i)
            for i in range(5)
        ]

        # Request pause after starting
        orchestrator.pause()

        await orchestrator.translate_units(units)

        # Should not complete all units
        assert orchestrator.progress.phase == TranslationPhase.PAUSED

    @pytest.mark.asyncio
    async def test_resume_from_index(self):
        """Test resuming from a specific index."""
        mock_responses = {
            2: '<p id="p2">Translated Unit 2</p>',
            3: '<p id="p3">Translated Unit 3</p>',
        }

        orchestrator = MockTranslationOrchestrator(mock_responses=mock_responses)

        # Create units with pre-translated first two
        units = [
            TranslationUnit(
                source_text=f'<p id="p{i}">Unit {i}</p>',
                sequence_number=i,
                translated_text=f"Pre-translated {i}" if i < 2 else None,
            )
            for i in range(4)
        ]

        result = await orchestrator.translate_units(units, start_from=2)

        assert len(result) == 4
        # First two should keep their translations
        assert "Pre-translated 0" in result[0].translated_text
        assert "Pre-translated 1" in result[1].translated_text
        # Last two should be newly translated
        assert "Translated Unit 2" in result[2].translated_text

