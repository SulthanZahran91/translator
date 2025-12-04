"""PDF writer for exporting translated documents.

Converts DOCX to PDF using LibreOffice in headless mode.
Falls back to just returning DOCX if LibreOffice is not available.
"""

import subprocess
import tempfile
from pathlib import Path

from backend.translation.export.docx_writer import write_docx
from backend.translation.ir import Document


class PDFWriter:
    """Writes documents to PDF via DOCX conversion."""

    def __init__(self) -> None:
        self._libreoffice_path: str | None = None
        self._check_libreoffice()

    def _check_libreoffice(self) -> None:
        """Check if LibreOffice is available."""
        # Common paths for LibreOffice
        paths = [
            "libreoffice",
            "soffice",
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            "/usr/bin/libreoffice",
            "/usr/bin/soffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        ]

        for path in paths:
            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self._libreoffice_path = path
                    return
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                continue

    @property
    def is_available(self) -> bool:
        """Check if PDF conversion is available."""
        return self._libreoffice_path is not None

    def write(self, document: Document, output_path: Path | str) -> Path:
        """Write document to PDF.

        Args:
            document: The document IR to write
            output_path: Path to save the PDF file

        Returns:
            Path to the written file

        Raises:
            RuntimeError: If LibreOffice is not available
        """
        output_path = Path(output_path)

        if not self.is_available:
            raise RuntimeError(
                "LibreOffice is not available for PDF conversion. "
                "Install LibreOffice or use DOCX export instead."
            )

        # First write to DOCX
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_docx = Path(temp_dir) / "temp.docx"
            write_docx(document, temp_docx)

            # Convert to PDF using LibreOffice
            self._convert_to_pdf(temp_docx, output_path.parent)

            # LibreOffice creates file with same name but .pdf extension
            temp_pdf = output_path.parent / "temp.pdf"

            if temp_pdf.exists():
                temp_pdf.rename(output_path)
            else:
                raise RuntimeError("PDF conversion failed - no output file created")

        return output_path

    def write_bytes(self, document: Document) -> bytes:
        """Write document to PDF bytes.

        Args:
            document: The document IR to write

        Returns:
            PDF file content as bytes
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.pdf"
            self.write(document, output_path)
            return output_path.read_bytes()

    def _convert_to_pdf(self, input_path: Path, output_dir: Path) -> None:
        """Convert DOCX to PDF using LibreOffice.

        Args:
            input_path: Path to the input DOCX file
            output_dir: Directory to save the output PDF
        """
        if not self._libreoffice_path:
            raise RuntimeError("LibreOffice not available")

        cmd = [
            self._libreoffice_path,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_dir),
            str(input_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=120,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"LibreOffice conversion failed: {stderr}")


def write_pdf(document: Document, output_path: Path | str) -> Path:
    """Convenience function to write a document to PDF.

    Args:
        document: The document IR to write
        output_path: Path to save the PDF file

    Returns:
        Path to the written file
    """
    writer = PDFWriter()
    return writer.write(document, output_path)


def write_pdf_bytes(document: Document) -> bytes:
    """Convenience function to write a document to PDF bytes.

    Args:
        document: The document IR to write

    Returns:
        PDF file content as bytes
    """
    writer = PDFWriter()
    return writer.write_bytes(document)


def is_pdf_export_available() -> bool:
    """Check if PDF export is available."""
    writer = PDFWriter()
    return writer.is_available

