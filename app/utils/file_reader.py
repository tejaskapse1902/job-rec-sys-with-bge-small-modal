from io import BytesIO
from typing import Union
import os

from pypdf import PdfReader
from docx import Document


def _read_pdf_from_bytes(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return " ".join([p.extract_text() or "" for p in reader.pages])


def _read_docx_from_bytes(data: bytes) -> str:
    doc = Document(BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text)


def read_resume_from_upload(file: Union["UploadFile", str, bytes]) -> str:
    """
    Supports:
    - FastAPI UploadFile
    - local file path (str)
    - raw bytes
    Returns extracted text.
    """

    # -------- Case 1: bytes input --------
    if isinstance(file, (bytes, bytearray)):
        # Can't know extension; treat as utf-8 text
        return bytes(file).decode("utf-8", errors="ignore")

    # -------- Case 2: file path input --------
    if isinstance(file, str):
        path = file
        ext = os.path.splitext(path)[1].lower()

        with open(path, "rb") as f:
            data = f.read()

        if ext == ".pdf":
            return _read_pdf_from_bytes(data)
        elif ext == ".docx":
            return _read_docx_from_bytes(data)
        else:
            return data.decode("utf-8", errors="ignore")

    # -------- Case 3: UploadFile input --------
    # Avoid importing UploadFile here to keep it pure utility
    name = (getattr(file, "filename", "") or "").lower()

    # Reset pointer
    file.file.seek(0)

    if name.endswith(".pdf"):
        # pypdf can read file-like objects directly
        reader = PdfReader(file.file)
        return " ".join([p.extract_text() or "" for p in reader.pages])

    elif name.endswith(".docx"):
        data = file.file.read()
        return _read_docx_from_bytes(data)

    else:
        return file.file.read().decode("utf-8", errors="ignore")
