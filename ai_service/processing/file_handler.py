import os
import asyncio
from .text_extractor import extract_from_pdf, extract_from_docx, extract_from_image

async def process_file(filepath: str) -> str:
    if not os.path.exists(filepath):
        return ""
    
    ext = filepath.lower().split('.')[-1]
    
    # Process text based on extension. OCR forms are disabled natively in extraction functions for performance.
    if ext == 'pdf':
        return await asyncio.to_thread(extract_from_pdf, filepath)
    elif ext in ['docx', 'doc']:
        return await asyncio.to_thread(extract_from_docx, filepath)
    elif ext in ['png', 'jpg', 'jpeg']:
        return await asyncio.to_thread(extract_from_image, filepath)
    return ""
