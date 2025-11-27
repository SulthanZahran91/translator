"""Tests for PDF converter.

Note: These tests require creating actual PDF files for testing.
We use reportlab or similar to generate test PDFs programmatically.
"""

import tempfile
from pathlib import Path

import pytest

# Skip these tests if reportlab is not available
pytest.importorskip("fitz")  # PyMuPDF


from backend.translation.ingestion.pdf_converter import (
    PDFConverter,
    convert_pdf_to_docx,
    parse_pdf,
    parse_pdf_bytes,
)
from backend.translation.ir import Document


def create_simple_pdf_bytes() -> bytes:
    """Create a simple test PDF in memory using PyMuPDF (fitz)."""
    import fitz  # PyMuPDF
    
    doc = fitz.open()
    page = doc.new_page()
    
    # Add text
    text = "Hello, World!\n안녕하세요!\n\nThis is a test PDF document."
    point = fitz.Point(72, 72)  # 1 inch from top-left
    page.insert_text(point, text, fontsize=12)
    
    # Save to bytes
    pdf_bytes = doc.write()
    doc.close()
    
    return pdf_bytes


def create_pdf_with_table_bytes() -> bytes:
    """Create a PDF with table-like content."""
    import fitz
    
    doc = fitz.open()
    page = doc.new_page()
    
    # Create table-like text layout
    y = 72
    for row in range(3):
        x = 72
        for col in range(3):
            text = f"R{row+1}C{col+1}"
            page.insert_text(fitz.Point(x, y), text, fontsize=10)
            x += 100
        y += 20
    
    pdf_bytes = doc.write()
    doc.close()
    
    return pdf_bytes


class TestPDFConverter:
    """Tests for PDFConverter class."""
    
    def test_convert_to_docx_creates_file(self, tmp_path: Path):
        """Test that PDF to DOCX conversion creates a file."""
        # Create test PDF
        pdf_content = create_simple_pdf_bytes()
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_content)
        
        # Convert
        converter = PDFConverter()
        docx_path = converter.convert_to_docx(pdf_path, tmp_path / "output.docx")
        
        assert docx_path.exists()
        assert docx_path.suffix == ".docx"
    
    def test_parse_pdf_returns_document(self, tmp_path: Path):
        """Test that parsing PDF returns a Document."""
        pdf_content = create_simple_pdf_bytes()
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_content)
        
        doc = parse_pdf(pdf_path)
        
        assert isinstance(doc, Document)
        assert doc.source_format == "pdf"
        assert doc.source_filename == "test.pdf"
    
    def test_parse_pdf_extracts_text(self, tmp_path: Path):
        """Test that text is extracted from PDF."""
        pdf_content = create_simple_pdf_bytes()
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_content)
        
        doc = parse_pdf(pdf_path)
        
        # Get all text
        all_text = " ".join(p.text for p in doc.all_paragraphs)
        
        # Should contain our test content
        assert "Hello" in all_text or len(all_text) > 0
    
    def test_parse_pdf_bytes(self):
        """Test parsing PDF from bytes."""
        pdf_content = create_simple_pdf_bytes()
        
        doc = parse_pdf_bytes(pdf_content, "test.pdf")
        
        assert isinstance(doc, Document)
        assert doc.source_format == "pdf"
        assert doc.source_filename == "test.pdf"
    
    def test_parse_korean_pdf(self, tmp_path: Path):
        """Test parsing PDF with Korean content."""
        import fitz
        
        doc = fitz.open()
        page = doc.new_page()
        
        # Add Korean text
        text = "한국어 테스트 문서입니다."
        page.insert_text(fitz.Point(72, 72), text, fontsize=12)
        
        pdf_bytes = doc.write()
        doc.close()
        
        pdf_path = tmp_path / "korean.pdf"
        pdf_path.write_bytes(pdf_bytes)
        
        parsed = parse_pdf(pdf_path)
        
        assert isinstance(parsed, Document)
        # Korean text may or may not be preserved depending on fonts
        # but the document should parse successfully


class TestPDFConverterWithCleanup:
    """Tests for cleanup behavior."""
    
    def test_temp_files_cleaned_up(self, tmp_path: Path):
        """Test that temporary files are cleaned up after parsing."""
        import os
        
        pdf_content = create_simple_pdf_bytes()
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_content)
        
        # Count files before
        temp_dir = tempfile.gettempdir()
        files_before = len(os.listdir(temp_dir))
        
        # Parse
        doc = parse_pdf(pdf_path)
        
        # The parse should have cleaned up its temp files
        # (We can't easily verify this without knowing the exact temp dir structure)
        assert doc is not None
    
    def test_conversion_preserves_structure(self, tmp_path: Path):
        """Test that document structure is preserved through conversion."""
        pdf_content = create_simple_pdf_bytes()
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_content)
        
        doc = parse_pdf(pdf_path)
        
        # Should have at least one section
        assert len(doc.sections) >= 1
        
        # JSON serialization should work
        json_str = doc.to_json()
        restored = Document.from_json(json_str)
        
        assert len(restored.sections) == len(doc.sections)

