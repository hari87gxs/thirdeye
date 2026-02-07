"""
Tampering Detection Agent — Step 5.

Runs 8 independent checks on the uploaded PDF and produces an overall
risk assessment.  Each check returns a dict with:
    check   – human-readable name
    status  – "pass" | "fail" | "warning"
    details – explanation

The checks are:
  1. Metadata Date Check          (creation ≠ modification → suspicious)
  2. Metadata Creator/Producer    (editing-tool fingerprints)
  3. Metadata Keywords            (suspicious keywords field)
  4. Font Consistency             (unexpected fonts across pages)
  5. Page Dimension Check         (undersized pages)
  6. Page Clarity / Sharpness     (blurry pages → possible scan-of-edit)
  7. Sharpness Spread             (page-to-page sharpness variation)
  8. Visual Tampering (LLM)       (GPT-4o vision on first page)
"""

import io
import re
import json
import base64
import logging
import statistics
from datetime import datetime
from typing import Optional

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from agents.base import BaseAgent
from config import settings
from models import Document
from services.llm_client import chat_completion_with_image

logger = logging.getLogger("ThirdEye.Agent.Tampering")

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _pdf_page_to_pil(file_path: str, page_number: int, dpi: int = 200) -> Image.Image:
    """Convert a single PDF page to a PIL Image (RGB)."""
    doc = fitz.open(file_path)
    page = doc.load_page(page_number)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def _pil_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _laplacian_variance(img: Image.Image) -> float:
    """Compute Laplacian variance (sharpness measure) for a PIL Image."""
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _parse_pdf_date(raw: str) -> Optional[datetime]:
    """Parse a PDF date string like D:20200101120000+08'00'."""
    if not raw:
        return None
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", raw)
    if not m:
        return None
    try:
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
        )
    except ValueError:
        return None


def _fmt(dt: Optional[datetime]) -> str:
    return dt.strftime("%d %b %Y, %I:%M:%S %p") if dt else "Not found"


# ─── Individual Checks ────────────────────────────────────────────────────────

def check_metadata_dates(file_path: str) -> dict:
    """Check 1: Compare creation vs modification dates."""
    name = "Metadata Date Check"
    try:
        doc = fitz.open(file_path)
        meta = doc.metadata or {}
        doc.close()

        creation_dt = _parse_pdf_date(meta.get("creationDate", ""))
        mod_dt = _parse_pdf_date(meta.get("modDate", ""))
        dates_str = f"Created: {_fmt(creation_dt)}, Modified: {_fmt(mod_dt)}"

        if not creation_dt and not mod_dt:
            return {"check": name, "status": "warning",
                    "details": f"{dates_str} — Both dates missing (metadata may have been stripped)."}

        if not creation_dt or not mod_dt:
            return {"check": name, "status": "warning",
                    "details": f"{dates_str} — One date is missing or malformed."}

        if mod_dt < creation_dt:
            return {"check": name, "status": "fail",
                    "details": f"{dates_str} — Modification date is BEFORE creation date (invalid)."}

        delta = (mod_dt - creation_dt).total_seconds()
        if delta == 0:
            return {"check": name, "status": "pass",
                    "details": f"{dates_str} — No modification detected."}

        if delta <= 5:
            return {"check": name, "status": "pass",
                    "details": f"{dates_str} — Modification within 5 seconds (normal generation)."}

        if delta <= 60:
            return {"check": name, "status": "warning",
                    "details": f"{dates_str} — Modified {int(delta)}s after creation."}

        return {"check": name, "status": "fail",
                "details": f"{dates_str} — Modified {int(delta)}s after creation — potential tampering."}

    except Exception as e:
        return {"check": name, "status": "warning", "details": f"Error: {e}"}


