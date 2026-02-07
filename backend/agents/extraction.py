"""
Extraction Agent — Extracts structured data from bank statements using Azure OpenAI.

Strategy  (v2 — accuracy-focused):
1. Extract text from all pages using pdfplumber (pre-LLM text chunking)
2. Identify bank & account info from page 1 (LLM + regex fallback)
3. Build overlapping page batches (1-page overlap preserves cross-page context)
4. Send text chunks to LLM for structured extraction
5. De-duplicate transactions at batch boundaries
6. Validate balance chain (each txn's balance must follow from the previous)
7. Compute extraction accuracy score
8. Compute 25+ metrics and store in DB
"""
from __future__ import annotations

import json
import logging
import math
import re
import statistics
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from agents.base import BaseAgent
from models import Document, RawTransaction, StatementMetrics, AggregatedMetrics
from services.pdf_processor import extract_text_with_pdfplumber, pdf_page_to_image, image_to_base64, is_scanned_pdf, ocr_all_pages
from services.llm_client import chat_completion, chat_completion_with_image

logger = logging.getLogger("ThirdEye.Agent.Extraction")

# ─── Page filtering (multi-bank) ─────────────────────────────────────────────

SKIP_PATTERNS = [
    # OCBC
    "TRANSACTION CODE DESCRIPTION",
    "CHECK YOUR STATEMENT",
    "UPDATING YOUR PERSONAL PARTICULARS",
    # DBS
    "IMPORTANT NOTES",
    "Important Information",
    "Transaction codes",
    # UOB
    "TRANSACTION CODES USED",
    "Deposit Insurance Scheme Singapore",
    # Standard Chartered
    "Terms and Conditions",
    # Generic footer-only pages
    "This page is intentionally left blank",
]

BANK_IDENTIFIERS = {
    "OCBC": ["OCBC Bank", "Oversea-Chinese Banking", "OCBC"],
    "DBS": ["DBS Bank", "Development Bank of Singapore", "DBS/POSB", "DBS"],
    "POSB": ["POSB"],
    "UOB": ["United Overseas Bank", "UOB"],
    "Standard Chartered": ["Standard Chartered"],
    "HSBC": ["HSBC"],
    "Citibank": ["Citibank"],
    "Maybank": ["Maybank"],
    "CIMB": ["CIMB"],
    "Bank of China": ["Bank of China"],
    "ICBC": ["ICBC"],
    "GXS Bank": ["GXS Bank", "GXS"],
    "Trust Bank": ["Trust Bank", "Trust"],
    "MariBank": ["MariBank"],
    "Revolut": ["Revolut"],
    "Wise": ["Wise", "TransferWise"],
    "Aspire": ["Aspire"],
    "Airwallex": ["Airwallex"],
}

# Product names that uniquely identify a bank (for PDFs without explicit bank name)
BANK_PRODUCT_IDENTIFIERS = {
    "DBS": ["AUTOSAVE ACCOUNT", "MULTIPLIER ACCOUNT", "MY ACCOUNT", "DBS TREASURES",
            "POSB SAYE", "POSB EVERYDAY"],
    "OCBC": ["360 ACCOUNT", "FRANK ACCOUNT", "OCBC VOYAGE"],
    "UOB": ["UNIPLUS", "ONE ACCOUNT", "STASH ACCOUNT"],
    "Standard Chartered": ["BONUSSAVER", "JUMPSTART"],
    "HSBC": ["EVERYDAY GLOBAL ACCOUNT", "CURRENT ACCOUNT"],
}

# Bank-specific noise to strip (headers/footers that repeat on every page)
BANK_NOISE_PATTERNS = {
    "OCBC": [r"Deposit Insurance Scheme.*", r"Please turn over.*", r"RNB\w+\\?\d+"],
    "DBS": [r"Page \d+\s*/\s*\d+", r"Page \d+ of \d+", r"DBS Bank Ltd.*",
            r"Printed By\s*:.*", r"Printed On\s*:.*",
            r"Deposit Insurance Scheme.*?\.",
            r"Transactions performed on a non-working day.*",
            r"If date requested is a non business day.*"],
    "UOB": [r"Page \d+ of \d+", r"United Overseas Bank Limited.*"],
    "Standard Chartered": [r"Page \d+ of \d+"],
    "HSBC": [r"Page\s*\d+\s*of\s*\d+", r"Deposit Insurance Scheme.*",
             r"Issued by The Hongkong.*", r"ENDOFSTATEMENT"],
    "_default": [r"Page \d+\s*/\s*\d+", r"Page \d+ of \d+"],
}


# ─── LLM Prompts ──────────────────────────────────────────────────────────────

ACCOUNT_INFO_PROMPT = """You are an expert bank statement parser for Singapore banks.
You must handle statements from any Singapore bank: OCBC, DBS, POSB, UOB, Standard Chartered,
HSBC, Citibank, Maybank, CIMB, GXS Bank, Trust Bank, MariBank, Revolut, Wise, Aspire, Airwallex.

Extract the following from this bank statement's first page(s).

Return ONLY valid JSON (no markdown fences):
{
  "account_holder": "company or person name",
  "bank": "full bank name",
  "account_number": "account number",
  "currency": "SGD or other",
  "statement_period": "DD MMM YYYY to DD MMM YYYY",
  "account_type": "type of account (e.g. Business, Savings, Current)"
}

If a field is not found, use null.

Bank statement text:
"""

TRANSACTION_EXTRACTION_PROMPT = """You are an expert bank statement transaction parser for Singapore banks.
Parse ALL transactions from the following bank statement page(s).

CRITICAL RULES:
- Each transaction has: transaction_date, value_date, description, withdrawal (if debit), deposit (if credit), balance
- Normalise ALL dates to "DD MMM" format (e.g. "30 NOV", "01 DEC"):
  - "01 DEC" → "01 DEC" (already correct — OCBC/UOB format)
  - "01-Sep-2025" → "01 SEP" (DBS format)
  - "01/12/2025" → "01 DEC"
- Amounts: return as plain numbers (no commas). E.g. 1943.69 not "1,943.69"
- Multi-line descriptions: concatenate into ONE description string separated by spaces.
  Many banks (especially DBS) have multi-line transaction details — combine ALL lines for one transaction.
- For DBS statements: the columns are "Date | Value Date | Transaction Details | Debit | Credit | Running Balance".
  Each transaction starts with a date row, followed by description continuation lines.
- "BALANCE B/F" or "BALANCE BROUGHT FORWARD" → transaction_type = "opening_balance"
- "BALANCE C/F" or "BALANCE CARRIED FORWARD" → transaction_type = "closing_balance"
- Withdrawals / Debits → transaction_type = "debit"
- Deposits / Credits → transaction_type = "credit"
- If the statement has a summary section like "Total Debit Count : 21 Total Debit Amount : 32,785.05", do NOT create transactions from the summary — only from individual transaction lines.
- channel: FAST, GIRO, ATM, DEBIT PURCHASE, PAYMENT/TRANSFER, CHEQUE, IBG, NETS, PayNow, INTERBANK GIRO, etc.
- counterparty: who the transaction is with (extracted from description). Look for company/person names.
- Do NOT skip any transactions. Extract EVERY single one.
- Do NOT invent transactions that aren't in the text.
- If a page has "BALANCE B/F" that was already in the previous batch, still include it (dedup happens later).

Return ONLY a valid JSON array (no markdown fences):
[
  {
    "transaction_date": "30 NOV",
    "value_date": "01 DEC",
    "description": "FAST PAYMENT OTHR GELMAX SG3P251128972769",
    "withdrawal": 1943.69,
    "deposit": null,
    "balance": 127543.16,
    "transaction_type": "debit",
    "channel": "FAST",
    "counterparty": "GELMAX",
    "reference": "SG3P251128972769"
  }
]

Bank statement page text:
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  Table-based extraction (structured PDFs — DBS, SCB, etc.)
# ═══════════════════════════════════════════════════════════════════════════════

# Column header aliases — maps various header labels to our canonical field names
_HEADER_ALIASES = {
    "date": "transaction_date",
    "txn date": "transaction_date",
    "transaction date": "transaction_date",
    "date & time": "transaction_date",
    "date and time": "transaction_date",
    "value date": "value_date",
    "val date": "value_date",
    "transaction details": "description",
    "details": "description",
    "description": "description",
    "particulars": "description",
    "counterparty": "counterparty",
    "debit": "debit",
    "withdrawal": "debit",
    "withdrawals": "debit",
    "dr": "debit",
    "credit": "credit",
    "deposit": "credit",
    "deposits": "credit",
    "cr": "credit",
    "running balance": "balance",
    "balance": "balance",
    "bal": "balance",
    "closing balance": "balance",
    "cheque": "cheque",
    "chq": "cheque",
    "reference": "reference",
    "ref": "reference",
}


def _normalise_header(raw: str) -> Optional[str]:
    """Map a raw column header to our canonical field name."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    # Strip non-ASCII (Chinese characters in OCBC headers etc.)
    cleaned = re.sub(r'[^\x00-\x7f]', '', cleaned).strip()
    # Replace newlines with spaces (e.g. 'Balance\n(SGD)')
    cleaned = cleaned.replace('\n', ' ').strip()
    # Try exact match first
    result = _HEADER_ALIASES.get(cleaned)
    if result:
        return result
    # Strip currency suffix like '(SGD)', '(USD)' etc.
    cleaned_no_ccy = re.sub(r'\s*\([A-Z]{3}\)\s*$', '', cleaned).strip()
    result = _HEADER_ALIASES.get(cleaned_no_ccy)
    if result:
        return result
    # Also try stripping leading '#' (sequence number column)
    if cleaned == '#' or cleaned == 'no' or cleaned == 'no.':
        return 'sequence'
    return None


def _parse_amount(val: str) -> Optional[float]:
    """Parse a monetary amount string like '6,540.00' → 6540.0. Returns None for empty."""
    if not val or not val.strip():
        return None
    cleaned = val.strip().replace(',', '').replace(' ', '')
    # Handle parentheses for negatives: (1,000.00) → -1000.0
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalise_date_to_dd_mmm(date_str: str) -> str:
    """Normalise various date formats to 'DD MMM'.
    '01-Sep-2025' → '01 SEP', '30 NOV' → '30 NOV', '01/12/2025' → '01 DEC'.
    '1 31 Dec 2025' → '31 DEC' (Aspire: sequence number + date).
    '30SEP2025' → '30 SEP' (HSBC: no separators).
    """
    if not date_str:
        return ""
    date_str = date_str.strip()
    # DDMMMYYYY — no separators (HSBC: 30SEP2025)
    m = re.search(r'(\d{2})([A-Za-z]{3})(\d{4})', date_str)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    # DD-MMM-YYYY (DBS)
    m = re.search(r'(\d{1,2})-([A-Za-z]{3})-\d{4}', date_str)
    if m:
        return f"{m.group(1).zfill(2)} {m.group(2).upper()}"
    # DD MMM YYYY or DD MMM (OCBC / ANEXT / Aspire)
    m = re.search(r'(\d{1,2})\s+([A-Za-z]{3})(?:\s+\d{4})?', date_str)
    if m:
        return f"{m.group(1).zfill(2)} {m.group(2).upper()}"
    # DD/MM/YYYY
    m = re.search(r'(\d{1,2})/(\d{1,2})(?:/\d{2,4})?', date_str)
    if m:
        months = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        mon = int(m.group(2))
        if 1 <= mon <= 12:
            return f"{m.group(1).zfill(2)} {months[mon]}"
    return date_str


