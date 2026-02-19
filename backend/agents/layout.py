"""
Layout Analysis Agent — Analyzes PDF structure and provides context to Extraction Agent.

This agent runs BEFORE extraction to understand the document's layout, improving
extraction accuracy especially for new/unknown bank statement formats.

Responsibilities:
1. Bank detection (from logos, headers, fonts, known patterns)
2. Table structure analysis (columns, headers, row patterns)
3. Date/amount format detection
4. Page layout analysis (headers, footers, margins)
5. Generate structured context for extraction agent

Output: Layout context that guides extraction for better accuracy.
"""
from __future__ import annotations

import json
import logging
import math
import re
from typing import Dict, List, Optional, Tuple
from collections import Counter

import pdfplumber
from sqlalchemy.orm import Session

from agents.base import BaseAgent
from models import Document
from services.pdf_processor import extract_text_with_pdfplumber

logger = logging.getLogger("ThirdEye.Agent.Layout")


def sanitize_float(value: float) -> float:
    """Sanitize float values to prevent JSON serialization errors."""
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return value

# ─── Bank Detection Patterns ──────────────────────────────────────────────────

BANK_SIGNATURES = {
    "DBS": {
        "keywords": ["DBS BANK", "DEVELOPMENT BANK OF SINGAPORE", "DBS/POSB"],
        "products": ["AUTOSAVE ACCOUNT", "MULTIPLIER ACCOUNT", "MY ACCOUNT", "DBS TREASURES"],
        "header_patterns": [r"DBS\s+BANK", r"DBS/POSB"],
    },
    "POSB": {
        "keywords": ["POSB", "POST OFFICE SAVINGS BANK"],
        "products": ["POSB SAYE", "POSB EVERYDAY"],
        "header_patterns": [r"POSB"],
    },
    "OCBC": {
        "keywords": ["OCBC BANK", "OVERSEA-CHINESE BANKING", "OCBC"],
        "products": ["360 ACCOUNT", "FRANK ACCOUNT", "OCBC VOYAGE"],
        "header_patterns": [r"OCBC\s+BANK"],
    },
    "UOB": {
        "keywords": ["UNITED OVERSEAS BANK", "UOB"],
        "products": ["UNIPLUS", "ONE ACCOUNT", "STASH ACCOUNT"],
        "header_patterns": [r"UNITED\s+OVERSEAS\s+BANK", r"UOB"],
    },
    "Standard Chartered": {
        "keywords": ["STANDARD CHARTERED"],
        "products": ["BONUSSAVER", "JUMPSTART"],
        "header_patterns": [r"STANDARD\s+CHARTERED"],
    },
    "HSBC": {
        "keywords": ["HSBC", "THE HONGKONG AND SHANGHAI BANKING"],
        "products": ["EVERYDAY GLOBAL ACCOUNT", "CURRENT ACCOUNT"],
        "header_patterns": [r"HSBC"],
    },
    "Citibank": {
        "keywords": ["CITIBANK"],
        "products": ["CITIGOLD", "MAXIGAIN"],
        "header_patterns": [r"CITIBANK"],
    },
    "GXS Bank": {
        "keywords": ["GXS BANK", "GXS"],
        "products": [],
        "header_patterns": [r"GXS\s+BANK"],
    },
    "Trust Bank": {
        "keywords": ["TRUST BANK"],
        "products": [],
        "header_patterns": [r"TRUST\s+BANK"],
    },
    "Aspire": {
        "keywords": ["ASPIRE"],
        "products": ["ASPIRE BUSINESS ACCOUNT"],
        "header_patterns": [r"ASPIRE"],
    },
    "Airwallex": {
        "keywords": ["AIRWALLEX"],
        "products": [],
        "header_patterns": [r"AIRWALLEX"],
    },
}


# ─── Column Header Mappings ───────────────────────────────────────────────────

COLUMN_ALIASES = {
    "date": ["date", "txn date", "transaction date", "date & time", "posting date"],
    "value_date": ["value date", "val date", "effective date"],
    "description": ["description", "transaction details", "details", "particulars", "narrative"],
    "debit": ["debit", "withdrawal", "withdrawals", "dr", "payments"],
    "credit": ["credit", "deposit", "deposits", "cr", "receipts"],
    "balance": ["balance", "running balance", "bal", "closing balance"],
    "reference": ["reference", "ref", "ref no", "transaction ref"],
}


# ─── Date Format Detection ────────────────────────────────────────────────────

DATE_PATTERNS = [
    (r'\d{2}-[A-Z]{3}-\d{4}', "DD-MMM-YYYY"),     # 01-SEP-2025
    (r'\d{2}\s+[A-Z]{3}\s+\d{4}', "DD MMM YYYY"),  # 01 SEP 2025
    (r'\d{2}\s+[A-Z]{3}', "DD MMM"),               # 01 SEP
    (r'\d{2}/\d{2}/\d{4}', "DD/MM/YYYY"),          # 01/09/2025
    (r'\d{2}/\d{2}/\d{2}', "DD/MM/YY"),            # 01/09/25
    (r'\d{2}[A-Z]{3}\d{4}', "DDMMMYYYY"),          # 01SEP2025 (HSBC)
]


