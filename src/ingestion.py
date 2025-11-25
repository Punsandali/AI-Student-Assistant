# ingestion.py
import pdfplumber
import docx
import pytesseract
from PIL import Image
import os
import re

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# -------------------------------
# CLEANING UTIL
# -------------------------------
def clean_text(text):
    if not text:
        return ""
    text = text.replace("•", "\n- ")
    text = re.sub(r'\n{2,}', '\n\n', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# -------------------------------
# PDF TEXT + TABLE + OCR EXTRACTOR
# -------------------------------
def extract_text_pdf(file_path):
    text = ""

    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                # ----- NORMAL TEXT -----
                page_text = page.extract_text() or ""
                page_text = clean_text(page_text)

                # ----- OCR FROM IMAGES -----
                ocr_text = ""
                for img in page.images:
                    try:
                        x0, top, x1, bottom = img["x0"], img["top"], img["x1"], img["bottom"]
                        crop = page.crop((x0, top, x1, bottom)).to_image(resolution=300).original
                        
                        ocr_result = pytesseract.image_to_string(crop)   # <-- assign first
                        print(f"[DEBUG] Page {i+1} OCR Text:\n{ocr_result}\n---")  # <-- then print
                        ocr_text += ocr_result
                        
                    except:
                        pass  # ignore OCR failures

                # ----- COMBINE -----
                combined = f"\n\n[Page {i+1}]\n{page_text}\n{ocr_text}"
                text += combined

                # ----- TABLE EXTRACTION -----
                tables = page.extract_tables() or []
                for table in tables:
                    safe_rows = []
                    for row in table:
                        # Prevent NoneType errors
                        safe_row = [(cell if cell is not None else "") for cell in row]
                        safe_rows.append(" | ".join(safe_row))

                    table_text = "\n".join(safe_rows)
                    text += f"\n\n[TABLE]\n{table_text}"

    except Exception as e:
        return f"[PDF ERROR] Could not read PDF: {e}"

    return text


# -------------------------------
# DOCX EXTRACTOR
# -------------------------------
def extract_text_docx(file_path):
    try:
        doc = docx.Document(file_path)
        text = ""
        for i, para in enumerate(doc.paragraphs):
            if para.text.strip():
                text += f"\n\n[Para {i+1}]\n{para.text}"
        return text
    except Exception as e:
        return f"[DOCX ERROR] Could not read DOCX: {e}"


# -------------------------------
# CHUNKING
# -------------------------------
def chunk_text(text, chunk_size=800, overlap=100):
    if not text:
        return [""]

    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


# -------------------------------
# MAIN FILE INGEST
# -------------------------------
def ingest_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        text = extract_text_pdf(file_path)
    elif ext == ".docx":
        text = extract_text_docx(file_path)
    else:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            text = f"[TEXT ERROR] Could not read file: {e}"

    chunks = chunk_text(text)

    # metadata included
    chunk_data = [
        {"id": f"{file_path}-chunk{i}", "text": c, "source": file_path}
        for i, c in enumerate(chunks)
    ]

    return chunk_data