def _detect_channel(description: str) -> str:
    """Detect payment channel from transaction description."""
    desc_upper = (description or "").upper()
    if "FAST PAYMENT" in desc_upper or "FAST" in desc_upper:
        return "FAST"
    if "INTERBANK GIRO" in desc_upper or "IBG" in desc_upper:
        return "INTERBANK GIRO"
    if "GIRO" in desc_upper:
        return "GIRO"
    if "ADVICE" in desc_upper or "ADV " in desc_upper:
        return "ADVICE"
    if "REMITTANCE" in desc_upper or "RTF " in desc_upper:
        return "REMITTANCE"
    if "ATM" in desc_upper:
        return "ATM"
    if "DEBIT PURCHASE" in desc_upper or "DEBIT PURC" in desc_upper:
        return "DEBIT PURCHASE"
    if "CHEQUE" in desc_upper or "CHQ" in desc_upper:
        return "CHEQUE"
    if "NETS" in desc_upper:
        return "NETS"
    if "PAYNOW" in desc_upper:
        return "PayNow"
    return "OTHER"


def _extract_counterparty(description: str) -> Optional[str]:
    """Extract counterparty name from multi-line transaction description."""
    if not description:
        return None
    lines = description.replace('\n', ' | ').split(' | ')
    # Skip first line (usually the channel like "FAST PAYMENT")
    # Skip lines that look like references (hex strings, long numbers, SGD amounts)
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        # Skip reference patterns
        if re.match(r'^[0-9a-fA-F]{16,}$', line):
            continue
        if re.match(r'^(EBGPP|X1AF|ADV |RTF |SGD |\d{14,})', line):
            continue
        if re.match(r'^\d+\s+U:', line):
            continue
        if re.match(r'^SGD\s+[\d,.]+$', line, re.IGNORECASE):
            continue
        if re.match(r'^(OTHER|SALARY PAYMENT|SUPPLIER PAYMENT|CLEARING LOANS)$', line, re.IGNORECASE):
            continue
        # This looks like a counterparty name
        if len(line) > 2 and any(c.isalpha() for c in line):
            return line
    return None


def _try_extract_tables(file_path: str) -> Optional[Dict]:
    """Try pdfplumber table extraction on the PDF.
    
    Returns a dict with:
        "account_info": {...} from header table (opening/closing balance, etc.)
        "transactions": [...] structured transaction list
        "column_headers": [...] detected column names
    Or None if tables cannot be extracted (borderless PDFs like OCBC).
    """
    import pdfplumber

    try:
        pdf = pdfplumber.open(file_path)
    except Exception as e:
        logger.warning(f"  Failed to open PDF for table extraction: {e}")
        return None

    all_transactions = []
    account_info_table = None
    column_headers = None
    header_only_count = 0  # Track tables with header but no data rows

    try:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            if not tables:
                # If we already found tables on earlier pages but this page has none,
                # that's okay (e.g. a summary/footer page). But if we haven't found
                # ANY tables yet on the first few pages, this PDF isn't table-based.
                if page_num < 2 and not all_transactions:
                    logger.info("  📊 No tables detected on first pages — PDF is not table-structured")
                    pdf.close()
                    return None
                continue

            for table in tables:
                if not table or len(table) < 1:
                    continue

                header_row = table[0]
                if not header_row:
                    continue

                # Map raw headers to canonical names
                mapped = [_normalise_header(str(h) if h else "") for h in header_row]

                # Is this the account info table? (has "Opening Balance" etc.)
                raw_str = " ".join(str(c) if c else "" for c in header_row).lower()
                if page_num == 0 and not account_info_table:
                    # Check if any cell mentions opening/account
                    all_cells = " ".join(
                        str(cell) if cell else ""
                        for row in table for cell in row
                    ).lower()
                    if "opening balance" in all_cells or "account number" in all_cells:
                        account_info_table = table
                        continue

                # Is this a transaction table? Must have date + (debit or credit) + balance
                if "transaction_date" not in mapped:
                    continue
                if "balance" not in mapped:
                    continue
                if "debit" not in mapped and "credit" not in mapped:
                    continue

                # If the table has only 1 row (header only, no data rows),
                # this is a header-only table (e.g. Aspire style with borderless data).
                # Track these and bail early — word-position extraction is better.
                if len(table) < 2:
                    header_only_count += 1
                    if header_only_count >= 2:
                        logger.info(
                            "  📊 Tables have headers but no data rows (borderless data) "
                            "— deferring to word-position extraction"
                        )
                        pdf.close()
                        return None
                    continue

                column_headers = mapped
                logger.debug(f"  Page {page_num+1}: found transaction table with {len(table)-1} rows")

                # Parse data rows
                for row in table[1:]:
                    if not row:
                        continue
                    # Build a dict from column mapping
                    row_data = {}
                    for ci, canonical in enumerate(mapped):
                        if canonical and ci < len(row):
                            row_data[canonical] = row[ci]

                    # Skip rows without a date (continuation rows, summary rows)
                    date_val = (row_data.get("transaction_date") or "").strip()
                    if not date_val or not re.match(r'\d', date_val):
                        continue

                    debit_amt = _parse_amount(row_data.get("debit", ""))
                    credit_amt = _parse_amount(row_data.get("credit", ""))
                    balance = _parse_amount(row_data.get("balance", ""))
                    description = (row_data.get("description") or "").replace('\n', ' ').strip()

                    # Determine transaction type
                    if debit_amt and not credit_amt:
                        txn_type = "debit"
                    elif credit_amt and not debit_amt:
                        txn_type = "credit"
                    elif debit_amt and credit_amt:
                        # Both columns filled — rare, treat larger as the type
                        txn_type = "debit" if debit_amt >= credit_amt else "credit"
                    else:
                        # No amount in either column — might be opening/closing balance
                        desc_upper = description.upper()
                        if "BALANCE B/F" in desc_upper or "OPENING" in desc_upper or "BALANCE BROUGHT" in desc_upper:
                            txn_type = "opening_balance"
                        elif "BALANCE C/F" in desc_upper or "CLOSING" in desc_upper or "BALANCE CARRIED" in desc_upper:
                            txn_type = "closing_balance"
                        else:
                            continue  # Skip rows with no amounts

                    txn = {
                        "transaction_date": _normalise_date_to_dd_mmm(date_val),
                        "value_date": _normalise_date_to_dd_mmm(
                            (row_data.get("value_date") or date_val).strip()
                        ),
                        "description": description,
                        "withdrawal": debit_amt,
                        "deposit": credit_amt,
                        "balance": balance,
                        "transaction_type": txn_type,
                        "channel": _detect_channel(description),
                        "counterparty": _extract_counterparty(
                            row_data.get("description", "")  # use original with newlines
                        ),
                        "reference": row_data.get("reference"),
                    }
                    all_transactions.append(txn)

    except Exception as e:
        logger.warning(f"  Table extraction error: {e}")
        pdf.close()
        return None

    num_pages = len(pdf.pages)
    pdf.close()

    if not all_transactions:
        return None

    # Parse account info from header table if found
    parsed_account_info = _parse_account_info_table(account_info_table) if account_info_table else {}

    logger.info(
        f"  📊 Table extraction successful: {len(all_transactions)} transactions "
        f"from {num_pages} pages (zero LLM calls for transactions!)"
    )

    return {
        "account_info": parsed_account_info,
        "transactions": all_transactions,
        "column_headers": column_headers,
    }


# ── Generic word-position extraction for ANY bank statement ────────────────
#
# This works for PDFs where columns are visually aligned — with or without
# grid lines.  We auto-discover the column layout from the header row using a
# broad dictionary of aliases that covers all SG banks.

# Canonical column names → all known aliases banks might use as headers
_COL_HEADER_ALIASES: Dict[str, List[str]] = {
    "transaction_date": [
        "transaction date", "txn date", "trans date", "date",
        "date & time", "date and time",
        "transaction", "trans",
    ],
    "value_date": [
        "value date", "posting date", "effective date",
    ],
    "description": [
        "description", "particulars", "details", "narrative",
        "remarks", "transaction details",
    ],
    "counterparty": [
        "counterparty", "payee", "beneficiary", "sender",
    ],
    "cheque": [
        "cheque", "chq", "check", "cheque no",
    ],
    "reference": [
        "reference", "ref", "ref no", "reference no",
    ],
    "withdrawal": [
        "withdrawal", "withdrawals", "debit", "debits",
        "debit amount", "withdrawal amount", "payments",
    ],
    "deposit": [
        "deposit", "deposits", "credit", "credits",
        "credit amount", "deposit amount", "receipts",
    ],
    "balance": [
        "balance", "running balance", "closing balance",
        "available balance", "ledger balance",
    ],
}


def _strip_non_ascii(s: str) -> str:
    """Remove non-ASCII chars (Chinese characters in bilingual headers)."""
    return re.sub(r'[^\x00-\x7f]', '', s).strip()


def _discover_column_layout(page) -> Optional[Dict]:
    """Auto-discover the column layout from a page's header row.

    Scans every text row (and merged adjacent rows within 16pt for multi-line
    headers like Aspire's ``Balance\\n(SGD)``), scores by how many canonical
    column-header aliases match, and picks the best.

    Returns a dict::

        {
            "header_y": int,            # y-coordinate of the main header row
            "header_y_max": int,        # bottom y of the (possibly merged) header band
            "columns": {                # discovered columns
                "withdrawal": {"x0": 331, "x1": 364},
                "deposit": {"x0": 426, "x1": 449},
                ...
            },
            "bounds": {                 # computed midpoint boundaries
                "withdrawal": (296.0, 393.0),
                "deposit": (393.0, 481.0),
                ...
            },
        }
    Or None if no suitable header row is found.
    """
    from collections import defaultdict

    words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=True)
    if not words:
        return None

    page_width = page.width or 612

    # Group words by y-position (4pt bands)
    y_groups: Dict[int, list] = defaultdict(list)
    for w in words:
        y_key = round(w["top"] / 4) * 4
        y_groups[y_key].append(w)

    sorted_ys = sorted(y_groups.keys())

    def _score_row(row_words_list):
        """Score a list of words against column aliases.  Returns (score, matches)."""
        # Build lowercased text (strip currency suffixes for matching)
        row_text = " ".join(_strip_non_ascii(w["text"]) for w in row_words_list).lower()
        # Also build a version with currency suffixes stripped
        row_text_no_ccy = re.sub(r'\([a-z]{3}\)', '', row_text).strip()

        matches: Dict[str, Dict] = {}
        score = 0

        for canonical, aliases in _COL_HEADER_ALIASES.items():
            for alias in aliases:
                if alias in row_text or alias in row_text_no_ccy:
                    # Find the word(s) whose text contributed to the alias
                    alias_words = set(alias.split())
                    for w in row_words_list:
                        wt = _strip_non_ascii(w["text"]).lower()
                        # Strip currency suffix from individual words too
                        wt_clean = re.sub(r'\s*\([a-z]{3}\)\s*$', '', wt).strip()
                        # Check: is the word text one of the alias words?
                        # OR does the word text contain the full alias (multi-word token)?
                        # OR does the alias contain the word text?
                        wt_words = set(wt_clean.split())
                        word_matches = (
                            (wt_clean and wt_clean in alias_words)
                            or (wt in alias_words)
                            or (alias in wt_clean)     # "date & time" word contains "date & time" alias
                            or (alias in wt)
                            or bool(wt_words & alias_words)  # any word in common
                        )
                        if word_matches:
                            if canonical not in matches:
                                matches[canonical] = {"x0": w["x0"], "x1": w["x1"]}
                            else:
                                matches[canonical]["x0"] = min(matches[canonical]["x0"], w["x0"])
                                matches[canonical]["x1"] = max(matches[canonical]["x1"], w["x1"])
                    if canonical in matches:
                        score += 1
                    break  # first alias match is enough

        return score, matches

    best_row_y: Optional[int] = None
    best_row_y_max: Optional[int] = None
    best_score = 0
    best_matches: Dict[str, Dict] = {}

    # Try single rows AND merged adjacent rows (for multi-line headers)
    for idx, y in enumerate(sorted_ys):
        # ── Single row ──
        row_words = sorted(y_groups[y], key=lambda w: w["x0"])
        score, matches = _score_row(row_words)

        has_amount = "withdrawal" in matches or "deposit" in matches
        has_balance = "balance" in matches
        if score > best_score and has_amount and has_balance:
            best_score = score
            best_row_y = y
            best_row_y_max = y
            best_matches = matches

        # ── Merge with next 1-2 adjacent rows (within 16pt gap) ──
        for span in (1, 2):
            if idx + span >= len(sorted_ys):
                break
            next_y = sorted_ys[idx + span]
            if next_y - y > 16:
                break
            # Combine words from adjacent rows
            merged_words = list(row_words)
            for s in range(1, span + 1):
                merged_words.extend(y_groups[sorted_ys[idx + s]])
            merged_words.sort(key=lambda w: w["x0"])

            mscore, mmatches = _score_row(merged_words)
            m_has_amount = "withdrawal" in mmatches or "deposit" in mmatches
            m_has_balance = "balance" in mmatches
            if mscore > best_score and m_has_amount and m_has_balance:
                best_score = mscore
                best_row_y = y
                best_row_y_max = sorted_ys[idx + span]
                best_matches = mmatches

    if best_row_y is None or best_score < 2:
        return None

    # ── Compute column boundaries using midpoints between adjacent headers ──
    sorted_cols = sorted(best_matches.items(), key=lambda kv: kv[1]["x0"])
    bounds: Dict[str, tuple] = {}

    for i, (name, pos) in enumerate(sorted_cols):
        mid = (pos["x0"] + pos["x1"]) / 2

        if i == 0:
            left = 0
        else:
            prev_mid = (sorted_cols[i - 1][1]["x0"] + sorted_cols[i - 1][1]["x1"]) / 2
            left = (prev_mid + mid) / 2

        if i == len(sorted_cols) - 1:
            right = page_width
        else:
            next_mid = (sorted_cols[i + 1][1]["x0"] + sorted_cols[i + 1][1]["x1"]) / 2
            right = (mid + next_mid) / 2

        bounds[name] = (round(left, 1), round(right, 1))

    return {
        "header_y": best_row_y,
        "header_y_max": best_row_y_max or best_row_y,
        "columns": best_matches,
        "bounds": bounds,
    }


