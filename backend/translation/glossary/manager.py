"""Glossary manager for three-tier glossary system.

Manages the hierarchy of glossaries:
- System glossaries (lowest priority)
- User glossaries (medium priority)
- Job glossaries (highest priority)

Provides merged glossary for prompts and handles conflict resolution.
"""

from dataclasses import dataclass

from backend.translation.chunking.tokenizer import get_tokenizer
from backend.translation.glossary.models import (
    Glossary,
    GlossaryConflict,
    GlossaryTerm,
    TermConfidence,
    TermSource,
)


@dataclass
class MergedGlossary:
    """Result of merging multiple glossaries."""
    terms: dict[str, GlossaryTerm]  # Merged terms, keyed by source_term
    sources: dict[str, str]  # Which glossary each term came from

    def to_prompt_format(self, max_tokens: int | None = None) -> str:
        """Format glossary as markdown table for LLM prompt.

        Args:
            max_tokens: Optional token limit for the glossary section

        Returns:
            Markdown-formatted glossary table
        """
        if not self.terms:
            return "No glossary terms provided."

        # Sort terms by confidence (HIGH first) and occurrence count
        sorted_terms = sorted(
            self.terms.values(),
            key=lambda t: (
                0 if t.confidence == TermConfidence.HIGH else (
                    1 if t.confidence == TermConfidence.MEDIUM else 2
                ),
                -t.occurrence_count
            )
        )

        lines = [
            "| Korean | English | Confidence |",
            "|--------|---------|------------|",
        ]

        tokenizer = get_tokenizer()
        current_tokens = tokenizer.count_tokens("\n".join(lines))

        for term in sorted_terms:
            line = f"| {term.source_term} | {term.target_term} | {term.confidence.value} |"
            line_tokens = tokenizer.count_tokens(line + "\n")

            if max_tokens and current_tokens + line_tokens > max_tokens:
                break

            lines.append(line)
            current_tokens += line_tokens

        return "\n".join(lines)

    def get_translation(self, source_term: str) -> str | None:
        """Get the translation for a source term."""
        term = self.terms.get(source_term)
        return term.target_term if term else None


