"""Document chunker for creating translation units.

This module splits documents into translation units that fit within the
LLM's context window while respecting natural boundaries (sentences,
paragraphs, tables).
"""

import re
from dataclasses import dataclass

from backend.translation.chunking.tokenizer import get_tokenizer, Tokenizer
from backend.translation.ir import (
    Document,
    DocumentElement,
    ElementReference,
    Paragraph,
    Table,
    TranslationUnit,
)


@dataclass
class ChunkingConfig:
    """Configuration for document chunking."""
    max_tokens_per_unit: int = 25000
    min_tokens_per_unit: int = 1000  # Don't create tiny chunks
    table_token_threshold: int = 20000  # Split tables larger than this
    
    # Whether to include element metadata in source text
    include_element_ids: bool = True


class Chunker:
    """Document chunker that creates translation units.
    
    The chunker walks through the document and creates TranslationUnits
    that respect:
    - Token limits (max tokens per unit)
    - Natural boundaries (paragraphs, tables)
    - Sentence boundaries (never split mid-sentence)
    """
    
    def __init__(
        self,
        tokenizer: Tokenizer | None = None,
        config: ChunkingConfig | None = None,
    ) -> None:
        self._tokenizer = tokenizer or get_tokenizer()
        self._config = config or ChunkingConfig()
    
    def chunk_document(self, document: Document) -> list[TranslationUnit]:
        """Split document into translation units.
        
        Args:
            document: The document IR to chunk
            
        Returns:
            List of translation units ready for translation
        """
        units: list[TranslationUnit] = []
        
        # Collect all elements with their paths
        elements: list[tuple[DocumentElement, str]] = []
        
        for section_idx, section in enumerate(document.sections):
            for elem_idx, elem in enumerate(section.elements):
                path = f"section[{section_idx}]/element[{elem_idx}]"
                elements.append((elem, path))
        
        # Process elements into chunks
        current_unit = self._create_empty_unit(len(units))
        
        for elem, path in elements:
            if isinstance(elem, Paragraph):
                current_unit = self._add_paragraph_to_unit(
                    current_unit, elem, path, units
                )
            elif isinstance(elem, Table):
                current_unit = self._add_table_to_unit(
                    current_unit, elem, path, units
                )
        
        # Don't forget the last unit
        if current_unit.source_text.strip():
            units.append(current_unit)
        
        # Update sequence numbers
        for i, unit in enumerate(units):
            unit.sequence_number = i
        
        return units
    
    def _create_empty_unit(self, sequence: int) -> TranslationUnit:
        """Create an empty translation unit."""
        return TranslationUnit(
            source_text="",
            element_refs=[],
            source_token_count=0,
            sequence_number=sequence,
        )
    
    def _add_paragraph_to_unit(
        self,
        unit: TranslationUnit,
        paragraph: Paragraph,
        path: str,
        units: list[TranslationUnit],
    ) -> TranslationUnit:
        """Add a paragraph to the current unit or start a new one."""
        para_text = paragraph.text
        
        if not para_text.strip():
            return unit  # Skip empty paragraphs
        
        # Format the paragraph for translation
        if self._config.include_element_ids:
            formatted_text = f'<p id="{paragraph.id}">{para_text}</p>\n'
        else:
            formatted_text = f"{para_text}\n"
        
        para_tokens = self._tokenizer.count_tokens(formatted_text)
        
        # Check if adding this paragraph exceeds limit
        if unit.source_token_count + para_tokens > self._config.max_tokens_per_unit:
            if unit.source_text.strip():
                # Finalize current unit and start new one
                units.append(unit)
                unit = self._create_empty_unit(len(units))
        
        # Add paragraph to unit
        unit.source_text += formatted_text
        unit.source_token_count += para_tokens
        unit.element_refs.append(ElementReference(
            element_id=paragraph.id,
            element_type="paragraph",
            path=path,
        ))
        
        return unit
    
    def _add_table_to_unit(
        self,
        unit: TranslationUnit,
        table: Table,
        path: str,
        units: list[TranslationUnit],
    ) -> TranslationUnit:
        """Add a table to the current unit, potentially splitting large tables."""
        # Calculate total table tokens
        table_text = self._format_table(table)
        table_tokens = self._tokenizer.count_tokens(table_text)
        
        # If table is small enough and fits in current unit, add it whole
        if (table_tokens <= self._config.table_token_threshold and
            unit.source_token_count + table_tokens <= self._config.max_tokens_per_unit):
            unit.source_text += table_text
            unit.source_token_count += table_tokens
            unit.element_refs.append(ElementReference(
                element_id=table.id,
                element_type="table",
                path=path,
            ))
            return unit
        
        # If current unit has content, finalize it first
        if unit.source_text.strip():
            units.append(unit)
            unit = self._create_empty_unit(len(units))
        
        # If table is too large, split by rows
        if table_tokens > self._config.table_token_threshold:
            return self._split_table_to_units(table, path, unit, units)
        
        # Table fits in a fresh unit
        unit.source_text = table_text
        unit.source_token_count = table_tokens
        unit.element_refs.append(ElementReference(
            element_id=table.id,
            element_type="table",
            path=path,
        ))
        unit.context_hint = "table"
        
        return unit
    
    def _split_table_to_units(
        self,
        table: Table,
        path: str,
        unit: TranslationUnit,
        units: list[TranslationUnit],
    ) -> TranslationUnit:
        """Split a large table into multiple translation units by rows."""
        current_rows: list[str] = []
        current_tokens = 0
        
        for row_idx, row in enumerate(table.rows):
            row_text = self._format_table_row(table, row_idx)
            row_tokens = self._tokenizer.count_tokens(row_text)
            
            if current_tokens + row_tokens > self._config.max_tokens_per_unit:
                if current_rows:
                    # Finalize current chunk
                    table_chunk = self._wrap_table_rows(table, current_rows)
                    unit.source_text = table_chunk
                    unit.source_token_count = current_tokens
                    unit.element_refs.append(ElementReference(
                        element_id=table.id,
                        element_type="table",
                        path=path,
                    ))
                    unit.context_hint = "table (split)"
                    units.append(unit)
                    unit = self._create_empty_unit(len(units))
                    current_rows = []
                    current_tokens = 0
            
            current_rows.append(row_text)
            current_tokens += row_tokens
        
        # Handle remaining rows
        if current_rows:
            table_chunk = self._wrap_table_rows(table, current_rows)
            unit.source_text = table_chunk
            unit.source_token_count = current_tokens
            unit.element_refs.append(ElementReference(
                element_id=table.id,
                element_type="table",
                path=path,
            ))
            unit.context_hint = "table (split)"
        
        return unit
    
    def _format_table(self, table: Table) -> str:
        """Format a table for translation."""
        if self._config.include_element_ids:
            lines = [f'<table id="{table.id}">']
        else:
            lines = ["<table>"]
        
        for row_idx, row in enumerate(table.rows):
            lines.append(self._format_table_row(table, row_idx))
        
        lines.append("</table>\n")
        return "\n".join(lines)
    
    def _format_table_row(self, table: Table, row_idx: int) -> str:
        """Format a single table row."""
        row = table.rows[row_idx]
        cells: list[str] = []
        
        for cell in row.cells:
            cell_text = cell.text
            if self._config.include_element_ids:
                cells.append(f'<td id="{cell.id}">{cell_text}</td>')
            else:
                cells.append(f"<td>{cell_text}</td>")
        
        return f"<tr>{''.join(cells)}</tr>"
    
    def _wrap_table_rows(self, table: Table, rows: list[str]) -> str:
        """Wrap table rows in table tags."""
        if self._config.include_element_ids:
            header = f'<table id="{table.id}">'
        else:
            header = "<table>"
        
        return f"{header}\n" + "\n".join(rows) + "\n</table>\n"


def chunk_document(document: Document, config: ChunkingConfig | None = None) -> list[TranslationUnit]:
    """Convenience function to chunk a document.
    
    Args:
        document: The document IR to chunk
        config: Optional chunking configuration
        
    Returns:
        List of translation units
    """
    chunker = Chunker(config=config)
    return chunker.chunk_document(document)


def estimate_translation_units(document: Document, tokens_per_unit: int = 25000) -> int:
    """Estimate the number of translation units for a document.
    
    This is a quick estimate without full chunking.
    
    Args:
        document: The document to estimate
        tokens_per_unit: Target tokens per unit
        
    Returns:
        Estimated number of translation units
    """
    tokenizer = get_tokenizer()
    
    # Count total tokens
    total_tokens = 0
    for para in document.all_paragraphs:
        total_tokens += tokenizer.count_tokens(para.text)
    
    # Estimate units (add some overhead for markup)
    overhead_factor = 1.2
    adjusted_tokens = int(total_tokens * overhead_factor)
    
    return max(1, adjusted_tokens // tokens_per_unit)