def _assign_words_to_columns(
    row_words: List[Dict],
    col_bounds: Dict[str, tuple],
    page_width: float = 612,
) -> Dict[str, str]:
    """Assign words from a row to columns based on their x-position midpoint.

    Words that fall outside the rightmost column boundary (e.g. watermark text)
    are silently dropped.
    """
    cols: Dict[str, list] = {k: [] for k in col_bounds}
    max_right = max(r for _, r in col_bounds.values())
    for w in row_words:
        x_mid = (w["x0"] + w["x1"]) / 2
        if x_mid > max_right:
            continue  # outside all columns (watermark, footer, etc.)
        for col_name, (x_min, x_max) in col_bounds.items():
            if x_min <= x_mid <= x_max:
                cols[col_name].append(w["text"])
                break
    return {k: " ".join(v).strip() for k, v in cols.items()}


def _is_transaction_page(page, header_y: int) -> bool:
    """Check if a page likely contains transaction data (generic)."""
    text = page.extract_text() or ""
    # Skip legend / code-description pages
    if "TRANSACTION CODE DESCRIPTION" in text:
        return False
    # Skip pages with only a confirmation/disclaimer footer
    text_lower = text.lower()
    if "confirmation of validity" in text_lower and len(text.strip()) < 500:
        return False
    # Fast positive checks
    if "BALANCE B/F" in text or "BALANCE C/F" in text:
        return True
    if "Balance Brought Forward" in text or "Balance Carried Forward" in text:
        return True
    if re.search(
        r'\d{1,2}[\s\-/]?(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)',
        text, re.IGNORECASE,
    ):
        return True
    # Check if the page has a recognizable column header layout
    layout = _discover_column_layout(page)
    if layout:
        return True
    return False


def _extract_account_info_from_text(pages) -> Dict:
    """Extract account info from page text using generic regex patterns.

    Works for any SG bank — looks for common patterns like
    'Account No.', statement period, account holder name, etc.
    """
    info: Dict[str, Any] = {}

    for page in pages[:3]:
        text = page.extract_text() or ""
        lines = text.split("\n")

        for line in lines:
            s = line.strip()

            # Account number (various formats)
            if "account_number" not in info:
                m = re.search(
                    r'Account\s*(?:No\.?|Number)\s*:?\s*(\d[\d\s\-]+\d)',
                    s, re.IGNORECASE,
                )
                if m:
                    info["account_number"] = re.sub(r'[\s\-]', '', m.group(1))

            # Statement period: "1 DEC 2025 TO 31 DEC 2025" or "01-Sep-2025 to 30-Sep-2025"
            if "statement_period" not in info:
                m = re.search(
                    r'(\d{1,2}[\s\-][A-Za-z]{3}[\s\-]\d{4})\s+(?:TO|to|-)\s+(\d{1,2}[\s\-][A-Za-z]{3}[\s\-]\d{4})',
                    s,
                )
                if m:
                    info["statement_period"] = f"{m.group(1)} to {m.group(2)}"

            # Statement date (HSBC: "StatementDate 31OCT2025")
            if "statement_date" not in info:
                m = re.search(
                    r'Statement\s*Date\s*:?\s*(\d{1,2}[A-Za-z]{3}\d{4}|\d{1,2}[\s\-][A-Za-z]{3}[\s\-]\d{4})',
                    s, re.IGNORECASE,
                )
                if m:
                    info["statement_date"] = m.group(1)

            # Currency
            if "currency" not in info:
                m = re.search(r'\b(SGD|USD|MYR|IDR|EUR|GBP|AUD|HKD)\b', s)
                if m:
                    info["currency"] = m.group(1)

        # Account holder: first prominent all-caps line in the address block
        found_marker = False
        for line in lines:
            s = line.strip()
            if "STATEMENT OF ACCOUNT" in s.upper() or "Singapore" in s:
                found_marker = True
                continue
            if found_marker and s and len(s) > 5 and s == s.upper():
                # Skip known non-name patterns
                if any(skip in s for skip in [
                    "ACCOUNT", "OCBC", "DBS", "UOB", "STATEMENT",
                    "TRANSACTION", "BALANCE", "BUSINESS",
                    "PAGE", "DATE",
                ]):
                    continue
                if re.match(r'^[A-Z\s.&,\-()]+$', s) and "account_holder" not in info:
                    info["account_holder"] = s
                    break

    return info