class GlossaryManager:
    """Manages the three-tier glossary hierarchy."""

    def __init__(self) -> None:
        self._system_glossaries: dict[str, Glossary] = {}
        self._user_glossary: Glossary | None = None
        self._job_glossary: Glossary | None = None
        self._conflicts: dict[str, GlossaryConflict] = {}

    def set_system_glossaries(self, glossaries: list[Glossary]) -> None:
        """Set system-level glossaries.

        Args:
            glossaries: List of system glossaries to use
        """
        self._system_glossaries = {g.name: g for g in glossaries}

    def add_system_glossary(self, glossary: Glossary) -> None:
        """Add a system glossary.

        Args:
            glossary: System glossary to add
        """
        self._system_glossaries[glossary.name] = glossary

    def set_user_glossary(self, glossary: Glossary | None) -> None:
        """Set the user's glossary.

        Args:
            glossary: User's glossary (or None to clear)
        """
        self._user_glossary = glossary

    def set_job_glossary(self, glossary: Glossary | None) -> None:
        """Set the job-specific glossary.

        Args:
            glossary: Job glossary (or None to clear)
        """
        self._job_glossary = glossary

    def get_job_glossary(self) -> Glossary:
        """Get or create the job glossary."""
        if self._job_glossary is None:
            self._job_glossary = Glossary(name="job")
        return self._job_glossary

    def merge(self) -> MergedGlossary:
        """Merge all glossaries with priority: Job > User > System.

        Returns:
            MergedGlossary with all terms from all tiers
        """
        terms: dict[str, GlossaryTerm] = {}
        sources: dict[str, str] = {}

        # Add system glossary terms (lowest priority)
        for name, glossary in self._system_glossaries.items():
            for term in glossary:
                terms[term.source_term] = term
                sources[term.source_term] = f"system:{name}"

        # Add user glossary terms (override system)
        if self._user_glossary:
            for term in self._user_glossary:
                terms[term.source_term] = term
                sources[term.source_term] = "user"

        # Add job glossary terms (highest priority)
        if self._job_glossary:
            for term in self._job_glossary:
                # Check for conflicts with resolved terms
                if term.source_term in self._conflicts:
                    conflict = self._conflicts[term.source_term]
                    if conflict.resolved and conflict.resolved_translation:
                        # Use resolved translation
                        term = GlossaryTerm(
                            source_term=term.source_term,
                            target_term=conflict.resolved_translation,
                            source=TermSource.CONFIRMED,
                            confidence=TermConfidence.HIGH,
                            occurrence_count=term.occurrence_count,
                        )

                terms[term.source_term] = term
                sources[term.source_term] = "job"

        return MergedGlossary(terms=terms, sources=sources)

    def add_extracted_term(
        self,
        source_term: str,
        target_term: str,
        unit_index: int,
        context: str | None = None,
    ) -> GlossaryConflict | None:
        """Add an extracted term to the job glossary.

        Args:
            source_term: The Korean source term
            target_term: The English translation
            unit_index: The translation unit where this was found
            context: Optional context for the term

        Returns:
            GlossaryConflict if a conflict was detected, None otherwise
        """
        job_glossary = self.get_job_glossary()
        existing = job_glossary.get_term(source_term)

        if existing:
            if existing.target_term != target_term:
                # Conflict detected
                conflict = self._get_or_create_conflict(source_term)
                conflict.add_translation(
                    existing.target_term,
                    existing.context,
                    existing.first_seen_unit or 0
                )
                conflict.add_translation(target_term, context, unit_index)
                return conflict
            else:
                # Same translation, increment count
                existing.increment_occurrence()
                return None

        # New term
        term = GlossaryTerm(
            source_term=source_term,
            target_term=target_term,
            context=context,
            source=TermSource.EXTRACTED,
            confidence=TermConfidence.LOW,
            occurrence_count=1,
            first_seen_unit=unit_index,
        )
        job_glossary.add_term(term)
        return None

    def _get_or_create_conflict(self, source_term: str) -> GlossaryConflict:
        """Get or create a conflict for a source term."""
        if source_term not in self._conflicts:
            self._conflicts[source_term] = GlossaryConflict(source_term=source_term)
        return self._conflicts[source_term]

    def resolve_conflict(self, source_term: str, chosen_translation: str) -> None:
        """Resolve a conflict by choosing a translation.

        Args:
            source_term: The conflicting source term
            chosen_translation: The translation to use
        """
        if source_term in self._conflicts:
            conflict = self._conflicts[source_term]
            conflict.resolve(chosen_translation)

            # Update job glossary with resolved term
            job_glossary = self.get_job_glossary()
            existing = job_glossary.get_term(source_term)
            if existing:
                existing.target_term = chosen_translation
                existing.source = TermSource.CONFIRMED
                existing.confidence = TermConfidence.HIGH

    def get_conflicts(self) -> list[GlossaryConflict]:
        """Get all conflicts."""
        return list(self._conflicts.values())

    def get_unresolved_conflicts(self) -> list[GlossaryConflict]:
        """Get unresolved conflicts only."""
        return [c for c in self._conflicts.values() if not c.resolved]

    def promote_job_terms_to_user(self, term_sources: list[str] | None = None) -> list[GlossaryTerm]:
        """Promote job glossary terms to user glossary.

        Args:
            term_sources: Specific terms to promote, or None for all confirmed terms

        Returns:
            List of promoted terms
        """
        if not self._user_glossary:
            self._user_glossary = Glossary(name="user")

        if not self._job_glossary:
            return []

        promoted: list[GlossaryTerm] = []

        for term in self._job_glossary:
            # Only promote if requested or if confirmed/high confidence
            should_promote = (
                (term_sources is not None and term.source_term in term_sources) or
                (term_sources is None and (
                    term.source == TermSource.CONFIRMED or
                    term.confidence == TermConfidence.HIGH
                ))
            )

            if should_promote:
                promoted_term = GlossaryTerm(
                    source_term=term.source_term,
                    target_term=term.target_term,
                    context=term.context,
                    domain=term.domain,
                    source=TermSource.USER_PROVIDED,
                    confidence=TermConfidence.HIGH,
                    occurrence_count=term.occurrence_count,
                )
                self._user_glossary.add_term(promoted_term)
                promoted.append(promoted_term)

        return promoted

    def to_dict(self) -> dict:
        """Serialize manager state to dictionary."""
        return {
            "system_glossaries": {
                name: g.to_dict() for name, g in self._system_glossaries.items()
            },
            "user_glossary": self._user_glossary.to_dict() if self._user_glossary else None,
            "job_glossary": self._job_glossary.to_dict() if self._job_glossary else None,
            "conflicts": {k: c.to_dict() for k, c in self._conflicts.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GlossaryManager":
        """Deserialize manager state from dictionary."""
        manager = cls()

        if data.get("system_glossaries"):
            for name, g_data in data["system_glossaries"].items():
                manager._system_glossaries[name] = Glossary.from_dict(g_data)

        if data.get("user_glossary"):
            manager._user_glossary = Glossary.from_dict(data["user_glossary"])

        if data.get("job_glossary"):
            manager._job_glossary = Glossary.from_dict(data["job_glossary"])

        if data.get("conflicts"):
            for term, c_data in data["conflicts"].items():
                manager._conflicts[term] = GlossaryConflict.from_dict(c_data)

        return manager

