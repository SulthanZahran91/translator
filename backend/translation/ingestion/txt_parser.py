"""TXT document parser that converts plain text files to IR.

This module parses .txt files and converts them into our Intermediate
Representation (IR) format. Since TXT files have no formatting, we create
simple paragraphs with default styling.
"""

from pathlib import Path

from backend.translation.ir import (
    Document,
    Paragraph,
    Section,
    TextRun,
)


class TxtParser:
    """Parser for converting TXT files to IR format."""

    def parse(self, file_path: Path | str) -> Document:
        """Parse a TXT file and return the IR Document.

        Args:
            file_path: Path to the .txt file

        Returns:
            Document IR representing the parsed content
        """
        file_path = Path(file_path)
        content = file_path.read_text(encoding="utf-8")
        return self._parse_content(content, file_path.name)

    def parse_bytes(self, content: bytes, filename: str = "document.txt") -> Document:
        """Parse TXT content from bytes.

        Args:
            content: The TXT file content as bytes
            filename: Original filename for metadata

        Returns:
            Document IR representing the parsed content
        """
        # Try UTF-8 first, then fall back to other encodings
        text = self._decode_content(content)
        return self._parse_content(text, filename)

    def _decode_content(self, content: bytes) -> str:
        """Decode bytes content to string, trying multiple encodings."""
        encodings = ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"]
        for encoding in encodings:
            try:
                return content.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        # Last resort - decode with replacement
        return content.decode("utf-8", errors="replace")

    def _parse_content(self, text: str, filename: str) -> Document:
        """Parse text content into Document IR.

        Args:
            text: The text content
            filename: Original filename for metadata

        Returns:
            Document IR representing the parsed content
        """
        # Split into paragraphs based on blank lines
        paragraphs = []
        lines = text.split("\n")
        current_lines: list[str] = []

        for line in lines:
            if line.strip() == "":
                if current_lines:
                    # Create paragraph from accumulated lines
                    para_text = "\n".join(current_lines)
                    paragraphs.append(self._create_paragraph(para_text))
                    current_lines = []
            else:
                current_lines.append(line)

        # Don't forget the last paragraph
        if current_lines:
            para_text = "\n".join(current_lines)
            paragraphs.append(self._create_paragraph(para_text))

        # Create a single section containing all paragraphs
        section = Section(elements=paragraphs)

        return Document(
            sections=[section],
            styles={},
            source_filename=filename,
            source_format="txt",
        )

    def _create_paragraph(self, text: str) -> Paragraph:
        """Create a paragraph with a single text run.

        Args:
            text: The paragraph text

        Returns:
            Paragraph with a single TextRun
        """
        run = TextRun(text=text)
        return Paragraph(runs=[run])


def parse_txt(file_path: Path | str) -> Document:
    """Convenience function to parse a TXT file.

    Args:
        file_path: Path to the .txt file

    Returns:
        Document IR representing the parsed content
    """
    parser = TxtParser()
    return parser.parse(file_path)


def parse_txt_bytes(content: bytes, filename: str = "document.txt") -> Document:
    """Convenience function to parse TXT from bytes.

    Args:
        content: The TXT file content as bytes
        filename: Original filename for metadata

    Returns:
        Document IR representing the parsed content
    """
    parser = TxtParser()
    return parser.parse_bytes(content, filename)