def _try_extract_words(file_path: str) -> Optional[Dict]:
    """Generic word-position extraction for ANY bank statement PDF.

    Auto-discovers the column layout from the header row, then extracts
    transactions by assigning each word to its column based on x-position.
    Works for bordered AND borderless PDFs — but for bordered PDFs the
    table-based ``_try_extract_tables()`` is preferred because it handles
    multi-line cells more reliably.

    Handles **multi-account / multi-currency** PDFs (e.g. ANEXT SGD + USD
    sections) by detecting currency section headers and Balance Brought
    Forward lines.  Each section is tagged with its currency and balance
    chains are validated independently per section.

    Returns the same dict structure as ``_try_extract_tables()`` or ``None``
    if no column header row can be discovered.
    """
    import pdfplumber
    from collections import defaultdict

    try:
        pdf = pdfplumber.open(file_path)
    except Exception as e:
        logger.warning(f"  Word-position extraction: failed to open PDF: {e}")
        return None

    num_pages = len(pdf.pages)

    # ── Auto-discover column layout from the first few pages ──
    layout: Optional[Dict] = None
    for page in pdf.pages[:5]:
        layout = _discover_column_layout(page)
        if layout:
            break

    if not layout:
        pdf.close()
        return None

    col_bounds = layout["bounds"]
    header_y = layout["header_y"]
    header_y_max = layout.get("header_y_max", header_y)
    data_y_min = header_y_max + 8  # data starts just below the full header band

    discovered_cols = list(layout["columns"].keys())
    logger.info(
        f"  📊 Auto-discovered columns: {discovered_cols} "
        f"(header at y={header_y}..{header_y_max})"
    )

    # Ensure we have the minimum columns needed for extraction
    if "balance" not in col_bounds:
        pdf.close()
        return None
    if "withdrawal" not in col_bounds and "deposit" not in col_bounds:
        pdf.close()
        return None

    # ── Extract account info from page text ──
    account_info = _extract_account_info_from_text(pdf.pages)

    # ── Helper: which column holds "date" info? ──
    date_col = (
        "transaction_date" if "transaction_date" in col_bounds
        else "value_date" if "value_date" in col_bounds
        else None
    )
    # Helper: which column holds descriptions?
    desc_col = (
        "description" if "description" in col_bounds
        else "counterparty" if "counterparty" in col_bounds
        else "cheque" if "cheque" in col_bounds
        else None
    )

    # Set of known ISO currency codes for section detection
    _CURRENCY_CODES = {
        'SGD', 'USD', 'EUR', 'GBP', 'CNY', 'JPY', 'AUD', 'HKD',
        'MYR', 'IDR', 'THB', 'PHP', 'INR', 'KRW', 'NZD', 'CHF',
        'CAD', 'TWD', 'VND',
    }

    # ── Process each transaction page ──
    all_transactions: List[Dict] = []
    current_currency: Optional[str] = account_info.get("currency")
    current_account_section: int = 0  # Increments at each new section boundary

    date_re = re.compile(
        r'\d{1,2}[\s\-/]?'
        r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)',
        re.IGNORECASE,
    )
    amount_re = re.compile(r'^[\d,]+\.\d{2}$')
    summary_re = re.compile(
        r'(Total Withdrawal|Total Deposit|Total Interest|Average Balance|'
        r'Withholding Tax|Total Debit|Total Credit|'
        r'Grand Total|Closing Statement|'
        r'ENDOFSTATEMENT|END\s*OF\s*STATEMENT)',
        re.IGNORECASE,
    )
    # Footer text that should be skipped (Deposit Insurance disclaimers, etc.)
    footer_re = re.compile(
        r'(Deposit\s*Insurance|Singaporedollardeposit|'
        r'currency\s*deposits.*not\s*insured|'
        r'structureddeposits|'
        r'Issued\s*by\s*The\s*Hongkong|'
        r'S\$100,000\s*in\s*aggregate|'
        r'aggregate\s*per\s*depositor)',
        re.IGNORECASE,
    )
    # HSBC-specific page summary pattern: "WITHDRAWALS  305,465.02DR  ASAT  31OCT2025"
    hsbc_summary_re = re.compile(
        r'^(WITHDRAWALS?|DEPOSITS?)\b',
        re.IGNORECASE,
    )

    for page_idx, page in enumerate(pdf.pages):
        if not _is_transaction_page(page, header_y):
            continue

        words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=True)

        # ── Per-page header detection for correct data_y_min ──
        # Some PDFs (Aspire) have different header positions on page 1 vs rest.
        page_layout = _discover_column_layout(page)
        if page_layout:
            page_data_y_min = page_layout.get("header_y_max", page_layout["header_y"]) + 8
        else:
            page_data_y_min = data_y_min

        # ── Detect currency section header on this page ──
        # Look for standalone currency codes ABOVE the data area
        for w in words:
            if w["text"].strip() in _CURRENCY_CODES and w["top"] < page_data_y_min:
                new_ccy = w["text"].strip()
                if new_ccy != current_currency:
                    current_currency = new_ccy
                    current_account_section += 1
                    logger.info(
                        f"  💱 Page {page_idx+1}: new currency section '{current_currency}' "
                        f"(section #{current_account_section})"
                    )

        # Group words by y-position (4-point bands)
        y_groups: Dict[int, list] = defaultdict(list)
        for w in words:
            y_key = round(w["top"] / 4) * 4
            y_groups[y_key].append(w)

        sorted_ys = sorted(y_groups.keys())
        current_txn: Optional[Dict] = None
        past_closing: bool = False  # Set True after BALANCE CARRIED FORWARD
        in_summary: bool = False    # Set True when we hit page summary (WITHDRAWALS/DEPOSITS)

        for y in sorted_ys:
            if y < page_data_y_min:
                continue

            row_words = sorted(y_groups[y], key=lambda w: w["x0"])

            # Skip header remnant rows: e.g. "(SGD)" sub-label from multi-line headers
            row_full = " ".join(w["text"].strip() for w in row_words).strip()
            if re.match(r'^\(?[A-Z]{3}\)?$', row_full):
                continue

            cols = _assign_words_to_columns(row_words, col_bounds, page.width)

            # Get the text from the appropriate columns
            date_text = cols.get(date_col, "") if date_col else ""
            desc_text = cols.get(desc_col, "").strip() if desc_col else ""
            w_text = cols.get("withdrawal", "")
            d_text = cols.get("deposit", "")
            b_text = cols.get("balance", "")

            # Also check 'counterparty' column if separate from description
            cpty_text = ""
            if "counterparty" in col_bounds and desc_col != "counterparty":
                cpty_text = cols.get("counterparty", "").strip()

            # Build a combined description from all non-amount non-date columns
            if not desc_text:
                for col_name in col_bounds:
                    if col_name in ("withdrawal", "deposit", "balance",
                                    "transaction_date", "value_date"):
                        continue
                    if cols.get(col_name, "").strip():
                        desc_text = cols[col_name].strip()
                        break

            # Skip summary/total rows (but only if they lack a transaction date,
            # since some banks use descriptions like "Interest Earned" for real txns)
            if summary_re.search(desc_text) and not (date_text and date_re.search(date_text.strip())):
                continue
            if summary_re.search(row_full):
                continue

            # Skip footer/disclaimer text (Deposit Insurance Scheme, etc.)
            if footer_re.search(row_full):
                continue

            # Skip HSBC-style page summary rows: "WITHDRAWALS 305,465.02DR ASAT ..."
            # These appear when the date column holds "WITHDRAWALS" or "DEPOSITS"
            # and can span 2 y-groups, so set a flag to skip the next row too.
            if date_text and hsbc_summary_re.match(date_text.strip()):
                in_summary = True
                continue
            if in_summary:
                # Check if this row is the continuation of the summary
                # (contains "ASAT" or "BALANCECARRIEDFORWARD") or has no date
                row_full_upper = row_full.upper()
                if "ASAT" in row_full_upper or "BALANCECARRIED" in row_full_upper:
                    continue
                elif "BALANCEBROUGHT" in row_full_upper:
                    in_summary = False  # Reset — this is a new section
                elif not (date_text and date_re.search(date_text.strip())):
                    # Still in summary zone (no transaction date) — skip
                    continue
                else:
                    in_summary = False  # New transaction date — resume

            # ── Check for mid-page currency section boundary ──
            # e.g. a standalone "USD" or "SGD" line in the data area
            row_full_text = " ".join(w["text"] for w in row_words).strip()
            if row_full_text in _CURRENCY_CODES:
                # Flush current transaction
                if current_txn:
                    all_transactions.append(current_txn)
                    current_txn = None
                if row_full_text != current_currency:
                    current_currency = row_full_text
                    current_account_section += 1
                    logger.info(
                        f"  💱 Page {page_idx+1}: mid-page currency section '{current_currency}' "
                        f"(section #{current_account_section})"
                    )
                continue

            has_txn_date = bool(date_text and date_re.search(date_text.strip()))
            is_balance_entry = bool(re.search(
                r'BALANCE\s*[BC]/F|OPENING\s+BALANCE|CLOSING\s+BALANCE|'
                r'BALANCE\s*BROUGHT|BALANCE\s*CARRIED',
                desc_text, re.IGNORECASE,
            ))

            # ── Track closing/opening balance boundaries ──
            # After BALANCE CARRIED FORWARD, skip all rows until we see
            # BALANCE BROUGHT FORWARD (avoids page summaries/footers)
            is_opening = bool(re.search(
                r'BALANCE\s*B/F|BALANCE\s*BROUGHT|OPENING\s+BALANCE',
                desc_text, re.IGNORECASE,
            ))
            is_closing = bool(re.search(
                r'BALANCE\s*C/F|BALANCE\s*CARRIED|CLOSING\s+BALANCE',
                desc_text, re.IGNORECASE,
            ))
            if is_opening:
                past_closing = False
            elif past_closing and not is_balance_entry:
                # We're in the footer zone after closing balance — skip row
                continue
            # Treat '-' as zero (Aspire uses '-' for no amount)
            if w_text.strip() == '-':
                w_text = ""
            if d_text.strip() == '-':
                d_text = ""
            has_amount = bool(w_text or d_text or b_text)
            has_desc = bool(desc_text)
            amount_only = has_amount and not has_desc and not has_txn_date

            if has_txn_date or is_balance_entry:
                # ── Start of a new transaction ──
                if current_txn:
                    all_transactions.append(current_txn)

                # Mark that we've passed a closing balance (for footer skipping)
                if is_closing:
                    past_closing = True

                current_txn = {
                    "txn_date": date_text.strip(),
                    "value_date": cols.get("value_date", "").strip() or date_text.strip(),
                    "description": desc_text,
                    "counterparty_text": cpty_text,
                    "withdrawal": w_text,
                    "deposit": d_text,
                    "balance": b_text,
                    "currency": current_currency,
                    "account_section": current_account_section,
                    "page_number": page_idx + 1,
                }

            elif current_txn and has_amount:
                # ── Check if this is a NEW sub-transaction (HSBC pattern) ──
                # If the current transaction already has a balance AND this row
                # has a new balance, it's a separate sub-transaction that
                # inherits the date from the previous one.
                txn_has_balance = bool(current_txn["balance"])
                new_has_balance = bool(b_text)
                if txn_has_balance and new_has_balance:
                    # Flush current and start a new sub-transaction
                    all_transactions.append(current_txn)
                    current_txn = {
                        "txn_date": current_txn["txn_date"],  # inherit date
                        "value_date": current_txn["value_date"],
                        "description": desc_text or "",
                        "counterparty_text": cpty_text,
                        "withdrawal": w_text,
                        "deposit": d_text,
                        "balance": b_text,
                        "currency": current_currency,
                        "account_section": current_account_section,
                        "page_number": page_idx + 1,
                    }
                else:
                    # Fill in missing amounts for the current transaction
                    if has_desc:
                        current_txn["description"] += " " + desc_text
                        if cpty_text:
                            current_txn["counterparty_text"] += " " + cpty_text
                    if not current_txn["withdrawal"] and w_text:
                        current_txn["withdrawal"] = w_text
                    if not current_txn["deposit"] and d_text:
                        current_txn["deposit"] = d_text
                    if not current_txn["balance"] and b_text:
                        current_txn["balance"] = b_text

            elif current_txn and has_desc:
                # Description continuation (no amounts on this row)
                current_txn["description"] += " " + desc_text
                if cpty_text:
                    current_txn["counterparty_text"] += " " + cpty_text

        # Flush last transaction on the page
        if current_txn:
            all_transactions.append(current_txn)
            current_txn = None

    pdf.close()

    if not all_transactions:
        return None

    # ── Convert raw word-position rows into canonical transaction dicts ──
    final_transactions: List[Dict] = []

    for raw in all_transactions:
        desc = (raw["description"] or "").strip()
        desc_upper = desc.upper()

        # Parse amounts — extract first valid number from each column text
        # (column text may include trailing watermark/reversed characters)
        def _extract_amount(text: str, allow_dr: bool = False) -> Optional[float]:
            if not text:
                return None
            cleaned = text.replace(" ", "").strip()
            if cleaned == '-' or cleaned == '':
                return None
            m = re.search(r'([\d,]+\.\d{2})\s*(DR)?', cleaned, re.IGNORECASE)
            if m:
                val = float(m.group(1).replace(",", ""))
                # DR suffix means debit/negative balance (HSBC convention)
                if allow_dr and m.group(2):
                    val = -val
                return val
            return None

        withdrawal = _extract_amount(raw.get("withdrawal"))
        deposit = _extract_amount(raw.get("deposit"))
        balance = _extract_amount(raw.get("balance"), allow_dr=True)

        # Determine transaction type
        if any(kw in desc_upper for kw in [
            "BALANCE B/F", "BALANCE BROUGHT", "BALANCEBROUGHT",
            "OPENING BALANCE",
        ]):
            txn_type = "opening_balance"
        elif any(kw in desc_upper for kw in [
            "BALANCE C/F", "BALANCE CARRIED", "BALANCECARRIED",
            "CLOSING BALANCE",
        ]):
            txn_type = "closing_balance"
            # For C/F, clear the withdrawal/deposit (those are summary totals)
            withdrawal = None
            deposit = None
        elif withdrawal and not deposit:
            txn_type = "debit"
        elif deposit and not withdrawal:
            txn_type = "credit"
        elif withdrawal and deposit:
            txn_type = "debit" if withdrawal >= deposit else "credit"
        else:
            continue  # No amounts — skip

        # Build description: merge desc + counterparty if separate columns
        full_desc = desc
        if raw.get("counterparty_text"):
            full_desc = f"{desc} | {raw['counterparty_text'].strip()}"

        txn = {
            "transaction_date": _normalise_date_to_dd_mmm(raw["txn_date"]),
            "value_date": _normalise_date_to_dd_mmm(
                raw["value_date"] or raw["txn_date"]
            ),
            "description": full_desc,
            "withdrawal": withdrawal,
            "deposit": deposit,
            "balance": balance,
            "transaction_type": txn_type,
            "channel": _detect_channel(full_desc),
            "counterparty": raw.get("counterparty_text") or _extract_counterparty(full_desc),
            "reference": None,
            "currency": raw.get("currency"),
            "account_section": raw.get("account_section", 0),
        }
        final_transactions.append(txn)

    if not final_transactions:
        return None

    # ── Detect reverse-chronological order (e.g. Aspire lists newest first) ──
    # Try a quick chain check on first 20 txns both forward and reversed.
    # Pick the order that yields more valid balance transitions.
    def _quick_chain_score(txns, limit=20):
        subset = [t for t in txns if t.get("transaction_type") in ("credit", "debit") and t.get("balance") is not None][:limit]
        if len(subset) < 2:
            return 0
        valid = 0
        for i in range(1, len(subset)):
            prev_b = subset[i-1]["balance"]
            curr_b = subset[i]["balance"]
            amt = subset[i].get("withdrawal") or subset[i].get("deposit") or 0
            ttype = subset[i]["transaction_type"]
            exp = round((prev_b - amt) if ttype == "debit" else (prev_b + amt), 2)
            if abs(exp - curr_b) <= 0.02:
                valid += 1
        return valid

    fwd_score = _quick_chain_score(final_transactions)
    rev_score = _quick_chain_score(list(reversed(final_transactions)))
    if rev_score > fwd_score:
        final_transactions.reverse()
        logger.info(
            f"  🔄 Detected reverse-chronological order (fwd={fwd_score}, rev={rev_score}) "
            f"— reversed to forward order"
        )

    # Detect multi-account
    sections = set(t.get("account_section", 0) for t in final_transactions)
    if len(sections) > 1:
        logger.info(
            f"  📊 Multi-account PDF: {len(sections)} sections detected "
            f"(currencies: {sorted(set(t.get('currency', '?') for t in final_transactions))})"
        )

    logger.info(
        f"  📊 Word-position extraction successful: {len(final_transactions)} transactions "
        f"from {num_pages} pages (zero LLM calls for transactions!)"
    )

    return {
        "account_info": account_info,
        "transactions": final_transactions,
        "column_headers": discovered_cols,
    }


