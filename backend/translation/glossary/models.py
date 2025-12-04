"""Glossary data models for term management.

These models represent glossary terms and conflicts independently of
the database models, for use in the translation pipeline.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TermSource(str, Enum):
    """Source of a glossary term."""
    SYSTEM_DEFAULT = "system_default"  # Pre-defined system glossary
    USER_PROVIDED = "user_provided"    # User uploaded
    EXTRACTED = "extracted"            # Auto-extracted by LLM
    CONFIRMED = "confirmed"           # User confirmed extracted term


class TermConfidence(str, Enum):
    """Confidence level for extracted terms."""
    LOW = "low"       # First occurrence
    MEDIUM = "medium"  # 1-2 occurrences
    HIGH = "high"      # 3+ occurrences


@dataclass
class GlossaryTerm:
    """A single glossary term with its translation."""
    source_term: str  # Korean term
    target_term: str  # English translation

    # Metadata
    context: str | None = None  # "technical", "legal", "general"
    domain: str | None = None   # "manufacturing", "finance", etc.
    definition: str | None = None

    # Tracking
    source: TermSource = TermSource.EXTRACTED
    confidence: TermConfidence = TermConfidence.LOW
    occurrence_count: int = 1
    first_seen_unit: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_term": self.source_term,
            "target_term": self.target_term,
            "context": self.context,
            "domain": self.domain,
            "definition": self.definition,
            "source": self.source.value,
            "confidence": self.confidence.value,
            "occurrence_count": self.occurrence_count,
            "first_seen_unit": self.first_seen_unit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GlossaryTerm":
        """Create from dictionary."""
        source = TermSource(data.pop("source", "extracted"))
        confidence = TermConfidence(data.pop("confidence", "low"))
        return cls(source=source, confidence=confidence, **data)

    def increment_occurrence(self) -> None:
        """Increment occurrence count and update confidence."""
        self.occurrence_count += 1
        if self.occurrence_count >= 3:
            self.confidence = TermConfidence.HIGH
        elif self.occurrence_count >= 1:
            self.confidence = TermConfidence.MEDIUM


@dataclass
class GlossaryConflict:
    """A conflict where the same source term has multiple translations."""
    source_term: str
    translations: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    unit_indices: list[int] = field(default_factory=list)
    resolved: bool = False
    resolved_translation: str | None = None

    def add_translation(self, translation: str, context: str | None, unit_index: int) -> None:
        """Add a new translation for this term."""
        if translation not in self.translations:
            self.translations.append(translation)
            self.contexts.append(context or "")
            self.unit_indices.append(unit_index)

    def resolve(self, chosen_translation: str) -> None:
        """Resolve the conflict with the chosen translation."""
        self.resolved = True
        self.resolved_translation = chosen_translation

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_term": self.source_term,
            "translations": self.translations,
            "contexts": self.contexts,
            "unit_indices": self.unit_indices,
            "resolved": self.resolved,
            "resolved_translation": self.resolved_translation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GlossaryConflict":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class Glossary:
    """A collection of glossary terms."""
    name: str
    terms: dict[str, GlossaryTerm] = field(default_factory=dict)  # keyed by source_term
    domain: str | None = None

    def add_term(self, term: GlossaryTerm) -> None:
        """Add or update a term in the glossary."""
        existing = self.terms.get(term.source_term)
        if existing:
            # Update occurrence count
            existing.occurrence_count += term.occurrence_count
            if existing.occurrence_count >= 3:
                existing.confidence = TermConfidence.HIGH
            elif existing.occurrence_count >= 1:
                existing.confidence = TermConfidence.MEDIUM
        else:
            self.terms[term.source_term] = term

    def get_term(self, source_term: str) -> GlossaryTerm | None:
        """Get a term by source text."""
        return self.terms.get(source_term)

    def has_term(self, source_term: str) -> bool:
        """Check if a term exists."""
        return source_term in self.terms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "terms": {k: v.to_dict() for k, v in self.terms.items()},
            "domain": self.domain,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Glossary":
        """Create from dictionary."""
        terms_data = data.pop("terms", {})
        terms = {k: GlossaryTerm.from_dict(v) for k, v in terms_data.items()}
        return cls(terms=terms, **data)

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Glossary":
        """Deserialize from JSON."""
        return cls.from_dict(json.loads(json_str))

    def __len__(self) -> int:
        """Return number of terms."""
        return len(self.terms)

    def __iter__(self):
        """Iterate over terms."""
        return iter(self.terms.values())

