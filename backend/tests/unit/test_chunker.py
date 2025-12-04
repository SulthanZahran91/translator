"""Tests for tokenizer and chunker."""


from backend.translation.chunking.chunker import (
    ChunkingConfig,
    chunk_document,
    estimate_translation_units,
)
from backend.translation.chunking.tokenizer import Tokenizer, count_tokens
from backend.translation.ir import (
    Document,
    Paragraph,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
)


class TestTokenizer:
    """Tests for Tokenizer class."""

    def test_count_tokens_basic(self):
        """Test basic token counting."""
        tokenizer = Tokenizer()

        # Simple English text
        count = tokenizer.count_tokens("Hello, World!")
        assert count > 0
        assert count < 10  # Should be just a few tokens

    def test_count_tokens_korean(self):
        """Test token counting for Korean text."""
        tokenizer = Tokenizer()

        count = tokenizer.count_tokens("안녕하세요, 세계!")
        assert count > 0

    def test_count_tokens_empty(self):
        """Test counting tokens for empty string."""
        tokenizer = Tokenizer()

        assert tokenizer.count_tokens("") == 0
        assert tokenizer.count_tokens("   ") > 0  # Whitespace counts

    def test_encode_decode_roundtrip(self):
        """Test that encode/decode preserves text."""
        tokenizer = Tokenizer()

        text = "Hello, World! 안녕하세요!"
        tokens = tokenizer.encode(text)
        decoded = tokenizer.decode(tokens)

        assert decoded == text

    def test_truncate_to_tokens(self):
        """Test truncating text to token limit."""
        tokenizer = Tokenizer()

        text = "This is a longer piece of text that we want to truncate."
        truncated = tokenizer.truncate_to_tokens(text, 5)

        # Truncated text should be shorter
        assert len(truncated) < len(text)
        # But should have at most 5 tokens
        assert tokenizer.count_tokens(truncated) <= 5

    def test_split_by_tokens(self):
        """Test splitting text by token count."""
        tokenizer = Tokenizer()

        # Create text that's definitely more than 5 tokens
        text = "This is a test. Here is another sentence. And one more."
        chunks = tokenizer.split_by_tokens(text, 5)

        assert len(chunks) > 1
        for chunk in chunks:
            assert tokenizer.count_tokens(chunk) <= 5

    def test_convenience_function(self):
        """Test the count_tokens convenience function."""
        count = count_tokens("Hello, World!")
        assert count > 0