def _parse_account_info_table(table: List[List]) -> Dict:
    """Parse account info from the header table (DBS-style).
    
    Example rows:
        ['Account Number :', '0725385342 - SGD', 'Account Name :', 'HOH JIA PTE. LTD.', None]
        ['Opening Balance :', '84,650.03 01-Sep-2025', ...]
        ['Ledger Balance :', '157,657.34 30-Sep-2025', ...]
    """
    info = {}
    for row in table:
        cells = [str(c).strip() if c else "" for c in row]
        row_text = " ".join(cells).lower()

        for i, cell in enumerate(cells):
            cell_lower = cell.lower()
            next_cell = cells[i + 1] if i + 1 < len(cells) else ""

            if "account number" in cell_lower and next_cell:
                # "0725385342 - SGD" → extract number and currency
                m = re.match(r'([\d\-]+)\s*(?:-\s*(\w+))?', next_cell)
                if m:
                    info["account_number"] = m.group(1).strip()
                    if m.group(2):
                        info["currency"] = m.group(2).strip()

            elif "account name" in cell_lower and next_cell:
                # Strip account number suffix if present
                name = re.sub(r'\s*-\s*\d[\d\-]+.*$', '', next_cell).strip()
                info["account_holder"] = name

            elif "product type" in cell_lower and next_cell:
                info["account_type"] = next_cell.strip()

            elif "opening balance" in cell_lower and next_cell:
                m = re.match(r'([\d,]+\.\d{2})\s*(.*)', next_cell)
                if m:
                    info["opening_balance"] = _parse_amount(m.group(1))
                    if m.group(2):
                        info["opening_date"] = m.group(2).strip()

            elif "ledger balance" in cell_lower and next_cell:
                m = re.match(r'([\d,]+\.\d{2})\s*(.*)', next_cell)
                if m:
                    info["closing_balance"] = _parse_amount(m.group(1))
                    if m.group(2):
                        info["closing_date"] = m.group(2).strip()

            elif "available balance" in cell_lower and next_cell:
                m = re.match(r'([\d,]+\.\d{2})', next_cell)
                if m:
                    info["available_balance"] = _parse_amount(m.group(1))

    # Derive statement period from opening/closing dates
    if info.get("opening_date") and info.get("closing_date"):
        info["statement_period"] = f"{info['opening_date']} to {info['closing_date']}"

    return info


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _is_skip_page(text: str) -> bool:
    """Should this page be skipped entirely? (legend, T&C, blank, etc.)"""
    text_stripped = text.strip()
    if len(text_stripped) < 80:          # near-blank page
        return True
    
    # If page has monetary amounts (like 1,234.56), it likely has transactions — don't skip
    has_monetary = bool(re.search(r'\d{1,3}(?:,\d{3})*\.\d{2}', text_stripped))
    # If page has date patterns, it likely has transactions
    has_dates = bool(
        re.search(r'\d{1,2}\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', text_stripped, re.IGNORECASE)
        or re.search(r'\d{1,2}[\-/][A-Za-z]{3}[\-/]\d{4}', text_stripped)
    )
    if has_monetary and has_dates:
        return False  # This page has transaction-like data, don't skip
    
    for pattern in SKIP_PATTERNS:
        if pattern.lower() in text_stripped.lower():
            # Only skip if this pattern is the DOMINANT content (>40% of the page)
            idx = text_stripped.lower().find(pattern.lower())
            if idx is not None and (len(text_stripped) - idx) > len(text_stripped) * 0.4:
                return True
    return False


def _has_transactions(text: str) -> bool:
    """Does this page contain transaction data?"""
    has_balance_header = bool(re.search(r'balance|bal\.?|running\s*balance', text, re.IGNORECASE))
    # Flexible date patterns:
    #   "01 DEC"          — OCBC, UOB
    #   "01-Sep-2025"     — DBS
    #   "01/12/2025"      — various
    #   "2025-12-01"      — ISO
    has_date_pattern = bool(
        re.search(r'\d{1,2}\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', text, re.IGNORECASE)
        or re.search(r'\d{1,2}[\-/](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\-/]?\d{0,4}', text, re.IGNORECASE)
        or re.search(r'\d{1,2}/\d{1,2}(/\d{2,4})?', text)
        or re.search(r'\d{4}-\d{2}-\d{2}', text)
    )
    has_amounts = bool(re.search(r'\d{1,3}(?:,\d{3})*\.\d{2}', text))
    return has_balance_header and has_date_pattern and has_amounts


def _detect_bank_from_logo(file_path: str) -> Optional[str]:
    """Detect bank by sending the page-1 header image to GPT-4o Vision.
    
    Crops the top 20% of page 1 (where the logo lives) and asks the LLM
    to identify the Singapore bank.  This is the most reliable method
    because many banks (e.g. DBS) only show their name in the logo image,
    not in extractable text.
    """
    KNOWN_BANKS = list(BANK_IDENTIFIERS.keys())  # canonical names
    try:
        img = pdf_page_to_image(file_path, page_number=0, dpi=150)
        w, h = img.size
        header = img.crop((0, 0, w, int(h * 0.20)))  # top 20%
        b64 = image_to_base64(header)

        response = chat_completion_with_image(
            prompt=(
                "Look at this bank statement header image and identify the Singapore bank "
                "from its logo or branding.\n"
                "Return ONLY the bank name — one of: "
                + ", ".join(KNOWN_BANKS)
                + ".\n"
                "If you cannot identify it, return: unknown"
            ),
            image_base64=b64,
            temperature=0.0,
            max_tokens=30,
        )
        bank = response.strip().strip('"').strip("'")
        # Normalise to our canonical list
        for known in KNOWN_BANKS:
            if known.lower() == bank.lower():
                return known
        # Fuzzy — if the response *contains* a known bank name
        for known in KNOWN_BANKS:
            if known.lower() in bank.lower():
                return known
        logger.warning(f"  🏦 Vision returned unrecognised bank: '{bank}'")
        return None
    except Exception as e:
        logger.warning(f"  🏦 Vision bank detection failed: {e}")
        return None


def _detect_bank_from_text(pages: List[Dict]) -> str:
    """Text-based fallback: scan extracted text for bank identifiers."""
    sample = " ".join(p["text"] for p in pages[:3])
    sample_lower = sample.lower()

    # 1. Bank-specific product names (most reliable — no false positives)
    for bank_name, products in BANK_PRODUCT_IDENTIFIERS.items():
        for product in products:
            if product.lower() in sample_lower:
                logger.info(f"  🏦 Text fallback: product name '{product}' → {bank_name}")
                return bank_name

    # 2. Explicit identifiers (word-boundary for short names to avoid false matches)
    for bank_name, identifiers in BANK_IDENTIFIERS.items():
        for ident in identifiers:
            if len(ident) <= 4:
                if re.search(r'\b' + re.escape(ident) + r'\b', sample, re.IGNORECASE):
                    return bank_name
            else:
                if ident.lower() in sample_lower:
                    return bank_name

    # 3. DBS-style format heuristic
    if re.search(r'Account Details.*Account Number', sample, re.DOTALL | re.IGNORECASE):
        if re.search(r'\d{2}-[A-Z][a-z]{2}-\d{4}', sample):
            logger.info("  🏦 Text fallback: DBS-style format patterns")
            return "DBS"

    return "unknown"


def _detect_bank(pages: List[Dict], file_path: str = None) -> str:
    """Detect which bank the statement is from.

    Strategy (ordered by reliability):
    1. **Vision** — crop page-1 header, send to GPT-4o to read the logo
    2. **Text product names** — e.g. "AUTOSAVE ACCOUNT" → DBS
    3. **Text identifiers** — e.g. "OCBC Bank"
    4. **Text heuristics** — format patterns
    """
    # --- Primary: Vision-based logo detection ---
    if file_path:
        vision_bank = _detect_bank_from_logo(file_path)
        if vision_bank:
            logger.info(f"  🏦 Bank detected via logo (vision): {vision_bank}")
            return vision_bank

    # --- Fallback: Text-based detection ---
    text_bank = _detect_bank_from_text(pages)
    if text_bank != "unknown":
        logger.info(f"  🏦 Bank detected via text: {text_bank}")
    return text_bank


def _clean_page_text(text: str, bank: str = "unknown") -> str:
    """Remove repeated headers/footers/noise specific to the detected bank."""
    # Bank-specific noise
    noise_patterns = BANK_NOISE_PATTERNS.get(bank, []) + BANK_NOISE_PATTERNS.get("_default", [])
    for pat in noise_patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)
    return text.strip()


def _batch_pages_with_overlap(
    pages: List[Dict], bank: str = "unknown", batch_size: int = 3, overlap: int = 0
) -> List[Dict]:
    """
    Build batches of cleaned transaction pages.
    
    Uses adaptive batch sizing: if pages are text-dense (>1500 chars avg),
    use smaller batches (2 pages) so the LLM doesn't miss transactions.
    For sparser pages (OCBC-style), 5 pages per batch is fine.
    
    Returns list of {"text": str, "page_numbers": list[int]}
    """
    # Filter to transaction-bearing pages only
    txn_pages = []
    for page in pages:
        text = page["text"]
        if _is_skip_page(text):
            logger.debug(f"  Skipping page {page['page_number']} (skip pattern)")
            continue
        if not _has_transactions(text):
            logger.debug(f"  Skipping page {page['page_number']} (no transactions detected)")
            continue
        cleaned = _clean_page_text(text, bank)
        txn_pages.append({"page_number": page["page_number"], "text": cleaned})

    if not txn_pages:
        logger.warning("  ⚠️ No transaction pages found after filtering!")
        return []

    # Adaptive batch sizing based on text density
    avg_chars = sum(len(p["text"]) for p in txn_pages) / len(txn_pages)
    if avg_chars > 1500:  # DBS-style verbose multi-line descriptions
        batch_size = min(batch_size, 2)
        logger.info(f"  📐 Dense text ({avg_chars:.0f} chars/page avg) → batch_size={batch_size}")
    elif avg_chars > 1000:  # Medium density
        batch_size = min(batch_size, 3)
    # else: keep default batch_size

    logger.info(f"  📄 {len(txn_pages)} transaction pages found, batch_size={batch_size}")

    batches = []
    i = 0
    while i < len(txn_pages):
        end = min(i + batch_size, len(txn_pages))
        batch_items = txn_pages[i:end]
        batch_text = "\n\n".join(
            f"--- Page {p['page_number']} ---\n{p['text']}" for p in batch_items
        )
        page_nums = [p["page_number"] for p in batch_items]
        batches.append({"text": batch_text, "page_numbers": page_nums})
        # Advance by (batch_size - overlap), so the last `overlap` pages repeat
        step = max(1, batch_size - overlap)
        i += step

    return batches


def _parse_llm_json(response: str) -> Union[list, dict]:
    """Robustly parse LLM JSON response (strips markdown fences, handles edge cases)."""
    response = response.strip()
    response = re.sub(r'^```(?:json)?\s*', '', response)
    response = re.sub(r'\s*```$', '', response)
    response = response.strip()
    # Handle case where LLM wraps in {"transactions": [...]}
    parsed = json.loads(response)
    if isinstance(parsed, dict) and "transactions" in parsed:
        return parsed["transactions"]
    return parsed


