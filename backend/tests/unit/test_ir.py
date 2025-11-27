"""Tests for Intermediate Representation data structures."""

import json

import pytest

from backend.translation.ir import (
    Alignment,
    Document,
    DocumentStyle,
    ElementReference,
    Paragraph,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
    TranslationUnit,
)


class TestTextRun:
    """Tests for TextRun class."""
    
    def test_create_text_run(self):
        """Test creating a basic text run."""
        run = TextRun(text="Hello, World!")
        
        assert run.text == "Hello, World!"
        assert run.font_name is None
        assert run.bold is False
        assert run.id is not None
    
    def test_create_styled_run(self):
        """Test creating a styled text run."""
        run = TextRun(
            text="Important",
            font_name="Arial",
            font_size=14.0,
            bold=True,
            italic=True,
            color="FF0000",
        )
        
        assert run.bold is True
        assert run.italic is True
        assert run.font_name == "Arial"
        assert run.color == "FF0000"
    
    def test_text_run_serialization(self):
        """Test TextRun to_dict and from_dict."""
        original = TextRun(
            text="Test",
            font_name="Times New Roman",
            bold=True,
        )
        
        data = original.to_dict()
        restored = TextRun.from_dict(data)
        
        assert restored.text == original.text
        assert restored.font_name == original.font_name
        assert restored.bold == original.bold
        assert restored.id == original.id


class TestParagraph:
    """Tests for Paragraph class."""
    
    def test_create_paragraph(self):
        """Test creating a paragraph with runs."""
        para = Paragraph(
            runs=[
                TextRun(text="Hello, "),
                TextRun(text="World!", bold=True),
            ]
        )
        
        assert len(para.runs) == 2
        assert para.text == "Hello, World!"
    
    def test_paragraph_alignment(self):
        """Test paragraph alignment."""
        para = Paragraph(alignment=Alignment.CENTER)
        assert para.alignment == Alignment.CENTER
    
    def test_paragraph_serialization(self):
        """Test Paragraph serialization."""
        original = Paragraph(
            runs=[TextRun(text="Test paragraph")],
            style_name="Heading1",
            alignment=Alignment.RIGHT,
            space_before=12.0,
        )
        
        data = original.to_dict()
        restored = Paragraph.from_dict(data)
        
        assert restored.text == original.text
        assert restored.style_name == original.style_name
        assert restored.alignment == Alignment.RIGHT
        assert restored.space_before == 12.0


class TestTable:
    """Tests for Table class."""
    
    def test_create_table(self):
        """Test creating a simple table."""
        cell1 = TableCell(paragraphs=[Paragraph(runs=[TextRun(text="A1")])])
        cell2 = TableCell(paragraphs=[Paragraph(runs=[TextRun(text="B1")])])
        row = TableRow(cells=[cell1, cell2])
        table = Table(rows=[row])
        
        assert table.num_rows == 1
        assert table.num_cols == 2
        assert table.get_cell(0, 0).text == "A1"
        assert table.get_cell(0, 1).text == "B1"
    
    def test_table_with_spanning(self):
        """Test table with cell spanning."""
        cell = TableCell(
            paragraphs=[Paragraph(runs=[TextRun(text="Merged")])],
            row_span=2,
            col_span=2,
        )
        
        assert cell.row_span == 2
        assert cell.col_span == 2
    
    def test_table_serialization(self):
        """Test table serialization."""
        table = Table(
            rows=[
                TableRow(cells=[
                    TableCell(paragraphs=[Paragraph(runs=[TextRun(text="Data")])]),
                ]),
            ],
            col_widths=[2.5],
        )
        
        data = table.to_dict()
        restored = Table.from_dict(data)
        
        assert restored.num_rows == 1
        assert restored.num_cols == 1
        assert restored.get_cell(0, 0).text == "Data"
        assert restored.col_widths == [2.5]


class TestSection:
    """Tests for Section class."""
    
    def test_create_section(self):
        """Test creating a section with elements."""
        section = Section(
            elements=[
                Paragraph(runs=[TextRun(text="Intro paragraph")]),
                Table(rows=[TableRow(cells=[TableCell()])]),
                Paragraph(runs=[TextRun(text="Conclusion")]),
            ],
            page_width=8.5,
            page_height=11.0,
            margin_top=1.0,
        )
        
        assert len(section.elements) == 3
        assert section.page_width == 8.5
    
    def test_section_serialization(self):
        """Test section serialization preserves element types."""
        section = Section(
            elements=[
                Paragraph(runs=[TextRun(text="Text")]),
                Table(rows=[TableRow(cells=[TableCell()])]),
            ]
        )
        
        data = section.to_dict()
        restored = Section.from_dict(data)
        
        assert len(restored.elements) == 2
        assert isinstance(restored.elements[0], Paragraph)
        assert isinstance(restored.elements[1], Table)


