"""Translation orchestrator for managing the translation process.

Handles:
- Sequential translation of translation units
- Context window management (glossary, previous tail)
- LLM API calls with retry logic
- Glossary term extraction from responses
- Progress tracking
"""

import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.models.user import User

from backend.core.config import get_settings
from backend.translation.chunking.tokenizer import get_tokenizer
from backend.translation.glossary.extractor import GlossaryExtractor
from backend.translation.glossary.manager import GlossaryManager
from backend.translation.ir import TranslationUnit


class TranslationPhase(str, Enum):
    """Current phase of translation."""
    PENDING = "pending"
    TRANSLATING = "translating"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class TranslationProgress:
    """Progress tracking for translation."""
    total_units: int = 0
    completed_units: int = 0
    current_unit: int = 0
    phase: TranslationPhase = TranslationPhase.PENDING
    current_unit_retries: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def percent_complete(self) -> float:
        """Get completion percentage."""
        if self.total_units == 0:
            return 0.0
        return (self.completed_units / self.total_units) * 100


@dataclass
class TranslationResult:
    """Result of translating a single unit."""
    unit: TranslationUnit
    translated_text: str
    input_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0
    error: str | None = None


# System prompt template
SYSTEM_PROMPT = """You are a professional Korean-to-English translator.

## TRANSLATION RULES
1. Translate ALL Korean text to natural, fluent English
2. Preserve EXACT structure (paragraphs, tables, formatting markers)
3. Use terminology from the provided glossary CONSISTENTLY
4. Match the tone and formality of the original
5. Keep all XML-like tags (e.g., <p id="...">, <table>, <td>) exactly as they appear

## TERMINOLOGY HANDLING
When you encounter a technical term, proper noun, or domain-specific phrase:
- First check the glossary below — use the provided translation
- If NOT in glossary and it's a significant term, mark it:
  <glossary>한국어용어|English Translation</glossary>

## OUTPUT FORMAT
- Return ONLY the translated text with the same structure
- Preserve all id attributes in tags
- Do not add explanations or notes
"""