def _deduplicate_transactions(transactions: List[Dict]) -> List[Dict]:
    """
    Remove duplicate transactions from overlapping batches.
    
    Uses fuzzy matching: two transactions are duplicates if they share:
    - Same balance (exact match — this is the strongest signal)
    - Same date
    - Same transaction type
    - Similar amount (within 0.01)
    
    We also do exact fingerprint dedup as a first pass.
    """
    if not transactions:
        return transactions

    # Pass 1: Exact fingerprint dedup
    seen_exact = set()
    pass1 = []
    for t in transactions:
        date = (t.get("value_date") or t.get("transaction_date") or "").strip()
        desc = (t.get("description") or "").strip()[:60]
        amt = t.get("withdrawal") or t.get("deposit") or 0
        bal = t.get("balance") or 0
        txn_type = t.get("transaction_type", "")
        key = f"{date}|{desc}|{amt:.2f}|{bal:.2f}|{txn_type}"
        if key not in seen_exact:
            seen_exact.add(key)
            pass1.append(t)

    exact_removed = len(transactions) - len(pass1)

    # Pass 2: Balance-based fuzzy dedup
    # If two transactions have the same balance AND same date AND same type,
    # they are almost certainly the same transaction extracted from an overlapping page.
    seen_balance = set()
    pass2 = []
    for t in pass1:
        bal = t.get("balance")
        date = (t.get("value_date") or t.get("transaction_date") or "").strip()
        txn_type = t.get("transaction_type", "")
        amt = t.get("withdrawal") or t.get("deposit") or 0

        if bal is not None and txn_type in ("credit", "debit"):
            fuzzy_key = f"{date}|{bal:.2f}|{txn_type}|{amt:.2f}"
            if fuzzy_key in seen_balance:
                continue
            seen_balance.add(fuzzy_key)
        pass2.append(t)

    fuzzy_removed = len(pass1) - len(pass2)
    total_removed = exact_removed + fuzzy_removed

    if total_removed > 0:
        logger.info(
            f"  🔄 Deduplication removed {total_removed} duplicates "
            f"(exact: {exact_removed}, fuzzy: {fuzzy_removed})"
        )
    return pass2


def _validate_balance_chain(transactions: List[Dict]) -> Dict:
    """
    Validate that running balances form a consistent chain.
    
    Supports **multi-account / multi-currency** PDFs: if transactions carry
    an ``account_section`` field, the chain is validated independently per
    section (e.g. SGD section, USD section).  Section boundaries are also
    detected by ``opening_balance`` / ``closing_balance`` transaction types
    for PDFs that don't carry explicit section tags.
    
    For each consecutive pair of transactions within the same section, check:
      prev_balance ± amount ≈ curr_balance  (within tolerance for rounding)
    
    Returns {
        "total_checked": int,
        "valid": int,
        "invalid": int,
        "chain_accuracy_pct": float,
        "breaks": [{"index": i, "expected": x, "actual": y, ...}],
        "sections": int,  # number of independent account sections found
    }
    """
    from collections import defaultdict

    # ── Partition transactions into independent sections ──
    # Use account_section tag if available; otherwise use opening_balance markers
    has_sections = any(t.get("account_section", 0) != 0 for t in transactions)

    sections: Dict[int, List[Dict]] = defaultdict(list)

    if has_sections:
        # Use explicit section tags
        for t in transactions:
            sec = t.get("account_section", 0)
            sections[sec].append(t)
    else:
        # Detect sections from opening_balance markers
        current_section = 0
        for t in transactions:
            if t.get("transaction_type") == "opening_balance" and sections[current_section]:
                # New section starts (but only if the current section already has transactions)
                current_section += 1
            sections[current_section].append(t)

    # ── Validate each section's balance chain independently ──
    total_valid = 0
    total_invalid = 0
    all_breaks = []
    tolerance = 0.02  # allow 2 cent rounding difference

    for sec_id in sorted(sections.keys()):
        sec_txns = [
            t for t in sections[sec_id]
            if t.get("transaction_type") in ("credit", "debit")
            and t.get("balance") is not None
        ]
        if len(sec_txns) < 2:
            continue

        for i in range(1, len(sec_txns)):
            prev_bal = sec_txns[i - 1]["balance"]
            curr_bal = sec_txns[i]["balance"]
            amt = sec_txns[i].get("withdrawal") or sec_txns[i].get("deposit") or 0
            txn_type = sec_txns[i]["transaction_type"]

            if txn_type == "debit":
                expected = round(prev_bal - amt, 2)
            else:
                expected = round(prev_bal + amt, 2)

            diff = abs(expected - curr_bal)
            if diff <= tolerance:
                total_valid += 1
            else:
                total_invalid += 1
                if len(all_breaks) < 20:
                    all_breaks.append({
                        "index": i,
                        "section": sec_id,
                        "date": sec_txns[i].get("value_date") or sec_txns[i].get("transaction_date"),
                        "description": (sec_txns[i].get("description") or "")[:50],
                        "expected_balance": expected,
                        "actual_balance": curr_bal,
                        "difference": round(diff, 2),
                    })

    total = total_valid + total_invalid
    pct = round(total_valid / total * 100, 1) if total > 0 else 100.0

    return {
        "total_checked": total,
        "valid": total_valid,
        "invalid": total_invalid,
        "chain_accuracy_pct": pct,
        "breaks": all_breaks,
        "sections": len(sections),
    }


def _compute_accuracy_score(
    transactions: List[Dict],
    metrics: Dict,
    balance_chain: Dict,
) -> Dict:
    """
    Compute an overall extraction accuracy score (0–100) based on multiple signals.
    
    Signals:
    1. Balance chain continuity (40% weight)
    2. Opening/closing balance match — does BALANCE B/F and C/F exist? (20% weight)
    3. Credit + Debit totals plausibility — sum of debits + opening ≈ sum of credits + closing? (20% weight)
    4. No-amount transactions ratio — txns missing amounts are suspicious (10% weight)
    5. Duplicate ratio — how many dupes were caught (10% weight, inverted — fewer is better)
    """
    scores = {}

    # 1. Balance chain (40%)
    chain_pct = balance_chain.get("chain_accuracy_pct", 0)
    scores["balance_chain"] = {"value": chain_pct, "weight": 40}

    # 2. Opening/closing balance present (20%)
    has_opening = metrics.get("opening_balance") is not None
    has_closing = metrics.get("closing_balance") is not None
    ob_score = 100.0 if (has_opening and has_closing) else (50.0 if (has_opening or has_closing) else 0.0)
    scores["opening_closing_present"] = {"value": ob_score, "weight": 20}

    # 3. Accounting equation check (20%)
    # opening + total_credits - total_debits ≈ closing
    # For multi-currency statements, the simple equation doesn't apply across currencies,
    # so if balance chain is 100%, we trust the extraction fully.
    if chain_pct >= 99.9:
        equation_score = 100.0
    elif has_opening and has_closing:
        opening = metrics["opening_balance"]
        closing = metrics["closing_balance"]
        total_credits = metrics.get("total_amount_of_credit_transactions", 0)
        total_debits = metrics.get("total_amount_of_debit_transactions", 0)
        expected_closing = round(opening + total_credits - total_debits, 2)
        diff = abs(expected_closing - closing)
        # Score: 100 if exact, degrades linearly. >5% off = 0
        relative_error = diff / max(abs(closing), 1)
        equation_score = max(0, 100 - relative_error * 100 / 0.05)  # 0% error=100, 5% error=0
        equation_score = min(100.0, equation_score)
    else:
        equation_score = 50.0  # can't verify
    scores["accounting_equation"] = {"value": round(equation_score, 1), "weight": 20}

    # 4. Missing amount ratio (10%)
    actual_txns = [t for t in transactions if t.get("transaction_type") in ("credit", "debit")]
    missing_amount = sum(
        1 for t in actual_txns
        if not t.get("withdrawal") and not t.get("deposit")
    )
    missing_pct = (missing_amount / max(len(actual_txns), 1)) * 100
    missing_score = max(0, 100 - missing_pct * 5)  # each 1% missing = -5 points
    scores["completeness"] = {"value": round(missing_score, 1), "weight": 10}

    # 5. Null balance ratio (10%)
    null_balance = sum(1 for t in actual_txns if t.get("balance") is None)
    null_pct = (null_balance / max(len(actual_txns), 1)) * 100
    null_score = max(0, 100 - null_pct * 5)
    scores["balance_completeness"] = {"value": round(null_score, 1), "weight": 10}

    # Weighted average
    total_weight = sum(s["weight"] for s in scores.values())
    weighted_sum = sum(s["value"] * s["weight"] for s in scores.values())
    overall = round(weighted_sum / total_weight, 1) if total_weight > 0 else 0

    # Grade
    if overall >= 95:
        grade = "A+"
    elif overall >= 90:
        grade = "A"
    elif overall >= 80:
        grade = "B"
    elif overall >= 70:
        grade = "C"
    elif overall >= 50:
        grade = "D"
    else:
        grade = "F"

    return {
        "overall_score": overall,
        "grade": grade,
        "breakdown": scores,
        "balance_chain_detail": balance_chain,
    }


# ─── Categorization (multi-bank) ──────────────────────────────────────────────

def _categorize_transaction(description: str, channel: str) -> str:
    desc_upper = (description or "").upper()
    # Salary & payroll
    if any(kw in desc_upper for kw in ["SALARY", "PAYROLL", "WAGES", "CPF", "CPF CONTRIBUTION"]):
        return "salary_payroll"
    # Rent & property
    if any(kw in desc_upper for kw in ["RENT", "LEASE", "TENANCY", "PROPERTY"]):
        return "rent"
    # Utilities
    if any(kw in desc_upper for kw in [
        "SP SERVICES", "SINGTEL", "STARHUB", "M1", "UTILITIES", "POWER SUPPLY",
        "TOWN COUNCIL", "PUB ", "WATER", "ELECTRICITY", "SIMBA TELECOM"
    ]):
        return "utilities"
    # Food & beverage
    if any(kw in desc_upper for kw in [
        "FOOD", "RESTAURANT", "CAFE", "COFFEE", "MCDONALD", "DELIVEROO", "GRAB FOOD",
        "FOODPANDA", "KFC", "SUBWAY", "STARBUCKS", "TOAST BOX", "YA KUN", "BAKERY",
        "ESPRESSO", "KOPITIAM", "HAWKER"
    ]):
        return "food_beverage"
    # Transport
    if any(kw in desc_upper for kw in [
        "TAXI", "GRAB ", "GOJEK", "COMFORTDELGRO", "CDG ENGIE", "CDG EGIE",
        "TRANSIT", "EZ-LINK", "LTA", "PARKING", "SBS TRANSIT", "SMRT"
    ]):
        return "transport"
    # Supplier payments
    if any(kw in desc_upper for kw in ["CARDUP", "SUPPLIER", "INVOICE", "VENDOR", "PURCHASE ORDER"]):
        return "supplier_payment"
    # Revenue / income
    if any(kw in desc_upper for kw in [
        "ADYEN", "STRIPE", "PAYNOW", "COLLECTION", "REVENUE", "SALES",
        "PAYMENT RECEIVED", "CUSTOMER PAYMENT"
    ]):
        return "revenue"
    # Loan & financing
    if any(kw in desc_upper for kw in ["LOAN", "MORTGAGE", "FINANCING", "EMI", "INSTALMENT"]):
        return "loan"
    # Tax & government
    if any(kw in desc_upper for kw in ["IRAS", "GST", "TAX", "ACRA", "GOVERNMENT", "CUSTOMS"]):
        return "tax_government"
    # Insurance
    if any(kw in desc_upper for kw in ["INSURANCE", "AIA", "PRUDENTIAL", "GREAT EASTERN", "NTUC INCOME"]):
        return "insurance"
    # Fees & charges
    if any(kw in desc_upper for kw in [
        "BANK CHARGE", "SERVICE CHARGE", "FEE", "INTEREST", "LATE CHARGE",
        "ANNUAL FEE", "COMM ON"
    ]):
        return "fees_charges"
    # Fund transfers
    if any(kw in desc_upper for kw in ["TRANSFER", "TRF", "IBG", "REMITTANCE", "TELEGRAPHIC"]):
        return "transfer"
    # Card purchases
    if "DEBIT PURCHASE" in desc_upper or "DEBIT PURC" in desc_upper or "VISA" in desc_upper:
        return "purchase"
    return "other"