class TestDocument:
    """Tests for Document class."""
    
    def test_create_document(self):
        """Test creating a complete document."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(runs=[TextRun(text="Chapter 1")]),
                ]),
            ],
            source_filename="test.docx",
            source_format="docx",
        )
        
        assert len(doc.sections) == 1
        assert doc.source_filename == "test.docx"
    
    def test_all_paragraphs(self):
        """Test getting all paragraphs including from tables."""
        doc = Document(
            sections=[
                Section(elements=[
                    Paragraph(runs=[TextRun(text="Para 1")]),
                    Table(rows=[TableRow(cells=[
                        TableCell(paragraphs=[
                            Paragraph(runs=[TextRun(text="Table para")]),
                        ]),
                    ])]),
                    Paragraph(runs=[TextRun(text="Para 2")]),
                ]),
            ]
        )
        
        all_paras = doc.all_paragraphs
        assert len(all_paras) == 3
        texts = [p.text for p in all_paras]
        assert "Para 1" in texts
        assert "Table para" in texts
        assert "Para 2" in texts
    
    def test_get_element_by_id(self):
        """Test finding elements by ID."""
        para = Paragraph(id="para1", runs=[TextRun(id="run1", text="Hello")])
        doc = Document(sections=[Section(elements=[para])])
        
        found_para = doc.get_element_by_id("para1")
        assert found_para == para
        
        found_run = doc.get_element_by_id("run1")
        assert found_run.text == "Hello"
        
        not_found = doc.get_element_by_id("nonexistent")
        assert not_found is None
    
    def test_document_json_roundtrip(self):
        """Test full JSON serialization roundtrip."""
        original = Document(
            sections=[
                Section(
                    elements=[
                        Paragraph(
                            runs=[
                                TextRun(text="Hello, ", bold=True),
                                TextRun(text="세계!", font_name="NanumGothic"),
                            ],
                            alignment=Alignment.CENTER,
                        ),
                        Table(rows=[
                            TableRow(cells=[
                                TableCell(paragraphs=[
                                    Paragraph(runs=[TextRun(text="Cell 1")]),
                                ]),
                                TableCell(paragraphs=[
                                    Paragraph(runs=[TextRun(text="Cell 2")]),
                                ]),
                            ]),
                        ]),
                    ],
                    page_width=8.5,
                    page_height=11.0,
                ),
            ],
            styles={
                "Heading1": DocumentStyle(
                    name="Heading1",
                    font_size=24.0,
                    bold=True,
                ),
            },
            source_filename="test.docx",
            source_format="docx",
        )
        
        # Serialize to JSON
        json_str = original.to_json()
        
        # Verify it's valid JSON with Korean characters
        assert "세계" in json_str
        
        # Deserialize back
        restored = Document.from_json(json_str)
        
        # Verify structure
        assert len(restored.sections) == 1
        assert len(restored.sections[0].elements) == 2
        assert restored.source_filename == "test.docx"
        
        # Verify paragraph content
        para = restored.sections[0].elements[0]
        assert isinstance(para, Paragraph)
        assert para.text == "Hello, 세계!"
        assert para.alignment == Alignment.CENTER
        assert para.runs[0].bold is True
        
        # Verify table content
        table = restored.sections[0].elements[1]
        assert isinstance(table, Table)
        assert table.num_rows == 1
        assert table.num_cols == 2
        
        # Verify styles
        assert "Heading1" in restored.styles
        assert restored.styles["Heading1"].font_size == 24.0


class TestTranslationUnit:
    """Tests for TranslationUnit class."""
    
    def test_create_translation_unit(self):
        """Test creating a translation unit."""
        unit = TranslationUnit(
            source_text="안녕하세요, 세계!",
            element_refs=[
                ElementReference(
                    element_id="para1",
                    element_type="paragraph",
                    path="section[0]/para[0]",
                ),
            ],
            context_hint="greeting",
            source_token_count=10,
            sequence_number=0,
        )
        
        assert unit.source_text == "안녕하세요, 세계!"
        assert len(unit.element_refs) == 1
        assert unit.translated_text is None
    
    def test_translation_unit_after_translation(self):
        """Test translation unit with translated content."""
        unit = TranslationUnit(
            source_text="안녕하세요",
            translated_text="Hello",
        )
        
        assert unit.translated_text == "Hello"
    
    def test_translation_unit_serialization(self):
        """Test translation unit serialization."""
        original = TranslationUnit(
            source_text="테스트",
            element_refs=[
                ElementReference(
                    element_id="p1",
                    element_type="paragraph",
                    path="section[0]/para[0]",
                ),
            ],
            translated_text="Test",
            source_token_count=5,
            sequence_number=1,
        )
        
        data = original.to_dict()
        restored = TranslationUnit.from_dict(data)
        
        assert restored.source_text == original.source_text
        assert restored.translated_text == original.translated_text
        assert len(restored.element_refs) == 1
        assert restored.element_refs[0].element_id == "p1"
        assert restored.sequence_number == 1

