"""Regression test directly executing Section 4 expected values from handoff doc."""

import pytest
from securecode_context.pdf.parser import PdfParser
from securecode_context.pointers.source.readers import BoundedSourceReader

def test_d1_pdf_page_leak_prevention():
    """Verify D1: Reading page 1 must NOT contain text from page 2 or 3."""
    mock_pdf = b"%PDF-1.4\n/Type /Page\nBT (Page1_Secret_Text) ET\n/Type /Page\nBT (Page2_Leaked_Text) ET"
    parser = PdfParser()
    parsed_page1 = parser.parse_pages(mock_pdf, target_pages=[1])
    
    text_p1 = parsed_page1[0]["text"]
    assert "Page1_Secret_Text" in text_p1
    assert "Page2_Leaked_Text" not in text_p1

def test_d3_d5_workspace_escape_and_bounded_read():
    """Verify D3/D5: Out-of-workspace read prevention and bounded byte read."""
    class DummyRegistry:
        workspace_roots = {"ws1": "/tmp/workspace_safe"}
        def stat(self, ptr):
            class Desc:
                real_path = "/etc/passwd"
                mtime = 0
            return Desc()

    reader = BoundedSourceReader(registry=DummyRegistry())
    with pytest.raises(ValueError, match="WORKSPACE_ESCAPE_FORBIDDEN"):
        reader.read_range("securecode://source/ws1/escaped", 1, 10)