class LayoutAgent(BaseAgent):
    """Analyzes PDF layout and structure to improve extraction accuracy."""

    def run(self, document_id: str, db: Session) -> dict:
        """
        Analyze document layout and return structured context.
        
        Returns:
            dict with keys:
                - results: layout context for extraction agent
                - summary: human-readable summary
                - risk_level: always "low" (informational only)
        """
        logger.info(f"Layout agent analyzing document {document_id}")

        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return self._error("Document not found")

        try:
            # Analyze PDF structure
            layout_context = self._analyze_layout(doc.file_path)
            
            summary = self._generate_summary(layout_context)
            
            logger.info(f"  ✅ Layout analysis complete: {layout_context['bank_detected']} "
                       f"(confidence: {layout_context['confidence']:.2f})")

            return {
                "results": layout_context,
                "summary": summary,
                "risk_level": "low",  # Layout analysis is informational
            }

        except Exception as e:
            logger.error(f"  ❌ Layout analysis failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return self._error(f"Layout analysis failed: {str(e)}")

    def _analyze_layout(self, file_path: str) -> dict:
        """Main layout analysis logic."""
        context = {
            "bank_detected": "Unknown",
            "confidence": 0.0,
            "is_scanned": False,
            "table_structure": None,
            "date_format": "DD MMM",
            "amount_format": "decimal_comma",
            "multi_line_descriptions": False,
            "column_mapping": {},
            "special_markers": {},
            "page_count": 0,
            "has_tables": False,
        }

        with pdfplumber.open(file_path) as pdf:
            context["page_count"] = len(pdf.pages)
            
            # Analyze first 3 pages (sufficient for layout detection)
            first_pages = pdf.pages[:min(3, len(pdf.pages))]
            
            # Step 1: Bank detection
            bank_info = self._detect_bank(first_pages)
            context["bank_detected"] = bank_info["bank"]
            context["confidence"] = sanitize_float(bank_info["confidence"])
            
            # Step 2: Table structure analysis
            table_info = self._analyze_tables(first_pages)
            context["table_structure"] = table_info["structure"]
            context["has_tables"] = table_info["has_tables"]
            context["column_mapping"] = table_info["column_mapping"]
            
            # Step 3: Date/amount format detection
            format_info = self._detect_formats(first_pages)
            context["date_format"] = format_info["date_format"]
            context["amount_format"] = format_info["amount_format"]
            
            # Step 4: Special markers detection
            context["special_markers"] = self._detect_special_markers(first_pages)
            
            # Step 5: Multi-line description detection
            context["multi_line_descriptions"] = self._detect_multiline_descriptions(
                first_pages, table_info
            )

        return context

    def _detect_bank(self, pages: List) -> dict:
        """Detect bank from text patterns, keywords, and products."""
        all_text = "\n".join(page.extract_text() or "" for page in pages[:2])
        all_text_upper = all_text.upper()
        
        scores = {}
        
        for bank_name, signatures in BANK_SIGNATURES.items():
            score = 0
            
            # Check keywords
            for keyword in signatures["keywords"]:
                if keyword.upper() in all_text_upper:
                    score += 3
            
            # Check product names
            for product in signatures["products"]:
                if product.upper() in all_text_upper:
                    score += 2
            
            # Check header patterns
            for pattern in signatures["header_patterns"]:
                if re.search(pattern, all_text_upper):
                    score += 2
            
            if score > 0:
                scores[bank_name] = score
        
        if not scores:
            return {"bank": "Unknown", "confidence": 0.0}
        
        # Get bank with highest score
        detected_bank = max(scores, key=scores.get)
        max_score = scores[detected_bank]
        
        # Confidence based on score (normalize to 0-1)
        confidence = min(max_score / 10.0, 1.0)
        
        return {"bank": detected_bank, "confidence": sanitize_float(confidence)}

    def _analyze_tables(self, pages: List) -> dict:
        """Analyze table structures and column headers."""
        result = {
            "has_tables": False,
            "structure": None,
            "column_mapping": {},
        }
        
        # Look for tables in first few pages
        for page_idx, page in enumerate(pages[:3]):
            tables = page.extract_tables()
            
            if not tables:
                continue
            
            result["has_tables"] = True
            
            # Analyze first substantial table
            for table in tables:
                if not table or len(table) < 2:
                    continue
                
                # Get header row (usually first row)
                headers = table[0]
                if not headers:
                    continue
                
                # Map headers to canonical column names
                column_mapping = self._map_columns(headers)
                
                if column_mapping:
                    result["column_mapping"] = column_mapping
                    result["structure"] = {
                        "page": page_idx,
                        "columns": len(headers),
                        "header_row": headers,
                        "sample_rows": table[1:min(4, len(table))],
                    }
                    break
            
            if result["structure"]:
                break
        
        return result

    def _map_columns(self, headers: List[str]) -> dict:
        """Map table headers to canonical column names."""
        mapping = {}
        
        for idx, header in enumerate(headers):
            if not header:
                continue
            
            header_clean = header.strip().lower()
            # Remove non-ASCII characters
            header_clean = re.sub(r'[^\x00-\x7f]', '', header_clean)
            # Remove currency markers like (SGD)
            header_clean = re.sub(r'\s*\([A-Z]{3}\)\s*', '', header_clean)
            header_clean = header_clean.strip()
            
            # Try to match to canonical name
            for canonical, aliases in COLUMN_ALIASES.items():
                for alias in aliases:
                    if alias in header_clean or header_clean in alias:
                        mapping[canonical] = idx
                        break
                if canonical in mapping:
                    break
        
        return mapping

    def _detect_formats(self, pages: List) -> dict:
        """Detect date and amount formats from sample text."""
        text = "\n".join(page.extract_text() or "" for page in pages[:2])
        
        # Date format detection
        date_format = "DD MMM"  # default
        for pattern, format_name in DATE_PATTERNS:
            if re.search(pattern, text):
                date_format = format_name
                break
        
        # Amount format detection (comma vs period)
        # Look for patterns like 1,234.56 (decimal) or 1.234,56 (european)
        decimal_count = len(re.findall(r'\d{1,3},\d{3}\.\d{2}', text))
        european_count = len(re.findall(r'\d{1,3}\.\d{3},\d{2}', text))
        
        amount_format = "decimal_comma" if decimal_count >= european_count else "european"
        
        return {
            "date_format": date_format,
            "amount_format": amount_format,
        }

    def _detect_special_markers(self, pages: List) -> dict:
        """Detect special transaction markers (opening/closing balance, etc.)."""
        text = "\n".join(page.extract_text() or "" for page in pages)
        text_upper = text.upper()
        
        markers = {}
        
        # Opening balance markers
        ob_patterns = ["BALANCE B/F", "BALANCE BROUGHT FORWARD", "OPENING BALANCE", 
                       "BROUGHT FORWARD", "B/F"]
        for pattern in ob_patterns:
            if pattern in text_upper:
                markers["opening_balance"] = pattern
                break
        
        # Closing balance markers
        cb_patterns = ["BALANCE C/F", "BALANCE CARRIED FORWARD", "CLOSING BALANCE",
                       "CARRIED FORWARD", "C/F"]
        for pattern in cb_patterns:
            if pattern in text_upper:
                markers["closing_balance"] = pattern
                break
        
        return markers

    def _detect_multiline_descriptions(self, pages: List, table_info: dict) -> bool:
        """
        Detect if transaction descriptions span multiple lines.
        Common in DBS statements.
        """
        if not table_info["has_tables"]:
            return False
        
        # If table structure has many rows but few date entries, likely multi-line
        for page in pages[:2]:
            tables = page.extract_tables()
            for table in tables:
                if len(table) < 5:
                    continue
                
                # Count rows with dates
                date_rows = 0
                total_rows = len(table) - 1  # Exclude header
                
                for row in table[1:]:
                    if not row:
                        continue
                    # Check if first cell looks like a date
                    first_cell = str(row[0] or "").strip()
                    if re.match(r'\d{1,2}[\-/\s]', first_cell):
                        date_rows += 1
                
                # If less than 60% of rows have dates, likely multi-line
                if date_rows > 0 and date_rows / total_rows < 0.6:
                    return True
        
        return False

    def _generate_summary(self, context: dict) -> str:
        """Generate human-readable summary of layout analysis."""
        bank = context["bank_detected"]
        conf = context["confidence"]
        pages = context["page_count"]
        
        summary_parts = [
            f"Detected bank: {bank} (confidence: {conf:.0%})",
            f"Document has {pages} page(s)",
        ]
        
        if context["has_tables"]:
            cols = len(context["column_mapping"])
            summary_parts.append(f"Found structured tables with {cols} identified columns")
        else:
            summary_parts.append("No structured tables detected (unstructured extraction required)")
        
        summary_parts.append(f"Date format: {context['date_format']}")
        
        if context["multi_line_descriptions"]:
            summary_parts.append("Multi-line transaction descriptions detected")
        
        return ". ".join(summary_parts) + "."

    def _error(self, message: str) -> dict:
        """Return error result."""
        return {
            "results": {"error": message},
            "summary": f"Layout analysis error: {message}",
            "risk_level": "low",
        }