def check_metadata_creator_producer(file_path: str) -> dict:
    """Check 2: Flag if creator/producer indicates an editing tool."""
    name = "Metadata Creator/Producer Check"
    try:
        doc = fitz.open(file_path)
        meta = doc.metadata or {}
        doc.close()

        creator = (meta.get("creator") or "").strip()
        producer = (meta.get("producer") or "").strip()

        if not creator and not producer:
            return {"check": name, "status": "warning",
                    "details": "No creator or producer metadata found (may have been stripped)."}

        # Known editing / tampering tools (case-insensitive check)
        suspicious_tools = [
            "canva", "ilovepdf", "smallpdf", "sejda", "pdf-xchange",
            "foxit phantompdf", "nitro", "pdfill", "pdfescape",
            "libreoffice", "openoffice", "google docs", "microsoft word",
            "print to pdf", "safari", "chrome",
        ]

        combined = f"{creator} {producer}".lower()
        for tool in suspicious_tools:
            if tool in combined:
                return {"check": name, "status": "fail",
                        "details": f"Creator: '{creator}', Producer: '{producer}' — "
                                   f"detected editing tool '{tool}'."}

        return {"check": name, "status": "pass",
                "details": f"Creator: '{creator}', Producer: '{producer}' — no suspicious tools detected."}

    except Exception as e:
        return {"check": name, "status": "warning", "details": f"Error: {e}"}


def check_metadata_keywords(file_path: str) -> dict:
    """Check 3: Flag suspicious keywords metadata."""
    name = "Metadata Keywords Check"
    try:
        doc = fitz.open(file_path)
        meta = doc.metadata or {}
        doc.close()

        keywords = (meta.get("keywords") or "").strip()
        if not keywords:
            return {"check": name, "status": "pass",
                    "details": "No keywords found — nothing suspicious."}

        # Simple heuristic: long hex strings, random chars, or known editing markers
        if re.search(r"[0-9a-f]{16,}", keywords, re.I):
            return {"check": name, "status": "fail",
                    "details": f"Keywords contain long hex/tracking string: '{keywords[:120]}'"}

        return {"check": name, "status": "pass",
                "details": f"Keywords: '{keywords[:120]}' — no issues."}

    except Exception as e:
        return {"check": name, "status": "warning", "details": f"Error: {e}"}


def check_font_consistency(file_path: str) -> dict:
    """Check 4: Extract all fonts and flag unexpected diversity or editing-tool fonts."""
    name = "Font Consistency Check"
    try:
        doc = fitz.open(file_path)
        all_fonts: set[str] = set()
        per_page_fonts: list[set[str]] = []

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_fonts: set[str] = set()
            for font_info in page.get_fonts(full=True):
                # font_info = (xref, ext, type, basefont, name, encoding)
                base_font = font_info[3] if font_info[3] else font_info[4]
                if base_font:
                    # Remove subset prefix (e.g., ABCDEF+ArialMT → ArialMT)
                    if "+" in base_font:
                        base_font = base_font.split("+", 1)[1]
                    page_fonts.add(base_font)
                    all_fonts.add(base_font)
            per_page_fonts.append(page_fonts)
        doc.close()

        if not all_fonts:
            return {"check": name, "status": "warning",
                    "details": "No fonts found — document may be image-based."}

        # Check for editing-tool font artifacts
        suspicious_font_keywords = ["helvetica-oblique", "canva", "edit"]
        for f in all_fonts:
            for kw in suspicious_font_keywords:
                if kw in f.lower():
                    return {"check": name, "status": "fail",
                            "details": f"Suspicious font detected: '{f}'. All fonts: {sorted(all_fonts)}"}

        # Check if page-to-page font sets differ significantly
        if len(per_page_fonts) > 1:
            page1_fonts = per_page_fonts[0]
            for i, pf in enumerate(per_page_fonts[1:], 2):
                diff = pf.symmetric_difference(page1_fonts)
                if len(diff) > 3:
                    return {"check": name, "status": "warning",
                            "details": f"Page {i} fonts differ from page 1 by {len(diff)} fonts. "
                                       f"Diff: {sorted(diff)}. All fonts: {sorted(all_fonts)}"}

        return {"check": name, "status": "pass",
                "details": f"Consistent fonts across {len(per_page_fonts)} pages. "
                           f"Fonts: {sorted(all_fonts)}"}

    except Exception as e:
        return {"check": name, "status": "warning", "details": f"Error: {e}"}


