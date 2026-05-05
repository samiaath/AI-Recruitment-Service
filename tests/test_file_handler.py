import os
import pytest
from unittest.mock import patch, MagicMock
from ai_service.processing.file_handler import process_file

@pytest.mark.asyncio
async def test_process_file_not_exists():
    result = await process_file("nonexistent.pdf")
    assert result == ""

@pytest.mark.asyncio
@patch("ai_service.processing.file_handler.os.path.exists", return_value=True)
@patch("ai_service.processing.file_handler.extract_from_pdf", return_value="PDF TEXT")
async def test_process_file_pdf(mock_extract, mock_exists):
    result = await process_file("test.pdf")
    assert result == "PDF TEXT"
    mock_extract.assert_called_once_with("test.pdf")

@pytest.mark.asyncio
@patch("ai_service.processing.file_handler.os.path.exists", return_value=True)
@patch("ai_service.processing.file_handler.extract_from_docx", return_value="DOCX TEXT")
async def test_process_file_docx(mock_extract, mock_exists):
    result = await process_file("test.docx")
    assert result == "DOCX TEXT"
    mock_extract.assert_called_once_with("test.docx")

@pytest.mark.asyncio
@patch("ai_service.processing.file_handler.os.path.exists", return_value=True)
@patch("ai_service.processing.file_handler.extract_from_image", return_value="IMG TEXT")
async def test_process_file_image(mock_extract, mock_exists):
    result = await process_file("test.png")
    assert result == "IMG TEXT"
    mock_extract.assert_called_once_with("test.png")

@pytest.mark.asyncio
@patch("ai_service.processing.file_handler.os.path.exists", return_value=True)
async def test_process_file_unknown_ext(mock_exists):
    result = await process_file("test.txt")
    assert result == ""
