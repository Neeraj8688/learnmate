from dataclasses import dataclass

import pymupdf


class ExtractionError(ValueError):
    pass


@dataclass
class Page:
    number: int | None   # 1-based; None for plain text
    text: str


def extract_pdf(data: bytes) -> list[Page]:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ExtractionError("Could not open file as a PDF.") from exc
    pages = [Page(i + 1, p.get_text().strip()) for i, p in enumerate(doc)]
    pages = [p for p in pages if p.text]
    if not pages:
        raise ExtractionError(
            "No extractable text found (scanned/image-only PDF? OCR is not supported)."
        )
    return pages


def extract_txt(data: bytes) -> list[Page]:
    try:
        text = data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ExtractionError("TXT file must be UTF-8 encoded.") from exc
    if not text:
        raise ExtractionError("File is empty.")
    return [Page(None, text)]


def extract(filename: str, data: bytes) -> list[Page]:
    name = filename.lower()
    if name.endswith(".pdf"):
        if not data.startswith(b"%PDF"):
            raise ExtractionError("File content is not a valid PDF.")
        return extract_pdf(data)
    if name.endswith(".txt"):
        return extract_txt(data)
    raise ExtractionError("Unsupported file type. Only .pdf and .txt are allowed.")
