"""Tests for glossary system."""


from backend.translation.glossary.extractor import (
    GlossaryExtractor,
    clean_response,
    extract_glossary_terms,
)
from backend.translation.glossary.manager import GlossaryManager
from backend.translation.glossary.models import (
    Glossary,
    GlossaryTerm,
    TermConfidence,
    TermSource,
)


class TestGlossaryTerm:
    """Tests for GlossaryTerm class."""

    def test_create_term(self):
        """Test creating a glossary term."""
        term = GlossaryTerm(
            source_term="안녕하세요",
            target_term="Hello",
        )

        assert term.source_term == "안녕하세요"
        assert term.target_term == "Hello"
        assert term.confidence == TermConfidence.LOW
        assert term.occurrence_count == 1

    def test_increment_occurrence(self):
        """Test that incrementing occurrence updates confidence."""
        term = GlossaryTerm(source_term="테스트", target_term="test")

        assert term.confidence == TermConfidence.LOW

        term.increment_occurrence()
        assert term.occurrence_count == 2
        assert term.confidence == TermConfidence.MEDIUM

        term.increment_occurrence()
        assert term.occurrence_count == 3
        assert term.confidence == TermConfidence.HIGH

    def test_serialization(self):
        """Test term serialization."""
        term = GlossaryTerm(
            source_term="용어",
            target_term="term",
            context="technical",
            confidence=TermConfidence.HIGH,
        )

        data = term.to_dict()
        restored = GlossaryTerm.from_dict(data)

        assert restored.source_term == term.source_term
        assert restored.target_term == term.target_term
        assert restored.confidence == TermConfidence.HIGH


class TestGlossary:
    """Tests for Glossary class."""

    def test_create_glossary(self):
        """Test creating a glossary."""
        glossary = Glossary(name="test")

        assert glossary.name == "test"
        assert len(glossary) == 0

    def test_add_term(self):
        """Test adding terms to glossary."""
        glossary = Glossary(name="test")
        term = GlossaryTerm(source_term="단어", target_term="word")

        glossary.add_term(term)

        assert len(glossary) == 1
        assert glossary.has_term("단어")
        assert glossary.get_term("단어").target_term == "word"

    def test_add_duplicate_term_increments_count(self):
        """Test that adding duplicate term increments occurrence count."""
        glossary = Glossary(name="test")
        term1 = GlossaryTerm(source_term="단어", target_term="word")
        term2 = GlossaryTerm(source_term="단어", target_term="word")

        glossary.add_term(term1)
        glossary.add_term(term2)

        assert len(glossary) == 1
        assert glossary.get_term("단어").occurrence_count == 2

    def test_json_serialization(self):
        """Test JSON serialization."""
        glossary = Glossary(name="test", domain="technical")
        glossary.add_term(GlossaryTerm(source_term="용어", target_term="terminology"))

        json_str = glossary.to_json()
        restored = Glossary.from_json(json_str)

        assert restored.name == "test"
        assert restored.domain == "technical"
        assert len(restored) == 1
        assert restored.get_term("용어").target_term == "terminology"


class TestGlossaryExtractor:
    """Tests for GlossaryExtractor class."""

    def test_extract_single_term(self):
        """Test extracting a single term."""
        response = "Hello, this is a <glossary>테스트|test</glossary> response."

        result = extract_glossary_terms(response)

        assert len(result.terms) == 1
        assert result.terms[0].source_term == "테스트"
        assert result.terms[0].target_term == "test"

    def test_extract_multiple_terms(self):
        """Test extracting multiple terms."""
        response = """
        The <glossary>문서|document</glossary> contains important
        <glossary>데이터|data</glossary> for analysis.
        """

        result = extract_glossary_terms(response)

        assert len(result.terms) == 2
        source_terms = {t.source_term for t in result.terms}
        assert "문서" in source_terms
        assert "데이터" in source_terms

    def test_cleaned_text_removes_tags(self):
        """Test that cleaned text has glossary tags removed."""
        response = "Hello, this is a <glossary>테스트|test</glossary> response."

        result = extract_glossary_terms(response)

        assert "<glossary>" not in result.cleaned_text
        assert "Hello, this is a  response." == result.cleaned_text

    def test_detect_conflict(self):
        """Test conflict detection when same term has different translations."""
        extractor = GlossaryExtractor()

        # First extraction
        result1 = extractor.extract("<glossary>용어|term</glossary>", unit_index=0)
        assert len(result1.conflicts) == 0

        # Second extraction with different translation
        result2 = extractor.extract("<glossary>용어|terminology</glossary>", unit_index=1)
        assert len(result2.conflicts) == 1
        assert result2.conflicts[0].source_term == "용어"

    def test_clean_response_function(self):
        """Test the clean_response convenience function."""
        response = "Text with <glossary>태그|tag</glossary> inside."
        cleaned = clean_response(response)

        assert "<glossary>" not in cleaned
        assert "Text with  inside." == cleaned


