"""Tests for document reconstructor."""

import pytest

from backend.translation.reconstruction.reconstructor import (
    Reconstructor,
    reconstruct_document,
)
from backend.translation.ir import (
    Document,
    Paragraph,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
    TranslationUnit,
    ElementReference,
)


class TestReconstructor:
    """Tests for Reconstructor class."""
    
    def test_reconstruct_single_paragraph(self):
        """Test reconstructing a single paragraph."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(id="p1", runs=[TextRun(text="안녕하세요")]),
                ]),
            ]
        )
        
        units = [
            TranslationUnit(
                source_text='<p id="p1">안녕하세요</p>',
                translated_text='<p id="p1">Hello</p>',
                element_refs=[ElementReference(
                    element_id="p1",
                    element_type="paragraph",
                    path="section[0]/element[0]",
                )],
            ),
        ]
        
        result = reconstruct_document(doc, units)
        
        assert result.elements_updated == 1
        assert len(result.elements_failed) == 0
        assert doc.sections[0].elements[0].text == "Hello"
    
    def test_reconstruct_multiple_paragraphs(self):
        """Test reconstructing multiple paragraphs."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(id="p1", runs=[TextRun(text="첫 번째")]),
                    Paragraph(id="p2", runs=[TextRun(text="두 번째")]),
                ]),
            ]
        )
        
        units = [
            TranslationUnit(
                translated_text='<p id="p1">First</p>\n<p id="p2">Second</p>',
            ),
        ]
        
        result = reconstruct_document(doc, units)
        
        assert result.elements_updated == 2
        assert doc.sections[0].elements[0].text == "First"
        assert doc.sections[0].elements[1].text == "Second"
    
    def test_reconstruct_preserves_formatting(self):
        """Test that formatting is preserved during reconstruction."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(
                        id="p1",
                        runs=[
                            TextRun(text="Bold ", bold=True),
                            TextRun(text="Normal", bold=False),
                        ]
                    ),
                ]),
            ]
        )
        
        units = [
            TranslationUnit(
                translated_text='<p id="p1">Translated text here</p>',
            ),
        ]
        
        result = reconstruct_document(doc, units)
        
        # Text should be updated
        para = doc.sections[0].elements[0]
        assert para.runs[0].text == "Translated text here"
        # Formatting should be preserved on first run
        assert para.runs[0].bold is True
        # Subsequent runs should be emptied
        assert para.runs[1].text == ""
    
    def test_reconstruct_table(self):
        """Test reconstructing a table."""
        doc = Document(
            sections=[
                Section(elements=[
                    Table(
                        id="t1",
                        rows=[
                            TableRow(cells=[
                                TableCell(
                                    id="c1",
                                    paragraphs=[
                                        Paragraph(id="cp1", runs=[TextRun(text="셀1")])
                                    ]
                                ),
                                TableCell(
                                    id="c2",
                                    paragraphs=[
                                        Paragraph(id="cp2", runs=[TextRun(text="셀2")])
                                    ]
                                ),
                            ]),
                        ]
                    ),
                ]),
            ]
        )
        
        units = [
            TranslationUnit(
                translated_text='<table id="t1"><tr><td id="c1">Cell1</td><td id="c2">Cell2</td></tr></table>',
            ),
        ]
        
        result = reconstruct_document(doc, units)
        
        table = doc.sections[0].elements[0]
        assert table.get_cell(0, 0).text == "Cell1"
        assert table.get_cell(0, 1).text == "Cell2"
    
    def test_reconstruct_mixed_content(self):
        """Test reconstructing document with paragraphs and tables."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(id="intro", runs=[TextRun(text="소개")]),
                    Table(
                        id="data",
                        rows=[
                            TableRow(cells=[
                                TableCell(
                                    id="cell1",
                                    paragraphs=[
                                        Paragraph(runs=[TextRun(text="데이터")])
                                    ]
                                ),
                            ]),
                        ]
                    ),
                    Paragraph(id="outro", runs=[TextRun(text="결론")]),
                ]),
            ]
        )
        
        units = [
            TranslationUnit(
                translated_text='''
                <p id="intro">Introduction</p>
                <table id="data"><tr><td id="cell1">Data</td></tr></table>
                <p id="outro">Conclusion</p>
                ''',
            ),
        ]
        
        result = reconstruct_document(doc, units)
        
        assert result.elements_updated >= 3
        assert doc.sections[0].elements[0].text == "Introduction"
        table = doc.sections[0].elements[1]
        assert table.get_cell(0, 0).text == "Data"
        assert doc.sections[0].elements[2].text == "Conclusion"
    
    def test_reconstruct_handles_missing_translation(self):
        """Test that missing translations are tracked."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(id="p1", runs=[TextRun(text="번역됨")]),
                    Paragraph(id="p2", runs=[TextRun(text="안 번역됨")]),
                ]),
            ]
        )
        
        units = [
            TranslationUnit(
                translated_text='<p id="p1">Translated</p>',
                # Note: p2 is not in the translation
            ),
        ]
        
        result = reconstruct_document(doc, units)
        
        assert result.elements_updated == 1
        # p2 should still have original text
        assert doc.sections[0].elements[1].text == "안 번역됨"
    
    def test_reconstruct_multiple_units(self):
        """Test reconstructing from multiple translation units."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(id="p1", runs=[TextRun(text="문단1")]),
                    Paragraph(id="p2", runs=[TextRun(text="문단2")]),
                    Paragraph(id="p3", runs=[TextRun(text="문단3")]),
                ]),
            ]
        )
        
        units = [
            TranslationUnit(
                translated_text='<p id="p1">Paragraph 1</p>',
                sequence_number=0,
            ),
            TranslationUnit(
                translated_text='<p id="p2">Paragraph 2</p>\n<p id="p3">Paragraph 3</p>',
                sequence_number=1,
            ),
        ]
        
        result = reconstruct_document(doc, units)
        
        assert result.elements_updated == 3
        assert doc.sections[0].elements[0].text == "Paragraph 1"
        assert doc.sections[0].elements[1].text == "Paragraph 2"
        assert doc.sections[0].elements[2].text == "Paragraph 3"