class TestChunker:
    """Tests for Chunker class."""

    def test_chunk_empty_document(self):
        """Test chunking an empty document."""
        doc = Document(sections=[Section(elements=[])])

        units = chunk_document(doc)

        assert len(units) == 0

    def test_chunk_single_paragraph(self):
        """Test chunking a document with one paragraph."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(runs=[TextRun(text="Hello, World!")]),
                ]),
            ]
        )

        units = chunk_document(doc)

        assert len(units) == 1
        assert "Hello, World!" in units[0].source_text

    def test_chunk_preserves_paragraph_id(self):
        """Test that paragraph IDs are preserved in source text."""
        para = Paragraph(id="para123", runs=[TextRun(text="Test content")])
        doc = Document(sections=[Section(elements=[para])])

        config = ChunkingConfig(include_element_ids=True)
        units = chunk_document(doc, config)

        assert len(units) == 1
        assert 'id="para123"' in units[0].source_text

    def test_chunk_multiple_paragraphs(self):
        """Test chunking multiple paragraphs."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(runs=[TextRun(text="First paragraph.")]),
                    Paragraph(runs=[TextRun(text="Second paragraph.")]),
                    Paragraph(runs=[TextRun(text="Third paragraph.")]),
                ]),
            ]
        )

        units = chunk_document(doc)

        # With default limits, all should fit in one unit
        assert len(units) >= 1

        # All paragraphs should be included
        all_text = " ".join(u.source_text for u in units)
        assert "First paragraph" in all_text
        assert "Second paragraph" in all_text
        assert "Third paragraph" in all_text

    def test_chunk_respects_token_limit(self):
        """Test that chunker respects token limit."""
        # Create a document with many paragraphs
        paragraphs = [
            Paragraph(runs=[TextRun(text=f"This is paragraph number {i}. " * 20)])
            for i in range(50)
        ]
        doc = Document(sections=[Section(elements=paragraphs)])

        # Use a small token limit
        config = ChunkingConfig(max_tokens_per_unit=500, min_tokens_per_unit=100)
        units = chunk_document(doc, config)

        # Should have multiple units
        assert len(units) > 1

        # Each unit should be under the limit
        tokenizer = Tokenizer()
        for unit in units:
            assert tokenizer.count_tokens(unit.source_text) <= 500 + 100  # Some tolerance

    def test_chunk_table(self):
        """Test chunking a table."""
        table = Table(
            rows=[
                TableRow(cells=[
                    TableCell(paragraphs=[Paragraph(runs=[TextRun(text="A1")])]),
                    TableCell(paragraphs=[Paragraph(runs=[TextRun(text="B1")])]),
                ]),
                TableRow(cells=[
                    TableCell(paragraphs=[Paragraph(runs=[TextRun(text="A2")])]),
                    TableCell(paragraphs=[Paragraph(runs=[TextRun(text="B2")])]),
                ]),
            ]
        )
        doc = Document(sections=[Section(elements=[table])])

        units = chunk_document(doc)

        assert len(units) >= 1
        assert "<table" in units[0].source_text
        assert "A1" in units[0].source_text
        assert "</table>" in units[0].source_text

    def test_chunk_mixed_content(self):
        """Test chunking with paragraphs and tables."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(runs=[TextRun(text="Introduction")]),
                    Table(rows=[
                        TableRow(cells=[
                            TableCell(paragraphs=[Paragraph(runs=[TextRun(text="Data")])]),
                        ]),
                    ]),
                    Paragraph(runs=[TextRun(text="Conclusion")]),
                ]),
            ]
        )

        units = chunk_document(doc)

        all_text = " ".join(u.source_text for u in units)
        assert "Introduction" in all_text
        assert "Data" in all_text
        assert "Conclusion" in all_text

    def test_element_refs_track_elements(self):
        """Test that element references are tracked."""
        para1 = Paragraph(id="p1", runs=[TextRun(text="First")])
        para2 = Paragraph(id="p2", runs=[TextRun(text="Second")])
        doc = Document(sections=[Section(elements=[para1, para2])])

        units = chunk_document(doc)

        assert len(units) >= 1

        # Collect all element IDs from refs
        all_ids = set()
        for unit in units:
            for ref in unit.element_refs:
                all_ids.add(ref.element_id)

        assert "p1" in all_ids
        assert "p2" in all_ids

    def test_sequence_numbers_assigned(self):
        """Test that sequence numbers are assigned correctly."""
        paragraphs = [
            Paragraph(runs=[TextRun(text="Content " * 100)])
            for _ in range(10)
        ]
        doc = Document(sections=[Section(elements=paragraphs)])

        config = ChunkingConfig(max_tokens_per_unit=200)
        units = chunk_document(doc, config)

        for i, unit in enumerate(units):
            assert unit.sequence_number == i


class TestEstimateTranslationUnits:
    """Tests for translation unit estimation."""

    def test_estimate_small_document(self):
        """Test estimating units for a small document."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(runs=[TextRun(text="Hello, World!")]),
                ]),
            ]
        )

        estimate = estimate_translation_units(doc)

        assert estimate >= 1

    def test_estimate_scales_with_content(self):
        """Test that estimate scales with content size."""
        small_doc = Document(
            sections=[Section(elements=[
                Paragraph(runs=[TextRun(text="Small content")])
            ])]
        )

        large_doc = Document(
            sections=[Section(elements=[
                Paragraph(runs=[TextRun(text="Large content " * 1000)])
            ])]
        )

        small_estimate = estimate_translation_units(small_doc)
        large_estimate = estimate_translation_units(large_doc)

        assert large_estimate >= small_estimate