class TranslationOrchestrator:
    """Orchestrates the translation of documents."""

    def __init__(
        self,
        user: "User",
        db_session: "AsyncSession | None" = None,
        glossary_manager: GlossaryManager | None = None,
        progress_callback: Callable[[TranslationProgress], Awaitable[None] | None] | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            user: The user who owns the job (for auth)
            db_session: Database session for updating user credentials
            glossary_manager: Optional glossary manager for term consistency
            progress_callback: Optional callback for progress updates
        """
        self._settings = get_settings()
        self._tokenizer = get_tokenizer()
        self._glossary_manager = glossary_manager or GlossaryManager()
        self._glossary_extractor = GlossaryExtractor(
            self._glossary_manager.get_job_glossary()
        )
        self._progress_callback = progress_callback

        self._progress = TranslationProgress()
        self._previous_tail: str = ""
        self._should_pause = False

        self._should_pause = False

        from backend.translation.llm_client import UpstreamLLMClient
        self._client = UpstreamLLMClient(user=user, db_session=db_session)

    async def translate_units(
        self,
        units: list[TranslationUnit],
        start_from: int = 0,
    ) -> list[TranslationUnit]:
        """Translate all units sequentially.

        Args:
            units: List of translation units to translate
            start_from: Index to start from (for resuming)

        Returns:
            List of translated units
        """
        self._progress.total_units = len(units)
        self._progress.phase = TranslationPhase.TRANSLATING
        await self._notify_progress()

        translated: list[TranslationUnit] = []

        # Handle already-translated units (for resume)
        for i in range(start_from):
            translated.append(units[i])

        for i in range(start_from, len(units)):
            if self._should_pause:
                self._progress.phase = TranslationPhase.PAUSED
                await self._notify_progress()
                break

            unit = units[i]
            self._progress.current_unit = i
            await self._notify_progress()

            try:
                result = await self._translate_unit(unit)

                # Update unit with translation
                unit.translated_text = result.translated_text
                translated.append(unit)

                # Update progress
                self._progress.completed_units = len(translated)
                self._progress.total_input_tokens += result.input_tokens
                self._progress.total_output_tokens += result.output_tokens

                # Update previous tail for context
                self._update_previous_tail(result.translated_text)

            except Exception as e:
                self._progress.errors.append(f"Unit {i}: {str(e)}")
                self._progress.phase = TranslationPhase.FAILED
                await self._notify_progress()
                raise

            await self._notify_progress()

        if not self._should_pause:
            self._progress.phase = TranslationPhase.COMPLETED
            await self._notify_progress()

        return translated

    async def _translate_unit(self, unit: TranslationUnit) -> TranslationResult:
        """Translate a single unit with retry logic.

        Args:
            unit: The translation unit to translate

        Returns:
            TranslationResult with the translation
        """
        prompt = self._build_prompt(unit)

        last_error: str | None = None

        for attempt in range(self._settings.llm_max_retries):
            try:
                response = await self._call_llm(prompt)

                # Extract glossary terms from response
                extraction = self._glossary_extractor.extract(
                    response["content"],
                    unit.sequence_number,
                )

                # Add extracted terms to glossary manager
                for term in extraction.terms:
                    self._glossary_manager.add_extracted_term(
                        term.source_term,
                        term.target_term,
                        unit.sequence_number,
                        term.context,
                    )

                return TranslationResult(
                    unit=unit,
                    translated_text=extraction.cleaned_text,
                    input_tokens=response.get("input_tokens", 0),
                    output_tokens=response.get("output_tokens", 0),
                    retries=attempt,
                )

            except Exception as e:
                last_error = str(e)
                self._progress.current_unit_retries = attempt + 1
                await self._notify_progress()

                # Exponential backoff
                delay = min(
                    self._settings.llm_retry_base_delay * (2 ** attempt),
                    self._settings.llm_retry_max_delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Failed to translate unit after {self._settings.llm_max_retries} attempts: {last_error}"
        )

    def _build_prompt(self, unit: TranslationUnit) -> str:
        """Build the full prompt for a translation unit.

        Args:
            unit: The translation unit

        Returns:
            The complete prompt string
        """
        # Get merged glossary
        merged = self._glossary_manager.merge()
        glossary_text = merged.to_prompt_format(
            max_tokens=self._settings.glossary_token_budget
        )

        # Build user message
        parts = [
            f"## Progress: Unit {unit.sequence_number + 1} of {self._progress.total_units}",
            "",
            "## Glossary:",
            glossary_text,
            "",
        ]

        if self._previous_tail:
            parts.extend([
                "## Previous context (for reference, already translated):",
                self._previous_tail,
                "",
            ])

        parts.extend([
            "---",
            "",
            "## Source text to translate:",
            unit.source_text,
            "",
            "---",
            "",
            "Translate the above Korean text to English. Maintain exact structure.",
        ])

        return "\n".join(parts)

    async def _call_llm(self, prompt: str) -> dict[str, Any]:
        """Call the LLM API.

        Args:
            prompt: The user prompt

        Returns:
            Dict with 'content', 'input_tokens', 'output_tokens'
        """
        response = await self._client.chat_completion(
            model=self._settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )

        # Extract content and usage from response
        # Response format is OpenAI-compatible dict (from UpstreamLLMClient)
        choice = response["choices"][0]
        message = choice["message"]
        usage = response.get("usage", {})

        return {
            "content": message.get("content", ""),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }

    def _update_previous_tail(self, translated_text: str) -> None:
        """Update the previous tail for context.

        Keeps the last N tokens of translated text for context in the next unit.

        Args:
            translated_text: The just-completed translation
        """
        max_tokens = self._settings.context_tail_tokens
        self._previous_tail = self._tokenizer.truncate_to_tokens(
            translated_text,
            max_tokens,
        )

    async def _notify_progress(self) -> None:
        """Notify progress callback if set."""
        if self._progress_callback:
            result = self._progress_callback(self._progress)
            if asyncio.iscoroutine(result):
                await result

    def pause(self) -> None:
        """Request pause after current unit completes."""
        self._should_pause = True

    def resume(self) -> None:
        """Clear pause flag."""
        self._should_pause = False

    @property
    def progress(self) -> TranslationProgress:
        """Get current progress."""
        return self._progress

    @property
    def glossary_manager(self) -> GlossaryManager:
        """Get the glossary manager."""
        return self._glossary_manager

    def set_previous_tail(self, tail: str) -> None:
        """Set the previous tail (for resuming from checkpoint)."""
        self._previous_tail = tail


class MockTranslationOrchestrator(TranslationOrchestrator):
    """Mock orchestrator for testing without LLM API calls."""

    def __init__(
        self,
        mock_responses: dict[int, str] | None = None,
        **kwargs,
    ) -> None:
        """Initialize mock orchestrator.

        Args:
            mock_responses: Optional dict of unit_index -> translated_text
            **kwargs: Passed to parent
        """
        super().__init__(**kwargs)
        self._mock_responses = mock_responses or {}

    async def _call_llm(self, prompt: str) -> dict[str, Any]:
        """Return mock response instead of calling LLM."""
        # Extract unit number from prompt
        unit_match = re.search(r"Unit (\d+) of", prompt)
        unit_num = int(unit_match.group(1)) - 1 if unit_match else 0

        if unit_num in self._mock_responses:
            content = self._mock_responses[unit_num]
        else:
            # Generate a simple mock translation
            # Extract source text from prompt
            source_match = re.search(
                r"## Source text to translate:\n(.*?)\n---",
                prompt,
                re.DOTALL,
            )
            source_text = source_match.group(1) if source_match else ""

            # Simple mock: wrap text and add mock glossary
            content = f"[Translated] {source_text}"
            if "용어" in source_text:
                content += " <glossary>용어|terminology</glossary>"

        # Simulate token usage
        return {
            "content": content,
            "input_tokens": len(prompt) // 4,
            "output_tokens": len(content) // 4,
        }

