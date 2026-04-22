import os
from .text_extractor import extract_from_pdf, extract_from_docx, extract_from_image

def process_file(filepath: str) -> str:
    if not os.path.exists(filepath):
        return ""
    
    ext = filepath.lower().split('.')[-1]
    if ext == 'pdf':
        return extract_from_pdf(filepath)
    elif ext in ['docx', 'doc']:
        return extract_from_docx(filepath)
    elif ext in ['png', 'jpg', 'jpeg']:
        return extract_from_image(filepath)
    return ""