class TestGlossaryManager:
    """Tests for GlossaryManager class."""

    def test_create_manager(self):
        """Test creating a glossary manager."""
        manager = GlossaryManager()

        merged = manager.merge()
        assert len(merged.terms) == 0

    def test_system_glossary_priority(self):
        """Test that system glossaries have lowest priority."""
        manager = GlossaryManager()

        system = Glossary(name="system")
        system.add_term(GlossaryTerm(source_term="용어", target_term="system_translation"))
        manager.add_system_glossary(system)

        merged = manager.merge()
        assert merged.get_translation("용어") == "system_translation"
        assert merged.sources["용어"] == "system:system"

    def test_user_glossary_overrides_system(self):
        """Test that user glossary overrides system."""
        manager = GlossaryManager()

        system = Glossary(name="system")
        system.add_term(GlossaryTerm(source_term="용어", target_term="system_translation"))
        manager.add_system_glossary(system)

        user = Glossary(name="user")
        user.add_term(GlossaryTerm(source_term="용어", target_term="user_translation"))
        manager.set_user_glossary(user)

        merged = manager.merge()
        assert merged.get_translation("용어") == "user_translation"
        assert merged.sources["용어"] == "user"

    def test_job_glossary_overrides_all(self):
        """Test that job glossary has highest priority."""
        manager = GlossaryManager()

        system = Glossary(name="system")
        system.add_term(GlossaryTerm(source_term="용어", target_term="system_translation"))
        manager.add_system_glossary(system)

        user = Glossary(name="user")
        user.add_term(GlossaryTerm(source_term="용어", target_term="user_translation"))
        manager.set_user_glossary(user)

        job = Glossary(name="job")
        job.add_term(GlossaryTerm(source_term="용어", target_term="job_translation"))
        manager.set_job_glossary(job)

        merged = manager.merge()
        assert merged.get_translation("용어") == "job_translation"
        assert merged.sources["용어"] == "job"

    def test_add_extracted_term(self):
        """Test adding extracted terms."""
        manager = GlossaryManager()

        conflict = manager.add_extracted_term("테스트", "test", unit_index=0)

        assert conflict is None
        job = manager.get_job_glossary()
        assert job.has_term("테스트")

    def test_add_extracted_term_detects_conflict(self):
        """Test that adding conflicting terms is detected."""
        manager = GlossaryManager()

        manager.add_extracted_term("테스트", "test", unit_index=0)
        conflict = manager.add_extracted_term("테스트", "testing", unit_index=1)

        assert conflict is not None
        assert conflict.source_term == "테스트"
        assert "test" in conflict.translations
        assert "testing" in conflict.translations

    def test_resolve_conflict(self):
        """Test resolving a conflict."""
        manager = GlossaryManager()

        manager.add_extracted_term("테스트", "test", unit_index=0)
        manager.add_extracted_term("테스트", "testing", unit_index=1)

        manager.resolve_conflict("테스트", "test")

        # Conflict should be resolved
        conflicts = manager.get_unresolved_conflicts()
        assert len(conflicts) == 0

        # Term should be updated
        job = manager.get_job_glossary()
        term = job.get_term("테스트")
        assert term.target_term == "test"
        assert term.source == TermSource.CONFIRMED
        assert term.confidence == TermConfidence.HIGH

    def test_promote_terms_to_user(self):
        """Test promoting job terms to user glossary."""
        manager = GlossaryManager()

        # Add and confirm some terms
        manager.add_extracted_term("용어1", "term1", unit_index=0)
        manager.add_extracted_term("용어2", "term2", unit_index=0)

        # Manually set one as confirmed
        job = manager.get_job_glossary()
        term1 = job.get_term("용어1")
        term1.source = TermSource.CONFIRMED
        term1.confidence = TermConfidence.HIGH

        # Promote
        promoted = manager.promote_job_terms_to_user()

        assert len(promoted) == 1
        assert promoted[0].source_term == "용어1"

    def test_to_prompt_format(self):
        """Test formatting merged glossary for prompt."""
        manager = GlossaryManager()

        job = manager.get_job_glossary()
        job.add_term(GlossaryTerm(
            source_term="안녕하세요",
            target_term="Hello",
            confidence=TermConfidence.HIGH,
        ))
        job.add_term(GlossaryTerm(
            source_term="감사합니다",
            target_term="Thank you",
            confidence=TermConfidence.MEDIUM,
        ))

        merged = manager.merge()
        prompt = merged.to_prompt_format()

        assert "| Korean | English | Confidence |" in prompt
        assert "안녕하세요" in prompt
        assert "Hello" in prompt
        assert "high" in prompt

    def test_serialization(self):
        """Test manager serialization."""
        manager = GlossaryManager()

        system = Glossary(name="system")
        system.add_term(GlossaryTerm(source_term="시스템", target_term="system"))
        manager.add_system_glossary(system)

        manager.add_extracted_term("테스트", "test", unit_index=0)

        data = manager.to_dict()
        restored = GlossaryManager.from_dict(data)

        merged = restored.merge()
        assert merged.get_translation("시스템") == "system"
        assert merged.get_translation("테스트") == "test"

