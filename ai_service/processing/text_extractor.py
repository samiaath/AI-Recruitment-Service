import pdfplumber
import pytesseract
from PIL import Image
import docx

def extract_from_pdf(filepath: str) -> str:
    text = ""
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + r"\n"
    except Exception as e:
        print(f"Error pdfplumber: {e}")
    return text

def extract_from_docx(filepath: str) -> str:
    text = ""
    try:
        doc = docx.Document(filepath)
        text = r"\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        print(f"Error docx: {e}")
    return text

def extract_from_image(filepath: str) -> str:
    try:
        image = Image.open(filepath).convert("RGB")
        return pytesseract.image_to_string(image, lang="fra+eng")
    except Exception as e:
        print(f"Error image: {e}")
        return ""