def _is_cash_transaction(description: str) -> bool:
    return any(kw in (description or "").upper() for kw in [
        "CASH DEPOSIT", "CASH WITHDRAWAL", "ATM WITHDRAWAL", "ATM DEPOSIT",
        "CDM", "CASH DEP", "ATM"
    ])


def _is_cheque_transaction(description: str) -> bool:
    return any(kw in (description or "").upper() for kw in [
        "CHEQUE", "CHQ", "CHEQUE DEPOSIT", "CHEQUE WITHDRAWAL"
    ])


def _compute_metrics(transactions: List[Dict], account_info: Dict) -> Dict:
    """Compute 25+ metrics from extracted transactions, with per-currency breakdown."""
    credits = [t for t in transactions if t.get("transaction_type") == "credit"]
    debits = [t for t in transactions if t.get("transaction_type") == "debit"]

    credit_amounts = [t["deposit"] for t in credits if t.get("deposit")]
    debit_amounts = [t["withdrawal"] for t in debits if t.get("withdrawal")]

    opening_balance = None
    closing_balance = None
    for t in transactions:
        if t.get("transaction_type") == "opening_balance":
            opening_balance = t.get("balance")
        elif t.get("transaction_type") == "closing_balance":
            closing_balance = t.get("balance")

    balances = [t["balance"] for t in transactions if t.get("balance") is not None]

    # Fallback: if no explicit opening/closing, use first/last balance
    if opening_balance is None and balances:
        opening_balance = balances[0]
    if closing_balance is None and balances:
        closing_balance = balances[-1]

    cash_deposits = [t for t in credits if _is_cash_transaction(t.get("description", ""))]
    cash_withdrawals = [t for t in debits if _is_cash_transaction(t.get("description", ""))]
    cheque_withdrawals = [t for t in debits if _is_cheque_transaction(t.get("description", ""))]
    fees = [t for t in debits if _categorize_transaction(t.get("description", ""), "") == "fees_charges"]

    # ── Per-currency breakdown ──
    currencies = sorted(set(t.get("currency") or "SGD" for t in transactions))
    currency_metrics = {}
    for ccy in currencies:
        ccy_txns = [t for t in transactions if (t.get("currency") or "SGD") == ccy]
        ccy_credits = [t for t in ccy_txns if t.get("transaction_type") == "credit"]
        ccy_debits = [t for t in ccy_txns if t.get("transaction_type") == "debit"]
        ccy_credit_amts = [t["deposit"] for t in ccy_credits if t.get("deposit")]
        ccy_debit_amts = [t["withdrawal"] for t in ccy_debits if t.get("withdrawal")]
        ccy_balances = [t["balance"] for t in ccy_txns if t.get("balance") is not None]

        # Opening/closing for this currency
        ccy_opening = None
        ccy_closing = None
        for t in ccy_txns:
            if t.get("transaction_type") == "opening_balance":
                ccy_opening = t.get("balance")
            elif t.get("transaction_type") == "closing_balance":
                ccy_closing = t.get("balance")
        if ccy_opening is None and ccy_balances:
            ccy_opening = ccy_balances[0]
        if ccy_closing is None and ccy_balances:
            ccy_closing = ccy_balances[-1]

        currency_metrics[ccy] = {
            "currency": ccy,
            "opening_balance": ccy_opening,
            "closing_balance": ccy_closing,
            "total_credits": len(ccy_credits),
            "total_credit_amount": round(sum(ccy_credit_amts), 2),
            "total_debits": len(ccy_debits),
            "total_debit_amount": round(sum(ccy_debit_amts), 2),
            "max_balance": max(ccy_balances) if ccy_balances else None,
            "min_balance": min(ccy_balances) if ccy_balances else None,
            "avg_balance": round(statistics.mean(ccy_balances), 2) if ccy_balances else None,
            "transaction_count": len([t for t in ccy_txns if t.get("transaction_type") in ("credit", "debit")]),
        }

    # Primary currency = the one with the most transactions
    primary_ccy = max(currencies, key=lambda c: len([
        t for t in transactions
        if (t.get("currency") or "SGD") == c and t.get("transaction_type") in ("credit", "debit")
    ])) if currencies else "SGD"

    result = {
        "account_holder": account_info.get("account_holder"),
        "bank": account_info.get("bank"),
        "account_number": account_info.get("account_number"),
        "currency": primary_ccy,
        "statement_period": account_info.get("statement_period"),
        "months_of_statement": account_info.get("statement_period"),
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "max_eod_balance": max(balances) if balances else None,
        "min_eod_balance": min(balances) if balances else None,
        "avg_eod_balance": round(statistics.mean(balances), 2) if balances else None,
        "total_no_of_credit_transactions": len(credits),
        "total_amount_of_credit_transactions": round(sum(credit_amounts), 2),
        "total_no_of_debit_transactions": len(debits),
        "total_amount_of_debit_transactions": round(sum(debit_amounts), 2),
        "average_deposit": round(statistics.mean(credit_amounts), 2) if credit_amounts else 0.0,
        "average_withdrawal": round(statistics.mean(debit_amounts), 2) if debit_amounts else 0.0,
        "max_debit_transaction": max(debit_amounts) if debit_amounts else 0.0,
        "min_debit_transaction": min(debit_amounts) if debit_amounts else 0.0,
        "max_credit_transaction": max(credit_amounts) if credit_amounts else 0.0,
        "min_credit_transaction": min(credit_amounts) if credit_amounts else 0.0,
        "total_no_of_cash_deposits": len(cash_deposits),
        "total_amount_of_cash_deposits": round(sum(t.get("deposit", 0) or 0 for t in cash_deposits), 2),
        "total_no_of_cash_withdrawals": len(cash_withdrawals),
        "total_amount_of_cash_withdrawals": round(sum(t.get("withdrawal", 0) or 0 for t in cash_withdrawals), 2),
        "total_no_of_cheque_withdrawals": len(cheque_withdrawals),
        "total_amount_of_cheque_withdrawals": round(sum(t.get("withdrawal", 0) or 0 for t in cheque_withdrawals), 2),
        "total_fees_charged": round(sum(t.get("withdrawal", 0) or 0 for t in fees), 2),
    }

    # Add per-currency breakdown only if multi-currency
    if len(currencies) > 1:
        result["currency_breakdown"] = currency_metrics

    return result


# ─── Agent ────────────────────────────────────────────────────────────────────

