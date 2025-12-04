"""Intermediate Representation (IR) data structures for document translation.

These structures capture document formatting metadata while keeping text content
separate for translation. The LLM never sees the formatting details - only the
plain text is sent for translation, and the IR is used to reconstruct the
formatted document afterward.
"""

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Alignment(str, Enum):
    """Paragraph alignment options."""
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


@dataclass
class TextRun:
    """Smallest unit of text with consistent formatting.

    A TextRun represents a contiguous span of text that shares the same
    formatting properties (font, size, bold, italic, etc.).
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    text: str = ""

    # Font properties
    font_name: str | None = None
    font_size: float | None = None  # in points

    # Style properties
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False

    # Color (hex format, e.g., "FF0000" for red)
    color: str | None = None
    highlight_color: str | None = None

    # Additional properties
    superscript: bool = False
    subscript: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "text": self.text,
            "font_name": self.font_name,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "strike": self.strike,
            "color": self.color,
            "highlight_color": self.highlight_color,
            "superscript": self.superscript,
            "subscript": self.subscript,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextRun":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class Paragraph:
    """A paragraph containing one or more text runs.

    Paragraphs are the primary structural unit for text content. Each paragraph
    can contain multiple runs with different formatting.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    runs: list[TextRun] = field(default_factory=list)

    # Paragraph style
    style_name: str | None = None
    alignment: Alignment = Alignment.LEFT

    # Spacing (in points)
    space_before: float | None = None
    space_after: float | None = None
    line_spacing: float | None = None

    # Indentation (in inches)
    left_indent: float | None = None
    right_indent: float | None = None
    first_line_indent: float | None = None

    # Translation control - skip translation for paragraphs with inline images
    # to prevent deletion of image anchors (TRS 1.3 Image Guard Logic)
    skip_translation: bool = False

    @property
    def text(self) -> str:
        """Get the full text content of the paragraph."""
        return "".join(run.text for run in self.runs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "runs": [run.to_dict() for run in self.runs],
            "style_name": self.style_name,
            "alignment": self.alignment.value,
            "space_before": self.space_before,
            "space_after": self.space_after,
            "line_spacing": self.line_spacing,
            "left_indent": self.left_indent,
            "right_indent": self.right_indent,
            "first_line_indent": self.first_line_indent,
            "skip_translation": self.skip_translation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Paragraph":
        """Create from dictionary."""
        runs = [TextRun.from_dict(r) for r in data.pop("runs", [])]
        alignment = Alignment(data.pop("alignment", "left"))
        return cls(runs=runs, alignment=alignment, **data)


@dataclass
class TableCell:
    """A cell within a table, containing one or more paragraphs."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    paragraphs: list[Paragraph] = field(default_factory=list)

    # Cell dimensions
    width: float | None = None  # in inches

    # Spanning
    row_span: int = 1
    col_span: int = 1

    # Cell properties
    vertical_alignment: str | None = None  # "top", "center", "bottom"

    # Background color (hex)
    background_color: str | None = None

    @property
    def text(self) -> str:
        """Get the full text content of the cell."""
        return "\n".join(p.text for p in self.paragraphs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "paragraphs": [p.to_dict() for p in self.paragraphs],
            "width": self.width,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "vertical_alignment": self.vertical_alignment,
            "background_color": self.background_color,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TableCell":
        """Create from dictionary."""
        paragraphs = [Paragraph.from_dict(p) for p in data.pop("paragraphs", [])]
        return cls(paragraphs=paragraphs, **data)


@dataclass
class TableRow:
    """A row within a table."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    cells: list[TableCell] = field(default_factory=list)

    # Row properties
    height: float | None = None  # in inches
    is_header: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "cells": [c.to_dict() for c in self.cells],
            "height": self.height,
            "is_header": self.is_header,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TableRow":
        """Create from dictionary."""
        cells = [TableCell.from_dict(c) for c in data.pop("cells", [])]
        return cls(cells=cells, **data)


@dataclass
class Table:
    """A table structure with rows and cells."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    rows: list[TableRow] = field(default_factory=list)

    # Column widths (in inches)
    col_widths: list[float] = field(default_factory=list)

    # Table style
    style_name: str | None = None

    @property
    def num_rows(self) -> int:
        """Get the number of rows."""
        return len(self.rows)

    @property
    def num_cols(self) -> int:
        """Get the number of columns."""
        if not self.rows:
            return 0
        return len(self.rows[0].cells)

    def get_cell(self, row: int, col: int) -> TableCell | None:
        """Get a cell by row and column index."""
        if 0 <= row < len(self.rows) and 0 <= col < len(self.rows[row].cells):
            return self.rows[row].cells[col]
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "rows": [r.to_dict() for r in self.rows],
            "col_widths": self.col_widths,
            "style_name": self.style_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Table":
        """Create from dictionary."""
        rows = [TableRow.from_dict(r) for r in data.pop("rows", [])]
        return cls(rows=rows, **data)


class ImageType(str, Enum):
    """Type of image positioning."""
    INLINE = "inline"  # InlineShape - flows with text
    FLOATING = "floating"  # Anchored shape - positioned relative to page/paragraph


@dataclass
class Image:
    """An embedded image in the document.
    
    Supports both inline images (InlineShape) that flow with text and
    floating images (anchored shapes) that can be positioned freely.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    
    # Image data (base64 encoded)
    data: str = ""
    
    # Image format (e.g., "png", "jpeg", "gif")
    format: str = "png"
    
    # Dimensions (in inches)
    width: float | None = None
    height: float | None = None
    
    # Image type (inline or floating)
    image_type: ImageType = ImageType.INLINE
    
    # Positioning for floating images (in inches from page edge)
    position_x: float | None = None
    position_y: float | None = None
    
    # Alt text for accessibility  
    alt_text: str | None = None
    
    # Original relationship ID (for debugging/tracking)
    rel_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "data": self.data,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "image_type": self.image_type.value,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "alt_text": self.alt_text,
            "rel_id": self.rel_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Image":
        """Create from dictionary."""
        image_type = ImageType(data.pop("image_type", "inline"))
        return cls(image_type=image_type, **data)


# Type alias for document elements
DocumentElement = Paragraph | Table | Image


@dataclass
class Section:
    """A document section with its own page layout settings.

    Sections define page dimensions, margins, and contain the actual content
    elements (paragraphs and tables).
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    elements: list[DocumentElement] = field(default_factory=list)

    # Page dimensions (in inches)
    page_width: float | None = None
    page_height: float | None = None

    # Margins (in inches)
    margin_top: float | None = None
    margin_bottom: float | None = None
    margin_left: float | None = None
    margin_right: float | None = None

    # Headers and footers could be added here

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        elements_data = []
        for elem in self.elements:
            elem_dict = elem.to_dict()
            if isinstance(elem, Paragraph):
                elem_dict["_type"] = "paragraph"
            elif isinstance(elem, Table):
                elem_dict["_type"] = "table"
            elif isinstance(elem, Image):
                elem_dict["_type"] = "image"
            elements_data.append(elem_dict)

        return {
            "id": self.id,
            "elements": elements_data,
            "page_width": self.page_width,
            "page_height": self.page_height,
            "margin_top": self.margin_top,
            "margin_bottom": self.margin_bottom,
            "margin_left": self.margin_left,
            "margin_right": self.margin_right,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Section":
        """Create from dictionary."""
        elements_data = data.pop("elements", [])
        elements: list[DocumentElement] = []

        for elem_data in elements_data:
            elem_type = elem_data.pop("_type", "paragraph")
            if elem_type == "table":
                elements.append(Table.from_dict(elem_data))
            elif elem_type == "image":
                elements.append(Image.from_dict(elem_data))
            else:
                elements.append(Paragraph.from_dict(elem_data))

        return cls(elements=elements, **data)


@dataclass
class DocumentStyle:
    """A named style that can be referenced by paragraphs."""
    name: str
    base_style: str | None = None

    # Font defaults
    font_name: str | None = None
    font_size: float | None = None
    bold: bool = False
    italic: bool = False

    # Paragraph defaults
    alignment: Alignment = Alignment.LEFT
    space_before: float | None = None
    space_after: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "base_style": self.base_style,
            "font_name": self.font_name,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "alignment": self.alignment.value,
            "space_before": self.space_before,
            "space_after": self.space_after,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentStyle":
        """Create from dictionary."""
        alignment = Alignment(data.pop("alignment", "left"))
        return cls(alignment=alignment, **data)


@dataclass
class Document:
    """Root container for the entire document.

    A Document contains sections, each of which can have different page layouts.
    It also stores named styles that can be referenced throughout.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    sections: list[Section] = field(default_factory=list)
    styles: dict[str, DocumentStyle] = field(default_factory=dict)

    # Metadata
    source_filename: str | None = None
    source_format: str | None = None  # "docx", "pdf"

    @property
    def all_paragraphs(self) -> list[Paragraph]:
        """Get all paragraphs in the document."""
        paragraphs: list[Paragraph] = []
        for section in self.sections:
            for elem in section.elements:
                if isinstance(elem, Paragraph):
                    paragraphs.append(elem)
                elif isinstance(elem, Table):
                    for row in elem.rows:
                        for cell in row.cells:
                            paragraphs.extend(cell.paragraphs)
        return paragraphs

    @property
    def all_tables(self) -> list[Table]:
        """Get all tables in the document."""
        tables: list[Table] = []
        for section in self.sections:
            for elem in section.elements:
                if isinstance(elem, Table):
                    tables.append(elem)
        return tables

    def get_element_by_id(self, element_id: str) -> DocumentElement | TextRun | TableCell | None:
        """Find an element by its ID."""
        for section in self.sections:
            for elem in section.elements:
                if isinstance(elem, Paragraph):
                    if elem.id == element_id:
                        return elem
                    for run in elem.runs:
                        if run.id == element_id:
                            return run
                elif isinstance(elem, Table):
                    if elem.id == element_id:
                        return elem
                    for row in elem.rows:
                        for cell in row.cells:
                            if cell.id == element_id:
                                return cell
                            for para in cell.paragraphs:
                                if para.id == element_id:
                                    return para
                                for run in para.runs:
                                    if run.id == element_id:
                                        return run
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "sections": [s.to_dict() for s in self.sections],
            "styles": {name: style.to_dict() for name, style in self.styles.items()},
            "source_filename": self.source_filename,
            "source_format": self.source_format,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        """Create from dictionary."""
        sections = [Section.from_dict(s) for s in data.pop("sections", [])]
        styles_data = data.pop("styles", {})
        styles = {name: DocumentStyle.from_dict(s) for name, s in styles_data.items()}
        return cls(sections=sections, styles=styles, **data)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Document":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class ElementReference:
    """Reference to an element in the IR that should be translated."""
    element_id: str
    element_type: str  # "paragraph", "cell", "run"
    path: str  # human-readable path like "section[0]/para[5]"


@dataclass
class TranslationUnit:
    """A chunk of text that will be sent to the LLM for translation.

    Translation units aggregate content from potentially multiple elements
    while respecting chunk size limits. The element_refs track which parts
    of the original IR this unit covers for reconstruction.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    # The source text (Korean) to be translated
    source_text: str = ""

    # References to the original IR elements covered by this unit
    element_refs: list[ElementReference] = field(default_factory=list)

    # Context hint for the LLM (e.g., "table content", "heading", etc.)
    context_hint: str | None = None

    # The translated text (English) - populated after translation
    translated_text: str | None = None

    # Token counts for budgeting
    source_token_count: int = 0

    # Order in the document
    sequence_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "source_text": self.source_text,
            "element_refs": [
                {"element_id": ref.element_id, "element_type": ref.element_type, "path": ref.path}
                for ref in self.element_refs
            ],
            "context_hint": self.context_hint,
            "translated_text": self.translated_text,
            "source_token_count": self.source_token_count,
            "sequence_number": self.sequence_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranslationUnit":
        """Create from dictionary."""
        refs_data = data.pop("element_refs", [])
        element_refs = [
            ElementReference(
                element_id=r["element_id"],
                element_type=r["element_type"],
                path=r["path"],
            )
            for r in refs_data
        ]
        return cls(element_refs=element_refs, **data)

