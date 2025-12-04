"""PDF to DOCX converter for document ingestion.

This module converts PDF files to DOCX format using pdf2docx, which preserves
layout and formatting reasonably well. The converted DOCX is then parsed
using our standard DOCX parser.
"""

import tempfile
from pathlib import Path

from pdf2docx import Converter

from backend.translation.ingestion.docx_parser import parse_docx
from backend.translation.ir import Document


class PDFConverter:
    """Converter for PDF files to DOCX and then to IR."""

    def __init__(self) -> None:
        self._temp_dir: Path | None = None

    def convert_to_docx(self, pdf_path: Path | str, output_path: Path | str | None = None) -> Path:
        """Convert a PDF file to DOCX format.

        Args:
            pdf_path: Path to the input PDF file
            output_path: Optional path for the output DOCX file.
                        If not provided, a temporary file is created.

        Returns:
            Path to the generated DOCX file
        """
        pdf_path = Path(pdf_path)

        if output_path is None:
            # Create temporary output file
            temp_dir = tempfile.mkdtemp()
            output_path = Path(temp_dir) / f"{pdf_path.stem}.docx"
        else:
            output_path = Path(output_path)

        # Convert PDF to DOCX
        cv = Converter(str(pdf_path))
        try:
            cv.convert(str(output_path))
        finally:
            cv.close()

        return output_path

    def convert_bytes_to_docx(self, pdf_content: bytes, filename: str = "document.pdf") -> tuple[bytes, Path | None]:
        """Convert PDF content from bytes to DOCX.

        Args:
            pdf_content: PDF file content as bytes
            filename: Original filename for reference

        Returns:
            Tuple of (DOCX content as bytes, temporary path or None)
        """
        # Use TemporaryDirectory for automatic cleanup
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / filename
            docx_path = Path(temp_dir) / f"{Path(filename).stem}.docx"

            pdf_path.write_bytes(pdf_content)

            # Convert
            cv = Converter(str(pdf_path))
            try:
                cv.convert(str(docx_path))
            finally:
                cv.close()

            docx_content = docx_path.read_bytes()
            # Path is no longer valid after context exit, so return None
            return docx_content, None

    def parse(self, pdf_path: Path | str) -> Document:
        """Convert PDF to DOCX and parse to IR.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Document IR representing the parsed content
        """
        pdf_path = Path(pdf_path)

        # Convert to DOCX in temp location
        docx_path = self.convert_to_docx(pdf_path)

        try:
            # Parse the DOCX
            doc = parse_docx(docx_path)

            # Update metadata to reflect original format
            doc.source_filename = pdf_path.name
            doc.source_format = "pdf"

            return doc
        finally:
            # Clean up temp file
            if docx_path.exists():
                docx_path.unlink()
            if docx_path.parent.exists() and docx_path.parent.name.startswith("tmp"):
                try:
                    docx_path.parent.rmdir()
                except OSError:
                    pass  # Directory not empty or other issue

    def parse_bytes(self, pdf_content: bytes, filename: str = "document.pdf") -> Document:
        """Convert PDF bytes to DOCX and parse to IR.

        Args:
            pdf_content: PDF file content as bytes
            filename: Original filename for metadata

        Returns:
            Document IR representing the parsed content
        """
        docx_content, docx_path = self.convert_bytes_to_docx(pdf_content, filename)

        try:
            from backend.translation.ingestion.docx_parser import parse_docx_bytes

            doc = parse_docx_bytes(docx_content, filename.replace(".pdf", ".docx"))

            # Update metadata
            doc.source_filename = filename
            doc.source_format = "pdf"

            return doc
        finally:
            # Clean up if path is provided
            if docx_path:
                if docx_path.exists():
                    docx_path.unlink()
                pdf_path = docx_path.parent / filename
                if pdf_path.exists():
                    pdf_path.unlink()
                if docx_path.parent.exists():
                    try:
                        docx_path.parent.rmdir()
                    except OSError:
                        pass


def convert_pdf_to_docx(pdf_path: Path | str, output_path: Path | str | None = None) -> Path:
    """Convenience function to convert PDF to DOCX.

    Args:
        pdf_path: Path to the input PDF file
        output_path: Optional path for the output DOCX file

    Returns:
        Path to the generated DOCX file
    """
    converter = PDFConverter()
    return converter.convert_to_docx(pdf_path, output_path)


def parse_pdf(pdf_path: Path | str) -> Document:
    """Convenience function to parse a PDF file to IR.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Document IR representing the parsed content
    """
    converter = PDFConverter()
    return converter.parse(pdf_path)


def parse_pdf_bytes(pdf_content: bytes, filename: str = "document.pdf") -> Document:
    """Convenience function to parse PDF bytes to IR.

    Args:
        pdf_content: PDF file content as bytes
        filename: Original filename for metadata

    Returns:
        Document IR representing the parsed content
    """
    converter = PDFConverter()
    return converter.parse_bytes(pdf_content, filename)