def check_page_dimensions(file_path: str) -> dict:
    """Check 5: Verify page dimensions meet minimum thresholds."""
    name = "Page Dimension Check"
    try:
        min_h = settings.DIMENSION_MIN_HEIGHT
        min_w = settings.DIMENSION_MIN_WIDTH
        dpi = settings.CHECK_SPECIFIC_DPI.get("document_dimension", 300)

        doc = fitz.open(file_path)
        num_pages = len(doc)
        doc.close()
        failures = []

        for page_num in range(num_pages):
            img = _pdf_page_to_pil(file_path, page_num, dpi=dpi)
            w, h = img.width, img.height
            reasons = []
            if h < min_h:
                reasons.append(f"height {h}px < min {min_h}px")
            if w < min_w:
                reasons.append(f"width {w}px < min {min_w}px")
            if reasons:
                failures.append(f"Page {page_num + 1}: {', '.join(reasons)}")

        if failures:
            return {"check": name, "status": "fail",
                    "details": " | ".join(failures)}

        return {"check": name, "status": "pass",
                "details": f"All {num_pages} pages meet minimum dimensions "
                           f"({min_w}×{min_h} at {dpi} DPI)."}

    except Exception as e:
        return {"check": name, "status": "warning", "details": f"Error: {e}"}


def check_page_clarity(file_path: str) -> dict:
    """Check 6: Laplacian variance sharpness per page."""
    name = "Page Clarity Check"
    try:
        threshold = settings.SHARPNESS_THRESHOLD
        dpi = settings.CHECK_SPECIFIC_DPI.get("page_clarity", 300)

        doc = fitz.open(file_path)
        num_pages = len(doc)
        doc.close()

        variances: list[float] = []
        failures = []

        for page_num in range(num_pages):
            img = _pdf_page_to_pil(file_path, page_num, dpi=dpi)
            lap = round(_laplacian_variance(img), 2)
            variances.append(lap)
            if lap < threshold:
                failures.append(
                    f"Page {page_num + 1}: sharpness {lap:.1f} < threshold {threshold}")

        if failures:
            return {"check": name, "status": "fail",
                    "details": " | ".join(failures)}

        per_page = ", ".join(f"P{i+1}:{v:.1f}" for i, v in enumerate(variances))
        return {"check": name, "status": "pass",
                "details": f"All {num_pages} pages passed clarity. Sharpness: [{per_page}]"}

    except Exception as e:
        return {"check": name, "status": "warning", "details": f"Error: {e}"}


def check_sharpness_spread(file_path: str) -> dict:
    """Check 7: Cross-page sharpness consistency."""
    name = "Sharpness Spread Check"
    try:
        ratio = settings.SHARPNESS_SPREAD_RATIO
        max_std = settings.SHARPNESS_MAX_STD_DEV
        dpi = settings.CHECK_SPECIFIC_DPI.get("sharpness_spread", 300)

        doc = fitz.open(file_path)
        num_pages = len(doc)
        doc.close()

        if num_pages < 2:
            return {"check": name, "status": "pass",
                    "details": "Only 1 page — spread check not applicable."}

        variances: list[float] = []
        for page_num in range(num_pages):
            img = _pdf_page_to_pil(file_path, page_num, dpi=dpi)
            variances.append(round(_laplacian_variance(img), 2))

        max_v, min_v = max(variances), min(variances)
        std_v = round(statistics.stdev(variances), 2) if len(variances) > 1 else 0.0
        spread_fail = (min_v < ratio * max_v) or (std_v > max_std)

        detail = (f"Variances: {variances}, Max: {max_v}, Min: {min_v}, "
                  f"StdDev: {std_v}")

        if spread_fail:
            return {"check": name, "status": "fail",
                    "details": f"{detail} — Significant variation across pages."}

        return {"check": name, "status": "pass",
                "details": f"{detail} — Consistent across pages."}

    except Exception as e:
        return {"check": name, "status": "warning", "details": f"Error: {e}"}


