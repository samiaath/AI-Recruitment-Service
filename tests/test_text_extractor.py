import pytest
import os
from ai_service.processing.text_extractor import extract_from_image

def test_extract_from_image_disabled():
    # extract_from_image is disabled for performance, so it should return an empty string
    res = extract_from_image("dummy_path.png")
    assert res == ""
    
# We could mock pdfplumber and docx for PDF and DOCX tests, but since they require actual files
# or mocking libraries (like unittest.mock), here's a simple test to verify they don't break
# on non-existent files when catching exceptions.

from ai_service.processing.text_extractor import extract_from_pdf, extract_from_docx

def test_extract_from_pdf_missing_file():
    res = extract_from_pdf("non_existent_file.pdf")
    # Due to try...except, it returns empty string instead of raising exception directly up
    assert res == ""

def test_extract_from_docx_missing_file():
    res = extract_from_docx("non_existent_file.docx")
    assert res == ""
