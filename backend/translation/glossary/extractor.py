"""Glossary term extractor from LLM responses.

Parses <glossary>source|target</glossary> tags from LLM translation
responses and updates the glossary with extracted terms.
"""

import re
from dataclasses import dataclass

from backend.translation.glossary.models import (
    Glossary,
    GlossaryConflict,
    GlossaryTerm,
    TermConfidence,
    TermSource,
)


@dataclass
class ExtractionResult:
    """Result of glossary term extraction from a response."""
    terms: list[GlossaryTerm]
    conflicts: list[GlossaryConflict]
    cleaned_text: str  # Response with glossary tags removed


class GlossaryExtractor:
    """Extracts glossary terms from LLM responses."""
    
    # Pattern to match <glossary>source|target</glossary> tags
    GLOSSARY_PATTERN = re.compile(
        r"<glossary>([^|<>]+)\|([^<>]+)</glossary>",
        re.IGNORECASE
    )
    
    def __init__(self, existing_glossary: Glossary | None = None) -> None:
        """Initialize extractor.
        
        Args:
            existing_glossary: Optional existing glossary to check for conflicts
        """
        self._glossary = existing_glossary or Glossary(name="extracted")
        self._conflicts: dict[str, GlossaryConflict] = {}
    
    def extract(self, response_text: str, unit_index: int) -> ExtractionResult:
        """Extract glossary terms from an LLM response.
        
        Args:
            response_text: The LLM's translation response
            unit_index: Index of the translation unit (for tracking)
            
        Returns:
            ExtractionResult with extracted terms, conflicts, and cleaned text
        """
        terms: list[GlossaryTerm] = []
        new_conflicts: list[GlossaryConflict] = []
        
        # Find all glossary tags
        matches = list(self.GLOSSARY_PATTERN.finditer(response_text))
        
        for match in matches:
            source_term = match.group(1).strip()
            target_term = match.group(2).strip()
            
            if not source_term or not target_term:
                continue
            
            # Check for existing term with different translation
            existing = self._glossary.get_term(source_term)
            
            if existing and existing.target_term != target_term:
                # Conflict detected
                conflict = self._get_or_create_conflict(source_term)
                conflict.add_translation(
                    existing.target_term,
                    existing.context,
                    existing.first_seen_unit or 0
                )
                conflict.add_translation(target_term, None, unit_index)
                new_conflicts.append(conflict)
            elif existing:
                # Same translation, increment count
                existing.increment_occurrence()
            else:
                # New term
                term = GlossaryTerm(
                    source_term=source_term,
                    target_term=target_term,
                    source=TermSource.EXTRACTED,
                    confidence=TermConfidence.LOW,
                    occurrence_count=1,
                    first_seen_unit=unit_index,
                )
                terms.append(term)
                self._glossary.add_term(term)
        
        # Remove glossary tags from response
        cleaned_text = self.GLOSSARY_PATTERN.sub("", response_text)
        
        return ExtractionResult(
            terms=terms,
            conflicts=new_conflicts,
            cleaned_text=cleaned_text.strip(),
        )
    
    def _get_or_create_conflict(self, source_term: str) -> GlossaryConflict:
        """Get existing conflict or create new one."""
        if source_term not in self._conflicts:
            self._conflicts[source_term] = GlossaryConflict(source_term=source_term)
        return self._conflicts[source_term]
    
    @property
    def glossary(self) -> Glossary:
        """Get the current glossary."""
        return self._glossary
    
    @property
    def conflicts(self) -> list[GlossaryConflict]:
        """Get all detected conflicts."""
        return list(self._conflicts.values())
    
    @property
    def unresolved_conflicts(self) -> list[GlossaryConflict]:
        """Get unresolved conflicts only."""
        return [c for c in self._conflicts.values() if not c.resolved]


def extract_glossary_terms(
    response_text: str,
    existing_glossary: Glossary | None = None,
    unit_index: int = 0,
) -> ExtractionResult:
    """Convenience function to extract glossary terms.
    
    Args:
        response_text: The LLM's translation response
        existing_glossary: Optional existing glossary
        unit_index: Index of the translation unit
        
    Returns:
        ExtractionResult with extracted terms and cleaned text
    """
    extractor = GlossaryExtractor(existing_glossary)
    return extractor.extract(response_text, unit_index)


def clean_response(response_text: str) -> str:
    """Remove glossary tags from response text.
    
    Args:
        response_text: Text potentially containing glossary tags
        
    Returns:
        Text with glossary tags removed
    """
    return GlossaryExtractor.GLOSSARY_PATTERN.sub("", response_text).strip()