class ExtractionAgent(BaseAgent):
    def run(self, document_id: str, db: Session) -> dict:
        logger.info(f"Extraction agent running for document {document_id}")

        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        # 1. Extract text from all pages (needed for bank detection + fallback)
        logger.info(f"  📄 Extracting text from {doc.page_count} pages...")
        is_scanned = is_scanned_pdf(doc.file_path)
        if is_scanned:
            logger.info("  🔍 Scanned/image PDF detected — running OCR via GPT-4o Vision...")
            pages = ocr_all_pages(doc.file_path)
        else:
            pages = extract_text_with_pdfplumber(doc.file_path)
        if not pages:
            raise ValueError("No text could be extracted from the PDF")

        # 2. Detect bank (vision logo first, then text fallback)
        bank = _detect_bank(pages, file_path=doc.file_path)
        logger.info(f"  🏦 Detected bank: {bank}")

        # 3. Try TABLE-BASED extraction first (works for bordered PDFs: DBS, SCB, etc.)
        #    Skip for scanned PDFs — pdfplumber can't extract tables from images.
        table_result = None
        if not is_scanned:
            logger.info("  📊 Trying table-based extraction...")
            table_result = _try_extract_tables(doc.file_path)

        if table_result and table_result["transactions"]:
            # ── Table path: structured extraction (no LLM for transactions) ──
            all_transactions = table_result["transactions"]
            extraction_method = "table"
            pages_processed = doc.page_count
            logger.info(
                f"  ✅ Table extraction: {len(all_transactions)} transactions "
                f"(zero LLM calls for transactions)"
            )

            # Account info: merge table-extracted info with LLM info
            logger.info("  🏦 Extracting account info...")
            first_pages_text = "\n\n".join(p["text"] for p in pages[:2])
            llm_account_info = self._extract_account_info(first_pages_text)
            table_account_info = table_result.get("account_info", {})

            # Table info is more reliable for balances; LLM for bank name etc.
            account_info = llm_account_info.copy()
            # Override with table-extracted values where available
            for key in ["account_number", "account_holder", "currency",
                        "account_type", "statement_period"]:
                if table_account_info.get(key):
                    account_info[key] = table_account_info[key]

            # Inject opening/closing balance into transactions if from table header
            if table_account_info.get("opening_balance") is not None:
                # Check if opening_balance transaction already exists
                has_opening = any(
                    t["transaction_type"] == "opening_balance" for t in all_transactions
                )
                if not has_opening:
                    all_transactions.insert(0, {
                        "transaction_date": _normalise_date_to_dd_mmm(
                            table_account_info.get("opening_date", "")
                        ),
                        "value_date": _normalise_date_to_dd_mmm(
                            table_account_info.get("opening_date", "")
                        ),
                        "description": "OPENING BALANCE",
                        "withdrawal": None,
                        "deposit": None,
                        "balance": table_account_info["opening_balance"],
                        "transaction_type": "opening_balance",
                        "channel": "",
                        "counterparty": None,
                        "reference": None,
                    })

            if table_account_info.get("closing_balance") is not None:
                has_closing = any(
                    t["transaction_type"] == "closing_balance" for t in all_transactions
                )
                if not has_closing:
                    all_transactions.append({
                        "transaction_date": _normalise_date_to_dd_mmm(
                            table_account_info.get("closing_date", "")
                        ),
                        "value_date": _normalise_date_to_dd_mmm(
                            table_account_info.get("closing_date", "")
                        ),
                        "description": "CLOSING BALANCE",
                        "withdrawal": None,
                        "deposit": None,
                        "balance": table_account_info["closing_balance"],
                        "transaction_type": "closing_balance",
                        "channel": "",
                        "counterparty": None,
                        "reference": None,
                    })

        else:
            # ── Try WORD-POSITION extraction (borderless PDFs like OCBC) ──
            #    Skip for scanned PDFs — pdfplumber can't extract words from images.
            word_result = None
            if not is_scanned:
                logger.info("  📊 Table extraction not available — trying word-position extraction...")
                word_result = _try_extract_words(doc.file_path)

            if word_result and word_result["transactions"]:
                # ── Word-position path: structured extraction from borderless PDF ──
                all_transactions = word_result["transactions"]
                extraction_method = "words"
                pages_processed = doc.page_count

                logger.info(
                    f"  ✅ Word-position extraction: {len(all_transactions)} transactions "
                    f"(zero LLM calls for transactions)"
                )

                # Account info: merge word-extracted info with LLM info
                logger.info("  🏦 Extracting account info...")
                first_pages_text = "\n\n".join(p["text"] for p in pages[:2])
                llm_account_info = self._extract_account_info(first_pages_text)
                word_account_info = word_result.get("account_info", {})

                account_info = llm_account_info.copy()
                for key in ["account_number", "account_holder", "currency",
                            "account_type", "statement_period"]:
                    if word_account_info.get(key):
                        account_info[key] = word_account_info[key]

            else:
                # ── LLM path: last resort for unstructured/scanned PDFs ──
                extraction_method = "llm" if not is_scanned else "ocr+llm"
                if is_scanned:
                    logger.info("  📊 Scanned PDF — using OCR text + LLM parsing")
                else:
                    logger.info("  📊 Word-position extraction not available — using LLM text parsing")

                # Extract account info via LLM
                logger.info("  🏦 Extracting account info...")
                first_pages_text = "\n\n".join(p["text"] for p in pages[:2])
                account_info = self._extract_account_info(first_pages_text)

                # Build page batches and extract transactions via LLM
                logger.info("  💳 Extracting transactions via LLM...")
                batches = _batch_pages_with_overlap(pages, bank=bank, batch_size=3, overlap=0)
                logger.info(f"  💳 Processing {len(batches)} batches...")

                all_transactions = []
                for i, batch in enumerate(batches):
                    logger.info(f"    Batch {i+1}/{len(batches)} (pages {batch['page_numbers']})...")
                    try:
                        txns = self._extract_transactions(batch["text"])
                        all_transactions.extend(txns)
                        logger.info(f"    → Extracted {len(txns)} transactions")
                    except Exception as e:
                        logger.error(f"    ❌ Batch {i+1} failed: {str(e)}")

                logger.info(f"  💳 Raw transactions extracted: {len(all_transactions)}")
                pages_processed = len(batches)

        logger.info(f"  🏦 Bank: {account_info.get('bank')}, Account: {account_info.get('account_number')}")

        # Use detected bank name if LLM got it wrong
        if bank != "unknown" and account_info.get("bank") != bank:
            logger.info(f"  🏦 Overriding LLM bank '{account_info.get('bank')}' with detected '{bank}'")
            account_info["bank"] = bank

        # 5. Deduplicate transactions
        all_transactions = _deduplicate_transactions(all_transactions)
        logger.info(f"  💳 After dedup: {len(all_transactions)} transactions")

        # 6. Validate balance chain
        logger.info("  🔗 Validating balance chain...")
        balance_chain = _validate_balance_chain(all_transactions)
        logger.info(
            f"  🔗 Balance chain: {balance_chain['valid']}/{balance_chain['total_checked']} valid "
            f"({balance_chain['chain_accuracy_pct']}%)"
        )

        # 7. Store raw transactions in DB
        logger.info("  💾 Storing transactions in database...")
        self._store_transactions(doc, all_transactions, db)

        # 8. Compute and store metrics
        logger.info("  📊 Computing metrics...")
        metrics = _compute_metrics(all_transactions, account_info)
        self._store_metrics(doc, metrics, db)

        # 9. Compute accuracy score
        logger.info("  🎯 Computing accuracy score...")
        accuracy = _compute_accuracy_score(all_transactions, metrics, balance_chain)
        logger.info(
            f"  🎯 Extraction accuracy: {accuracy['overall_score']}/100 (Grade: {accuracy['grade']})"
        )

        # 10. Update aggregated metrics if in a group
        if doc.upload_group_id:
            self._update_aggregated_metrics(doc.upload_group_id, db)

        summary_parts = [
            f"Bank: {account_info.get('bank', 'Unknown')}",
            f"Account: {account_info.get('account_number', 'Unknown')}",
            f"Holder: {account_info.get('account_holder', 'Unknown')}",
            f"Period: {account_info.get('statement_period', 'Unknown')}",
            f"Transactions: {len(all_transactions)}",
            f"Opening: {metrics.get('opening_balance', 'N/A')}",
            f"Closing: {metrics.get('closing_balance', 'N/A')}",
            f"Total Credits: {metrics.get('total_amount_of_credit_transactions', 0):.2f}",
            f"Total Debits: {metrics.get('total_amount_of_debit_transactions', 0):.2f}",
            f"Method: {extraction_method}",
            f"Accuracy: {accuracy['overall_score']}/100 ({accuracy['grade']})",
        ]
        if metrics.get("currency_breakdown"):
            currencies = list(metrics["currency_breakdown"].keys())
            summary_parts.append(f"Currencies: {', '.join(currencies)}")

        return {
            "results": {
                "account_info": account_info,
                "metrics": metrics,
                "transaction_count": len(all_transactions),
                "pages_processed": pages_processed,
                "extraction_method": extraction_method,
                "accuracy": accuracy,
            },
            "summary": " | ".join(summary_parts),
            "risk_level": "low",
        }

    def _extract_account_info(self, first_pages_text: str) -> dict:
        try:
            response = chat_completion(
                messages=[
                    {"role": "system", "content": "You are an expert bank statement parser for Singapore banks. Return only valid JSON."},
                    {"role": "user", "content": ACCOUNT_INFO_PROMPT + first_pages_text[:4000]},
                ],
                temperature=0.0,
                max_tokens=500,
            )
            return _parse_llm_json(response)
        except Exception as e:
            logger.error(f"Account info extraction failed: {e}")
            return self._fallback_account_info(first_pages_text)

    def _fallback_account_info(self, text: str) -> dict:
        """Regex-based fallback when LLM fails — works for major SG banks."""
        info = {
            "account_holder": None, "bank": None,
            "account_number": None, "currency": "SGD",
            "statement_period": None,
        }
        for bank_name, identifiers in BANK_IDENTIFIERS.items():
            for ident in identifiers:
                if ident.lower() in text.lower():
                    info["bank"] = bank_name
                    break
            if info["bank"]:
                break
        # Account number patterns vary by bank
        acct_match = (
            re.search(r'Account\s*No\.?\s*[:\s]*(\d[\d\-]+\d)', text, re.IGNORECASE)
            or re.search(r'Account\s*Number\s*[:\s]*(\d[\d\-]+\d)', text, re.IGNORECASE)
            or re.search(r'A/C\s*No\.?\s*[:\s]*(\d[\d\-]+\d)', text, re.IGNORECASE)
        )
        if acct_match:
            info["account_number"] = acct_match.group(1)
        # Statement period — flexible patterns
        period_match = (
            re.search(r'(\d{1,2}\s+\w+\s+\d{4})\s+(?:TO|to|-)\s+(\d{1,2}\s+\w+\s+\d{4})', text)
            or re.search(r'Statement\s+Period\s*[:\s]*(.+)', text, re.IGNORECASE)
        )
        if period_match:
            if period_match.lastindex and period_match.lastindex >= 2:
                info["statement_period"] = f"{period_match.group(1)} to {period_match.group(2)}"
            else:
                info["statement_period"] = period_match.group(1).strip()
        return info

    def _extract_transactions(self, page_text: str) -> List[Dict]:
        response = chat_completion(
            messages=[
                {"role": "system", "content": "You are an expert bank statement transaction parser for Singapore banks. Return only valid JSON arrays. Do not wrap in markdown."},
                {"role": "user", "content": TRANSACTION_EXTRACTION_PROMPT + page_text},
            ],
            temperature=0.0,
            max_tokens=16000,
        )
        transactions = _parse_llm_json(response)
        if not isinstance(transactions, list):
            raise ValueError(f"Expected list, got {type(transactions)}")
        return transactions

    def _store_transactions(self, doc: Document, transactions: List[Dict], db: Session):
        db.query(RawTransaction).filter(RawTransaction.document_id == doc.id).delete()
        stored = 0
        for txn in transactions:
            txn_type = txn.get("transaction_type", "")
            if txn_type in ("opening_balance", "closing_balance"):
                continue
            description = txn.get("description", "")
            channel = txn.get("channel", "")
            raw_txn = RawTransaction(
                document_id=doc.id,
                upload_group_id=doc.upload_group_id,
                date=txn.get("value_date") or txn.get("transaction_date"),
                description=description,
                transaction_type=txn_type,
                amount=txn.get("withdrawal") or txn.get("deposit"),
                balance=txn.get("balance"),
                reference=txn.get("reference"),
                category=_categorize_transaction(description, channel),
                counterparty=txn.get("counterparty"),
                channel=channel,
                is_cash=_is_cash_transaction(description),
                is_cheque=_is_cheque_transaction(description),
                currency=txn.get("currency", "SGD"),
                page_number=txn.get("page_number"),
                raw_text=json.dumps(txn),
            )
            db.add(raw_txn)
            stored += 1
        db.commit()
        logger.info(f"  💾 Stored {stored} transactions")

    def _store_metrics(self, doc: Document, metrics: Dict, db: Session):
        db.query(StatementMetrics).filter(StatementMetrics.document_id == doc.id).delete()
        # Remove non-column fields before persisting to DB
        db_metrics = {k: v for k, v in metrics.items() if k != "currency_breakdown"}
        stmt_metrics = StatementMetrics(
            document_id=doc.id,
            upload_group_id=doc.upload_group_id,
            **db_metrics,
        )
        db.add(stmt_metrics)
        db.commit()
        logger.info("  💾 Stored statement metrics")

    def _update_aggregated_metrics(self, upload_group_id: str, db: Session):
        all_metrics = (
            db.query(StatementMetrics)
            .filter(StatementMetrics.upload_group_id == upload_group_id)
            .all()
        )
        if not all_metrics:
            return
        db.query(AggregatedMetrics).filter(
            AggregatedMetrics.upload_group_id == upload_group_id
        ).delete()
        agg = AggregatedMetrics(
            upload_group_id=upload_group_id,
            account_holder=all_metrics[0].account_holder,
            bank=all_metrics[0].bank,
            account_number=all_metrics[0].account_number,
            currency=all_metrics[0].currency or "SGD",
            total_statements=len(all_metrics),
            period_covered=(
                f"{all_metrics[0].statement_period} — {all_metrics[-1].statement_period}"
                if len(all_metrics) > 1 else all_metrics[0].statement_period
            ),
            overall_max_eod_balance=max((m.max_eod_balance or 0) for m in all_metrics),
            overall_min_eod_balance=min((m.min_eod_balance or float('inf')) for m in all_metrics),
            overall_avg_eod_balance=round(statistics.mean((m.avg_eod_balance or 0) for m in all_metrics), 2),
            avg_opening_balance=round(statistics.mean((m.opening_balance or 0) for m in all_metrics), 2),
            avg_closing_balance=round(statistics.mean((m.closing_balance or 0) for m in all_metrics), 2),
            total_credit_transactions=sum(m.total_no_of_credit_transactions or 0 for m in all_metrics),
            total_credit_amount=round(sum(m.total_amount_of_credit_transactions or 0 for m in all_metrics), 2),
            total_debit_transactions=sum(m.total_no_of_debit_transactions or 0 for m in all_metrics),
            total_debit_amount=round(sum(m.total_amount_of_debit_transactions or 0 for m in all_metrics), 2),
            overall_avg_deposit=round(statistics.mean((m.average_deposit or 0) for m in all_metrics), 2),
            overall_avg_withdrawal=round(statistics.mean((m.average_withdrawal or 0) for m in all_metrics), 2),
            overall_max_debit=max((m.max_debit_transaction or 0) for m in all_metrics),
            overall_max_credit=max((m.max_credit_transaction or 0) for m in all_metrics),
            total_cash_deposits=sum(m.total_no_of_cash_deposits or 0 for m in all_metrics),
            total_cash_deposit_amount=round(sum(m.total_amount_of_cash_deposits or 0 for m in all_metrics), 2),
            total_cash_withdrawals=sum(m.total_no_of_cash_withdrawals or 0 for m in all_metrics),
            total_cash_withdrawal_amount=round(sum(m.total_amount_of_cash_withdrawals or 0 for m in all_metrics), 2),
            total_cheque_withdrawals=sum(m.total_no_of_cheque_withdrawals or 0 for m in all_metrics),
            total_cheque_withdrawal_amount=round(sum(m.total_amount_of_cheque_withdrawals or 0 for m in all_metrics), 2),
            total_fees=round(sum(m.total_fees_charged or 0 for m in all_metrics), 2),
            monthly_credit_totals=[],
            monthly_debit_totals=[],
            monthly_balances=[],
        )
        db.add(agg)
        db.commit()
        logger.info(f"  💾 Updated aggregated metrics for group {upload_group_id}")
