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

    def run_group(self, upload_group_id: str, db: Session) -> dict:
        """Run tampering analysis across ALL documents in an upload group.

        For each document, aggregates the per-document results and adds
        cross-document consistency checks (e.g. do all PDFs share the same
        creator/producer?  Are sharpness levels consistent?).
        """
        logger.info(f"🔍 Group tampering agent starting for group {upload_group_id}")

        docs = (
            db.query(Document)
            .filter(Document.upload_group_id == upload_group_id)
            .all()
        )

        if not docs:
            return {
                "results": {"error": "No documents found"},
                "summary": "No documents found in group",
                "risk_level": "low",
            }

        logger.info(f"  📄 Running cross-document tampering checks on {len(docs)} PDFs...")

        # ── Collect per-document summaries from existing agent results ──
        from models import AgentResult
        per_doc_summaries = []
        all_per_doc_checks = []

        for doc in docs:
            result = (
                db.query(AgentResult)
                .filter(
                    AgentResult.document_id == doc.id,
                    AgentResult.agent_type == "tampering",
                )
                .first()
            )
            doc_summary = {
                "document_id": doc.id,
                "filename": doc.original_filename,
                "status": result.status if result else "not_run",
                "risk_level": result.risk_level if result else "unknown",
                "pass_count": 0,
                "fail_count": 0,
                "warning_count": 0,
            }
            if result and result.results:
                r = result.results
                doc_summary["pass_count"] = r.get("pass_count", 0)
                doc_summary["fail_count"] = r.get("fail_count", 0)
                doc_summary["warning_count"] = r.get("warning_count", 0)
                all_per_doc_checks.extend(r.get("checks", []))
            per_doc_summaries.append(doc_summary)

        # ── Cross-document checks ──
        checks: list[dict] = []

        # Check 1: Creator/Producer consistency across documents
        checks.append(self._check_cross_creator_consistency(docs))

        # Check 2: Sharpness consistency across documents
        checks.append(self._check_cross_sharpness_consistency(docs))

        # Check 3: Aggregate per-document tampering failures
        total_fails = sum(d["fail_count"] for d in per_doc_summaries)
        total_warns = sum(d["warning_count"] for d in per_doc_summaries)
        if total_fails == 0 and total_warns <= len(docs):
            checks.append({
                "check": "Per-Document Tampering Summary",
                "status": "pass",
                "details": (
                    f"All {len(docs)} documents have clean tampering checks "
                    f"({total_warns} minor warnings)."
                ),
            })
        elif total_fails > 0:
            failed_docs = [d["filename"] for d in per_doc_summaries if d["fail_count"] > 0]
            checks.append({
                "check": "Per-Document Tampering Summary",
                "status": "fail",
                "details": (
                    f"{total_fails} tampering check failure(s) across documents: "
                    f"{', '.join(failed_docs)}."
                ),
            })
        else:
            checks.append({
                "check": "Per-Document Tampering Summary",
                "status": "warning",
                "details": f"{total_warns} warning(s) across {len(docs)} documents.",
            })

        # ── Compute risk ──
        risk_level, risk_score, summary = _compute_risk(checks)

        logger.info(
            f"  🔍 Group tampering result: {risk_level} (score={risk_score}) — {summary}"
        )

        return {
            "results": {
                "checks": checks,
                "per_document_summary": per_doc_summaries,
                "risk_score": risk_score,
                "pass_count": sum(1 for c in checks if c["status"] == "pass"),
                "fail_count": sum(1 for c in checks if c["status"] == "fail"),
                "warning_count": sum(1 for c in checks if c["status"] == "warning"),
                "total_checks": len(checks),
                "documents_analyzed": len(docs),
            },
            "summary": f"[{len(docs)} documents] {summary}",
            "risk_level": risk_level,
        }

    def _check_cross_creator_consistency(self, docs: list) -> dict:
        """Check that all PDFs were produced by the same tool (consistent source)."""
        name = "Cross-Document Creator Consistency"
        creators = {}
        producers = {}

        for doc in docs:
            try:
                pdf = fitz.open(doc.file_path)
                meta = pdf.metadata or {}
                pdf.close()
                creator = (meta.get("creator") or "").strip() or "Unknown"
                producer = (meta.get("producer") or "").strip() or "Unknown"
                creators[doc.original_filename] = creator
                producers[doc.original_filename] = producer
            except Exception:
                creators[doc.original_filename] = "Error"
                producers[doc.original_filename] = "Error"

        unique_creators = set(creators.values()) - {"Unknown", "Error"}
        unique_producers = set(producers.values()) - {"Unknown", "Error"}

        if len(unique_creators) <= 1 and len(unique_producers) <= 1:
            return {
                "check": name,
                "status": "pass",
                "details": (
                    f"All {len(docs)} documents have consistent creator/producer metadata. "
                    f"Creator: {unique_creators or {'N/A'}}, Producer: {unique_producers or {'N/A'}}"
                ),
            }

        return {
            "check": name,
            "status": "warning" if len(unique_creators) <= 2 else "fail",
            "details": (
                f"Inconsistent PDF tools detected across documents. "
                f"Creators: {dict(creators)}, Producers: {dict(producers)}"
            ),
        }

    def _check_cross_sharpness_consistency(self, docs: list) -> dict:
        """Check that page sharpness is consistent across all documents."""
        name = "Cross-Document Sharpness Consistency"
        doc_sharpnesses = {}

        for doc in docs:
            try:
                img = _pdf_page_to_pil(doc.file_path, 0, dpi=150)
                lap = _laplacian_variance(img)
                doc_sharpnesses[doc.original_filename] = round(lap, 2)
            except Exception:
                doc_sharpnesses[doc.original_filename] = 0

        values = list(doc_sharpnesses.values())
        if len(values) < 2:
            return {"check": name, "status": "pass",
                    "details": "Only one document — consistency check not applicable."}

        max_v = max(values)
        min_v = min(values)
        ratio = min_v / max_v if max_v > 0 else 1

        if ratio >= 0.3:
            return {
                "check": name,
                "status": "pass",
                "details": (
                    f"Sharpness is consistent across {len(docs)} documents. "
                    f"Values: {doc_sharpnesses}"
                ),
            }

        return {
            "check": name,
            "status": "fail",
            "details": (
                f"Significant sharpness variation across documents (ratio: {ratio:.2f}). "
                f"Values: {doc_sharpnesses} — some documents may be scanned copies."
            ),
        }