def check_visual_tampering(file_path: str) -> dict:
    """Check 8: GPT-4o vision analysis of the first page."""
    name = "Visual Tampering Check"
    try:
        dpi = settings.CHECK_SPECIFIC_DPI.get("visual_tampering", 150)
        img = _pdf_page_to_pil(file_path, 0, dpi=dpi)
        b64 = _pil_to_base64(img)

        prompt = (
            "You are a document fraud detection AI. Analyze the visual layout "
            "and appearance of this bank statement page. Check for signs of "
            "tampering such as:\n"
            "- Inconsistent font styles or sizes within the same section\n"
            "- Alignment issues or misaligned columns\n"
            "- Pasted or overlaid content (visible edges or colour mismatches)\n"
            "- Irregular spacing between rows or columns\n"
            "- Blurriness or visual artifacts in specific areas (while rest is sharp)\n"
            "- Signs of image editing (gradient inconsistencies, jpeg artefacts)\n"
            "- Missing or broken bank logos/headers\n\n"
            "Respond ONLY with valid JSON (no markdown fences):\n"
            '{"status": "pass" or "fail", '
            '"details": "brief explanation of findings, pointing out specific '
            'areas if suspicious"}'
        )

        raw = chat_completion_with_image(
            prompt=prompt,
            image_base64=b64,
            max_tokens=400,
        )

        # Parse LLM JSON
        raw = re.sub(r"^```json\s*|```\s*$", "", raw.strip()).strip()
        parsed = json.loads(raw)

        return {
            "check": name,
            "status": parsed.get("status", "warning"),
            "details": parsed.get("details", raw[:300]),
        }

    except Exception as e:
        return {"check": name, "status": "warning",
                "details": f"Could not run visual check: {e}"}


# ─── Risk Assessment ──────────────────────────────────────────────────────────

def _compute_risk(checks: list[dict]) -> tuple[str, int, str]:
    """
    Compute overall risk level from individual check results.
    Returns (risk_level, risk_score, summary_text).
    """
    fail_count = sum(1 for c in checks if c["status"] == "fail")
    warn_count = sum(1 for c in checks if c["status"] == "warning")
    pass_count = sum(1 for c in checks if c["status"] == "pass")
    total = len(checks)

    # Score: fail=3, warning=1, pass=0
    score = fail_count * 3 + warn_count * 1

    if fail_count >= 4:
        risk = "critical"
    elif fail_count >= 2:
        risk = "high"
    elif fail_count >= 1 or warn_count >= 3:
        risk = "medium"
    elif warn_count >= 1:
        risk = "low"
    else:
        risk = "low"

    summary_parts = []
    summary_parts.append(f"{pass_count}/{total} checks passed")
    if fail_count:
        failed = [c["check"] for c in checks if c["status"] == "fail"]
        summary_parts.append(f"{fail_count} failed: {', '.join(failed)}")
    if warn_count:
        warned = [c["check"] for c in checks if c["status"] == "warning"]
        summary_parts.append(f"{warn_count} warnings: {', '.join(warned)}")

    summary = ". ".join(summary_parts) + "."
    return risk, score, summary


# ─── Agent Class ──────────────────────────────────────────────────────────────

class TamperingAgent(BaseAgent):
    """
    Runs all tampering checks on a document and produces structured results.
    """

    def run(self, document_id: str, db: Session) -> dict:
        logger.info(f"🔍 Tampering agent starting for document {document_id}")

        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return {
                "results": {"error": "Document not found"},
                "summary": "Document not found",
                "risk_level": "low",
            }

        file_path = doc.file_path

        # ── Run all checks ────────────────────────────────────────────────
        checks: list[dict] = []

        # Checks 1-4: Fast metadata / font checks (no image rendering)
        logger.info("  📋 Running metadata & font checks...")
        checks.append(check_metadata_dates(file_path))
        checks.append(check_metadata_creator_producer(file_path))
        checks.append(check_metadata_keywords(file_path))
        checks.append(check_font_consistency(file_path))

        # Check 5: Page dimensions
        logger.info("  📐 Running page dimension check...")
        checks.append(check_page_dimensions(file_path))

        # Checks 6-7: Sharpness / clarity (render pages)
        logger.info("  🔎 Running sharpness / clarity checks...")
        checks.append(check_page_clarity(file_path))
        checks.append(check_sharpness_spread(file_path))

        # Check 8: Visual tampering via LLM (most expensive — last)
        logger.info("  👁️  Running visual tampering check (LLM)...")
        checks.append(check_visual_tampering(file_path))

        # ── Compute risk ──────────────────────────────────────────────────
        risk_level, risk_score, summary = _compute_risk(checks)

        logger.info(f"  🔍 Tampering result: {risk_level} (score={risk_score}) — {summary}")

        return {
            "results": {
                "checks": checks,
                "risk_score": risk_score,
                "pass_count": sum(1 for c in checks if c["status"] == "pass"),
                "fail_count": sum(1 for c in checks if c["status"] == "fail"),
                "warning_count": sum(1 for c in checks if c["status"] == "warning"),
                "total_checks": len(checks),
            },
            "summary": summary,
            "risk_level": risk_level,
        }
