"""Document reconstructor for applying translations back to IR.

Takes the translated text from translation units and maps it back to
the original IR structure, preserving formatting while replacing content.
"""

import re
from dataclasses import dataclass

from backend.translation.ir import (
    Document,
    Paragraph,
    Table,
    TableCell,
    TextRun,
    TranslationUnit,
)


@dataclass
class ReconstructionResult:
    """Result of reconstruction."""
    document: Document
    elements_updated: int
    elements_failed: list[str]


class Reconstructor:
    """Reconstructs translated documents from IR and translation units."""

    def __init__(self) -> None:
        # Pattern to extract content from tagged paragraphs
        self._para_pattern = re.compile(
            r'<p\s+id="([^"]+)">(.*?)</p>',
            re.DOTALL,
        )

        # Pattern to extract content from tagged table cells
        self._cell_pattern = re.compile(
            r'<td\s+id="([^"]+)">(.*?)</td>',
            re.DOTALL,
        )

    def reconstruct(
        self,
        document: Document,
        units: list[TranslationUnit],
    ) -> ReconstructionResult:
        """Reconstruct document with translations.

        Args:
            document: The original document IR
            units: List of translated units

        Returns:
            ReconstructionResult with updated document
        """
        # Build lookup of translations by element ID
        translations = self._build_translation_lookup(units)

        # Track results
        elements_updated = 0
        elements_failed: list[str] = []

        # Walk through document and apply translations
        for section in document.sections:
            for elem in section.elements:
                if isinstance(elem, Paragraph):
                    if self._apply_paragraph_translation(elem, translations):
                        elements_updated += 1
                    elif elem.id in translations:
                        elements_failed.append(elem.id)
                elif isinstance(elem, Table):
                    updated, failed = self._apply_table_translation(elem, translations)
                    elements_updated += updated
                    elements_failed.extend(failed)

        return ReconstructionResult(
            document=document,
            elements_updated=elements_updated,
            elements_failed=elements_failed,
        )

    def _build_translation_lookup(
        self,
        units: list[TranslationUnit],
    ) -> dict[str, str]:
        """Build a lookup of element ID to translated text.

        Args:
            units: List of translated units

        Returns:
            Dict mapping element_id -> translated_text
        """
        translations: dict[str, str] = {}

        for unit in units:
            if not unit.translated_text:
                continue

            # Extract paragraph translations
            for match in self._para_pattern.finditer(unit.translated_text):
                elem_id = match.group(1)
                content = match.group(2).strip()
                translations[elem_id] = content

            # Extract cell translations
            for match in self._cell_pattern.finditer(unit.translated_text):
                elem_id = match.group(1)
                content = match.group(2).strip()
                translations[elem_id] = content

        return translations

    def _apply_paragraph_translation(
        self,
        paragraph: Paragraph,
        translations: dict[str, str],
    ) -> bool:
        """Apply translation to a paragraph.

        Args:
            paragraph: The paragraph to update
            translations: Translation lookup

        Returns:
            True if translation was applied
        """
        if paragraph.id not in translations:
            return False

        translated_text = translations[paragraph.id]

        if not paragraph.runs:
            # Create a new run with the translation
            paragraph.runs.append(TextRun(text=translated_text))
        elif len(paragraph.runs) == 1:
            # Simple case: single run, just replace text
            paragraph.runs[0].text = translated_text
        else:
            # Multiple runs: merge all text into first run's formatting
            # and clear subsequent runs
            paragraph.runs[0].text = translated_text
            for run in paragraph.runs[1:]:
                run.text = ""

        return True

    def _apply_table_translation(
        self,
        table: Table,
        translations: dict[str, str],
    ) -> tuple[int, list[str]]:
        """Apply translations to a table.

        Args:
            table: The table to update
            translations: Translation lookup

        Returns:
            Tuple of (elements_updated, failed_element_ids)
        """
        updated = 0
        failed: list[str] = []

        for row in table.rows:
            for cell in row.cells:
                if cell.id in translations:
                    if self._apply_cell_translation(cell, translations):
                        updated += 1
                    else:
                        failed.append(cell.id)
                else:
                    # Try to translate individual paragraphs in cell
                    for para in cell.paragraphs:
                        if self._apply_paragraph_translation(para, translations):
                            updated += 1
                        elif para.id in translations:
                            failed.append(para.id)

        return updated, failed

    def _apply_cell_translation(
        self,
        cell: TableCell,
        translations: dict[str, str],
    ) -> bool:
        """Apply translation to a table cell.

        Args:
            cell: The cell to update
            translations: Translation lookup

        Returns:
            True if translation was applied
        """
        if cell.id not in translations:
            return False

        translated_text = translations[cell.id]

        if not cell.paragraphs:
            # Create a new paragraph with the translation
            cell.paragraphs.append(
                Paragraph(runs=[TextRun(text=translated_text)])
            )
        elif len(cell.paragraphs) == 1:
            # Single paragraph: use paragraph translation logic
            if cell.paragraphs[0].runs:
                cell.paragraphs[0].runs[0].text = translated_text
                for run in cell.paragraphs[0].runs[1:]:
                    run.text = ""
            else:
                cell.paragraphs[0].runs.append(TextRun(text=translated_text))
        else:
            # Multiple paragraphs: merge into first
            if cell.paragraphs[0].runs:
                cell.paragraphs[0].runs[0].text = translated_text
                for run in cell.paragraphs[0].runs[1:]:
                    run.text = ""
            else:
                cell.paragraphs[0].runs.append(TextRun(text=translated_text))

            # Clear other paragraphs
            for para in cell.paragraphs[1:]:
                for run in para.runs:
                    run.text = ""

        return True


def reconstruct_document(
    document: Document,
    units: list[TranslationUnit],
) -> ReconstructionResult:
    """Convenience function to reconstruct a document.

    Args:
        document: The original document IR
        units: List of translated units

    Returns:
        ReconstructionResult with updated document
    """
    reconstructor = Reconstructor()
    return reconstructor.reconstruct(document, units)

