"""PDF processing utilities."""
import io
import base64
import logging
import fitz  # PyMuPDF
import pdfplumber
from PIL import Image
from config import settings

logger = logging.getLogger("ThirdEye.PDF")


def extract_text_with_pdfplumber(file_path: str) -> list[dict]:
    """
    Extract text from each page of a PDF using pdfplumber.
    Returns a list of {page_number, text} dicts.
    """
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            pages.append({"page_number": i + 1, "text": text})
    return pages


def extract_text_with_pymupdf(file_path: str) -> list[dict]:
    """
    Extract text from each page using PyMuPDF.
    Returns a list of {page_number, text} dicts.
    """
    pages = []
    doc = fitz.open(file_path)
    for i, page in enumerate(doc):
        text = page.get_text()
        pages.append({"page_number": i + 1, "text": text})
    doc.close()
    return pages


def extract_full_text(file_path: str) -> str:
    """Extract all text from a PDF, concatenated."""
    pages = extract_text_with_pdfplumber(file_path)
    return "\n\n".join(p["text"] for p in pages)


def get_metadata(file_path: str) -> dict:
    """Extract PDF metadata using PyMuPDF."""
    doc = fitz.open(file_path)
    metadata = doc.metadata or {}
    metadata["page_count"] = doc.page_count
    metadata["is_encrypted"] = doc.is_encrypted
    doc.close()
    return metadata


def pdf_page_to_image(file_path: str, page_number: int = 0, dpi: int = None) -> Image.Image:
    """Convert a specific PDF page to a PIL Image."""
    dpi = dpi or settings.PDF_TO_IMAGE_DPI
    doc = fitz.open(file_path)
    page = doc.load_page(page_number)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def pdf_pages_to_images(file_path: str, dpi: int = None) -> list[Image.Image]:
    """Convert all PDF pages to PIL Images."""
    dpi = dpi or settings.PDF_TO_IMAGE_DPI
    doc = fitz.open(file_path)
    images = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """Convert a PIL Image to base64 string."""
    buffered = io.BytesIO()
    image.save(buffered, format=format)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def is_scanned_pdf(file_path: str, sample_pages: int = 3) -> bool:
    """Detect if a PDF is scanned/image-based (no extractable text).
    
    Checks the first `sample_pages` pages. If all have <20 characters of text,
    the PDF is considered scanned.
    """
    with pdfplumber.open(file_path) as pdf:
        pages_to_check = min(sample_pages, len(pdf.pages))
        for i in range(pages_to_check):
            text = pdf.pages[i].extract_text() or ""
            if len(text.strip()) > 20:
                return False
    return True


def ocr_page_with_vision(file_path: str, page_number: int, dpi: int = None) -> str:
    """OCR a single PDF page using GPT-4o Vision.
    
    Converts the page to an image, sends it to GPT-4o, and returns the
    extracted text in a structured format suitable for bank statement parsing.
    """
    from services.llm_client import chat_completion_with_image

    dpi = dpi or settings.PDF_TO_IMAGE_DPI
    img = pdf_page_to_image(file_path, page_number, dpi=dpi)
    b64 = image_to_base64(img)

    prompt = (
        "You are an OCR engine. Extract ALL text from this bank statement page "
        "exactly as it appears, preserving the layout as much as possible.\n\n"
        "Rules:\n"
        "- Reproduce every line of text you see, in reading order (top to bottom, left to right)\n"
        "- Preserve column alignment using spaces or tabs where possible\n"
        "- Include all numbers, dates, amounts, and descriptions exactly as printed\n"
        "- For table rows, separate columns with ' | ' (pipe with spaces)\n"
        "- Include headers, footers, and any bank logos/text you can read\n"
        "- If text is blurry or unclear, provide your best reading with [?] for uncertain parts\n"
        "- Do NOT add any commentary — output ONLY the extracted text"
    )

    text = chat_completion_with_image(
        prompt=prompt,
        image_base64=b64,
        max_tokens=4096,
    )
    return text


def ocr_all_pages(file_path: str, dpi: int = None) -> list[dict]:
    """OCR all pages of a scanned PDF using GPT-4o Vision.
    
    Returns the same format as extract_text_with_pdfplumber:
    a list of {page_number, text} dicts.
    """
    doc = fitz.open(file_path)
    num_pages = len(doc)
    doc.close()

    pages = []
    for i in range(num_pages):
        logger.info(f"  🔍 OCR page {i+1}/{num_pages}...")
        text = ocr_page_with_vision(file_path, i, dpi=dpi)
        pages.append({"page_number": i + 1, "text": text})
    return pages
