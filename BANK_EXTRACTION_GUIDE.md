# Bank Statement Extraction — Technical Reference Guide

> **Source file:** `backend/agents/extraction.py` (~2400 lines)
> **Last updated:** January 2025

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Three-Tier Extraction Strategy](#2-three-tier-extraction-strategy)
3. [Bank Detection](#3-bank-detection)
4. [Supported Banks & Identifiers](#4-supported-banks--identifiers)
5. [Tier 1 — Table-Based Extraction](#5-tier-1--table-based-extraction)
6. [Tier 2 — Word-Position Extraction](#6-tier-2--word-position-extraction)
7. [Tier 3 — LLM Fallback](#7-tier-3--llm-fallback)
8. [Per-Bank Handling Details](#8-per-bank-handling-details)
9. [Column Mapping & Header Aliases](#9-column-mapping--header-aliases)
10. [Date Normalisation](#10-date-normalisation)
11. [Amount Parsing](#11-amount-parsing)
12. [Multi-Currency / Multi-Account PDFs](#12-multi-currency--multi-account-pdfs)
13. [Balance Chain Validation](#13-balance-chain-validation)
14. [Accuracy Scoring](#14-accuracy-scoring)
15. [Transaction Enrichment](#15-transaction-enrichment)
16. [Noise Filtering & Page Skipping](#16-noise-filtering--page-skipping)
17. [Deduplication](#17-deduplication)
18. [Adding Support for a New Bank](#18-adding-support-for-a-new-bank)

---

## 1. Architecture Overview

The `ExtractionAgent` is responsible for:

1. **Extracting text** from every page of the uploaded PDF (via `pdfplumber`, or OCR via GPT-4o Vision for scanned docs).
2. **Detecting the bank** (logo vision → product-name text → generic text identifiers).
3. **Extracting transactions** using a 3-tier cascade: Table → Word-position → LLM.
4. **Validating** the balance chain for accuracy.
5. **Computing metrics** (25+ financial KPIs) and an overall accuracy score.
6. **Storing** everything to the SQLite database.

```
┌─────────────────────────────────────────────────────┐
│                   PDF Upload                         │
└──────────────────────┬──────────────────────────────┘
                       ▼
              ┌────────────────┐
              │  Extract Text  │  pdfplumber / OCR (GPT-4o Vision)
              └───────┬────────┘
                      ▼
              ┌────────────────┐
              │  Detect Bank   │  Vision logo → Product names → Text IDs
              └───────┬────────┘
                      ▼
         ┌────────────┴────────────┐
         ▼                         ▼
  ┌──────────────┐         ┌──────────────┐
  │ Tier 1: Table│ ──fail──▶│ Tier 2: Words│ ──fail──▶ Tier 3: LLM
  │ (pdfplumber) │         │ (x-position) │
  └──────┬───────┘         └──────┬───────┘
         │                        │
         └────────┬───────────────┘
                  ▼
        ┌──────────────────┐
        │ Validate & Score │  Balance chain, accuracy score
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ Store in DB      │  Transactions + Metrics
        └──────────────────┘
```

### Key Design Decisions

- **Zero LLM calls** for transaction parsing whenever possible — Tier 1 and Tier 2 use pure rule-based PDF parsing.
- **LLM is only used** for: (a) account info extraction from header text, (b) bank logo detection via Vision, and (c) Tier 3 fallback for scanned/unstructured PDFs.
- **Multi-currency support** — PDFs with multiple currency sections (e.g. ANEXT SGD + USD) are handled by detecting currency boundaries and validating each section independently.

---

## 2. Three-Tier Extraction Strategy

| Tier | Method | When Used | LLM Calls | Speed |
|------|--------|-----------|-----------|-------|
| **Tier 1** | Table-based (`_try_extract_tables`) | PDFs with bordered tables (DBS, SCB) | 0 | ⚡ Fastest |
| **Tier 2** | Word-position (`_try_extract_words`) | Borderless but text-aligned PDFs (OCBC, HSBC, Aspire, ANEXT) | 0 | ⚡ Fast |
| **Tier 3** | LLM parsing (`_extract_transactions`) | Scanned PDFs, or when Tiers 1 & 2 fail | N (batch-based) | 🐢 Slow |

**Cascade logic** (in `ExtractionAgent.run()`):

```
if not scanned:
    result = _try_extract_tables(file_path)      # Tier 1
    if not result:
        result = _try_extract_words(file_path)    # Tier 2
if not result:
    result = _extract_via_llm(batches)            # Tier 3
```

---

## 3. Bank Detection

**Function:** `_detect_bank(pages, file_path)`

Three-step cascade, ordered by reliability:

### Step 1: Vision Logo Detection (`_detect_bank_from_logo`)
- Crops the **top 20%** of page 1 (where the logo lives).
- Sends the cropped image to **GPT-4o Vision** with a prompt asking to identify the Singapore bank.
- Most reliable because many banks (e.g. DBS) only display their name in the logo image, not in extractable text.

### Step 2: Product Name Matching (`_detect_bank_from_text`)
- Scans the first 3 pages for **bank-specific product names** (highest specificity, no false positives).
- Example: `"AUTOSAVE ACCOUNT"` → DBS, `"GLOBAL SAVINGS ACCOUNT"` → HSBC.

### Step 3: Text Identifier Matching
- Falls back to generic bank identifiers with word-boundary matching for short names to avoid false positives.
- Example: `"DBS Bank"` → DBS, `"OCBC"` → OCBC.

---

## 4. Supported Banks & Identifiers

The system supports **18 Singapore banks** defined in the `BANK_IDENTIFIERS` dictionary:

| Bank | Identifiers | Product Names (examples) |
|------|-------------|-------------------------|
| **OCBC** | `OCBC`, `Oversea-Chinese Banking` | `360 Account`, `Frank Account` |
| **DBS** | `DBS Bank`, `DBS` | `Autosave Account`, `Multiplier Account`, `DBS BusinessCare` |
| **POSB** | `POSB` | `POSB Everyday Savings` |
| **UOB** | `United Overseas Bank`, `UOB` | `Stash Account`, `One Account`, `UOB BizAccount` |
| **Standard Chartered** | `Standard Chartered`, `StanChart` | `Bonus$aver`, `JumpStart Account`, `e$aver` |
| **HSBC** | `HSBC`, `Hongkong and Shanghai` | `Global Savings Account`, `Everyday Global Account` |
| **Citibank** | `Citibank`, `Citi` | `Citi Priority`, `Citigold` |
| **Maybank** | `Maybank`, `Malayan Banking` | `iSAVvy Savings`, `Maybank SaveUp` |
| **CIMB** | `CIMB Bank` | `FastSaver`, `StarSaver`, `CIMB BusinessGo` |
| **Bank of China** | `Bank of China`, `BOC` | `SmartSaver` |
| **ICBC** | `ICBC`, `Industrial and Commercial Bank` | |
| **GXS Bank** | `GXS Bank`, `GXS` | `GXS FlexiDeposit`, `GXS Savings` |
| **Trust Bank** | `Trust Bank`, `Trust` | `Trust Savings` |
| **MariBank** | `MariBank`, `Mari Bank` | `Mari Savings` |
| **Revolut** | `Revolut` | |
| **Wise** | `Wise`, `TransferWise` | |
| **Aspire** | `Aspire` | `Aspire Business Account` |
| **Airwallex** | `Airwallex` | `Airwallex Global Account` |

---

## 5. Tier 1 — Table-Based Extraction

**Function:** `_try_extract_tables(file_path)`

### How It Works

1. Opens the PDF with `pdfplumber` and iterates over all pages.
2. Calls `page.extract_tables()` to find bordered (gridded) tables.
3. For each table:
   - **Maps headers** to canonical column names using `_HEADER_ALIASES` (see [Section 9](#9-column-mapping--header-aliases)).
   - Detects **account info tables** (e.g. DBS puts `Account Number:`, `Opening Balance:` in a header table) and extracts structured account info via `_parse_account_info_table()`.
   - Parses each row as a transaction if it contains a date and amounts.
4. Detects **opening/closing balance** from description keywords.

### Which Banks Use This Path

- **DBS** — well-bordered tables with clear headers: `Date | Value Date | Transaction Details | Debit | Credit | Running Balance`.
- **Standard Chartered** — bordered tables with similar structure.
- Any other bank that produces PDFs with grid-line tables.

### Limitations

- Fails on **borderless** PDFs (OCBC, HSBC, Aspire) — `pdfplumber.extract_tables()` returns nothing or header-only tables.
- Multi-line descriptions within table cells are concatenated automatically by pdfplumber.

### Special Handling

- **Header-only tables** (e.g. Aspire) — detected when a table has headers but no data rows. The function returns `None`, triggering fallback to Tier 2.
- **DBS account info table** — the first table on page 1 often contains account metadata rather than transactions. Detected by checking if cells contain "Account Number" or "Opening Balance".

---

## 6. Tier 2 — Word-Position Extraction

**Function:** `_try_extract_words(file_path)`

This is the **workhorse** for most borderless bank statements. It works by treating the PDF as a grid of words positioned at (x, y) coordinates, then assigning each word to a column based on where it falls horizontally.

### Step-by-Step Process

#### 6.1 Auto-Discover Column Layout (`_discover_column_layout`)

1. Extracts all words from the page with their (x, y) coordinates via `page.extract_words()`.
2. Groups words into **y-position bands** (4pt tolerance).
3. For each row (and merged adjacent rows within 16pt — for multi-line headers like Aspire's `Balance\n(SGD)`):
   - Scores the row against `_COL_HEADER_ALIASES` (see [Section 9](#9-column-mapping--header-aliases)).
   - A valid header row must contain at least one amount column (`withdrawal` or `deposit`) AND a `balance` column.
4. Picks the **highest-scoring row** as the header.
5. Computes **column boundaries** using midpoints between adjacent headers.

Returns:
```python
{
    "header_y": 142,              # y-coordinate of header row
    "header_y_max": 158,          # bottom of (possibly multi-line) header
    "columns": {                  # discovered columns with x-extents
        "transaction_date": {"x0": 28, "x1": 65},
        "description": {"x0": 90, "x1": 280},
        "withdrawal": {"x0": 331, "x1": 364},
        "deposit": {"x0": 426, "x1": 449},
        "balance": {"x0": 500, "x1": 550},
    },
    "bounds": {                   # computed midpoint boundaries
        "transaction_date": (0, 77.5),
        "description": (77.5, 305.5),
        "withdrawal": (305.5, 393.0),
        "deposit": (393.0, 475.0),
        "balance": (475.0, 612),
    },
}
```

#### 6.2 Word Assignment (`_assign_words_to_columns`)

For each word on a transaction page, compute the x-midpoint and assign it to the column whose bounds contain it. Words falling outside all column boundaries (watermarks, margin text) are silently dropped.

#### 6.3 Transaction Assembly

For each page, process rows top-to-bottom:

1. **Transaction start** — a row with a valid date (matches `DD[sep]MMM` pattern) or a balance entry keyword → start a new transaction.
2. **Sub-transaction** (HSBC pattern) — if the current transaction already has a balance AND the new row has a different balance, flush the current transaction and start a new one inheriting the same date.
3. **Amount continuation** — row has amounts but no date → fill in missing withdrawal/deposit/balance on the current transaction.
4. **Description continuation** — row has text but no amounts/dates → append to the current transaction's description.

#### 6.4 Post-Processing

- **Reverse chronological detection** — some banks (Aspire) list newest transactions first. A quick chain-score comparison (forward vs. reversed) detects this and reverses the list.
- **Multi-account detection** — if transactions span multiple `account_section` values (set during currency section detection), each section is validated independently.

### Which Banks Use This Path

- **OCBC** — borderless columns: `Date | Description | Withdrawals | Deposits | Balance`
- **UOB** — borderless columns with similar layout
- **HSBC** — borderless, no-space concatenated headers, DR suffix for negative balances
- **Aspire** — borderless with multi-line headers (e.g. `Balance\n(SGD)`)
- **ANEXT** — multi-currency sections (SGD + USD)
- **Citibank**, **Maybank**, **CIMB** — when PDFs are borderless
- Essentially **any bank** whose PDF has visually-aligned text columns

---

## 7. Tier 3 — LLM Fallback

**Functions:** `_extract_transactions()`, `_batch_pages_with_overlap()`

Used when both Tier 1 and Tier 2 fail (typically scanned/image PDFs).

### Process

1. **Page filtering** — removes non-transaction pages (legend, T&C, blank pages) using `_is_skip_page()` and `_has_transactions()`.
2. **Bank-specific noise cleaning** — removes repeated headers/footers using `BANK_NOISE_PATTERNS[bank]`.
3. **Adaptive batching** — groups pages into batches for LLM processing:
   - Dense text (>1500 chars/page avg): **2 pages** per batch
   - Medium density (>1000 chars): **3 pages** per batch
   - Sparse text: up to **5 pages** per batch
4. **LLM extraction** — sends each batch to GPT-4o with the `TRANSACTION_EXTRACTION_PROMPT` which instructs the model to:
   - Normalise all dates to `DD MMM` format
   - Return amounts as plain numbers
   - Concatenate multi-line descriptions
   - Detect channels (FAST, GIRO, ATM, etc.)
   - Extract counterparty names

### For Scanned PDFs

- Detected via `is_scanned_pdf()` — checks if the PDF has very little extractable text.
- Uses `ocr_all_pages()` which sends each page image to **GPT-4o Vision** for OCR.
- The OCR'd text is then processed through the LLM batch pipeline.

---

## 8. Per-Bank Handling Details

### 8.1 DBS / POSB

| Aspect | Details |
|--------|---------|
| **Extraction tier** | Tier 1 (Table) — well-bordered PDF tables |
| **Date format** | `DD-MMM-YYYY` (e.g. `01-Sep-2025`) |
| **Columns** | Date, Value Date, Transaction Details, Debit, Credit, Running Balance |
| **Account info** | Structured header table: Account Number, Account Name, Product Type, Opening Balance, Ledger Balance |
| **Noise patterns** | `Page \d+ of \d+`, `DBS Bank Ltd`, `DBS BusinessCare`, `Deposit Insurance Scheme` |
| **Special handling** | Multi-line descriptions within table cells; `_parse_account_info_table()` extracts account number, currency, opening/closing balances from header table |
| **Product identifiers** | Autosave Account, Multiplier Account, My Account, DBS BusinessCare |

### 8.2 OCBC

| Aspect | Details |
|--------|---------|
| **Extraction tier** | Tier 2 (Word-position) — borderless PDF |
| **Date format** | `DD MMM` (e.g. `01 DEC`) — no year |
| **Columns** | Date, Description, Withdrawals, Deposits, Balance |
| **Noise patterns** | `OVERSEA-CHINESE BANKING`, `Page \d+ of \d+`, `ACCOUNT STATEMENT`, `Statement Date`, `Deposit Insurance Scheme` |
| **Special handling** | Bilingual headers (Chinese + English) — `_strip_non_ascii()` removes Chinese characters during column discovery |
| **Product identifiers** | 360 Account, Frank Account, OCBC Business Growth |

### 8.3 UOB

| Aspect | Details |
|--------|---------|
| **Extraction tier** | Tier 2 (Word-position) |
| **Date format** | `DD MMM` (e.g. `01 DEC`) |
| **Columns** | Date, Description/Particulars, Withdrawals, Deposits, Balance |
| **Noise patterns** | `United Overseas Bank`, `Page \d+ of \d+`, `Deposit Insurance Scheme` |
| **Product identifiers** | Stash Account, One Account, UOB BizAccount |

### 8.4 Standard Chartered (SCB)

| Aspect | Details |
|--------|---------|
| **Extraction tier** | Tier 1 (Table) — bordered tables |
| **Date format** | `DD MMM YYYY` or `DD/MM/YYYY` |
| **Columns** | Date, Description, Debit, Credit, Balance |
| **Noise patterns** | `Standard Chartered Bank`, `Page \d+ of \d+`, `Please examine`, `Deposit Insurance Scheme` |
| **Product identifiers** | Bonus$aver, JumpStart Account, e$aver, ExtraSaver |

### 8.5 HSBC

| Aspect | Details |
|--------|---------|
| **Extraction tier** | Tier 2 (Word-position) — borderless PDF with unique challenges |
| **Date format** | `DDMMMYYYY` — **no separator** (e.g. `30SEP2025`, `31OCT2025`) |
| **Columns** | Date, Details, Withdrawals, Deposits, Balance |
| **Special handling** | Multiple HSBC-specific fixes: |
| | • `DDMMMYYYY` date format support in `_normalise_date_to_dd_mmm()` |
| | • **DR suffix** for negative/debit balances (e.g. `1,234.56DR` → -1234.56) |
| | • **Sub-transactions** without dates (commissions, fees listed under a main transaction — detected when a row has amounts + balance but no date) |
| | • **Page summaries** (e.g. `WITHDRAWALS 305,465.02DR ASAT 31OCT2025`) — filtered via `hsbc_summary_re` |
| | • **Footer filtering** — Deposit Insurance disclaimers, `Issued by The Hongkong` boilerplate |
| | • **`past_closing` flag** — after `BALANCE CARRIED FORWARD`, all rows are skipped until the next `BALANCE BROUGHT FORWARD` (prevents footer/summary contamination) |
| | • **No-space concatenated text** — HSBC PDFs concatenate words without spaces (e.g. `BALANCEBROUGHTFORWARD`, `BALANCECARRIEDFORWARD`) — matched via regex without `\s*` |
| **Noise patterns** | `HSBC`, `Hongkong and Shanghai`, `Page \d+ of \d+`, `Issued by` |
| **Product identifiers** | Global Savings Account, Everyday Global Account |

### 8.6 Aspire

| Aspect | Details |
|--------|---------|
| **Extraction tier** | Tier 2 (Word-position) — borderless, header-only tables in Tier 1 |
| **Date format** | `DD MMM YYYY` (e.g. `01 Dec 2025`) |
| **Columns** | Date, Description, Withdrawal, Deposit, Balance (SGD) |
| **Special handling** | • Multi-line headers: `Balance\n(SGD)` — `_discover_column_layout()` merges adjacent rows within 16pt for header detection |
| | • Uses `'-'` for zero amounts — treated as empty |
| | • **Reverse chronological** — newest transactions listed first; auto-detected and reversed via `_quick_chain_score()` |
| | • Header-only tables trigger fallback from Tier 1 to Tier 2 |
| **Product identifiers** | Aspire Business Account |

### 8.7 ANEXT (Ant International)

| Aspect | Details |
|--------|---------|
| **Extraction tier** | Tier 2 (Word-position) |
| **Date format** | `DD MMM YYYY` |
| **Special handling** | • **Multi-currency**: SGD + USD (or more) sections in a single PDF |
| | • Currency section boundaries detected by standalone ISO currency code lines (e.g. a row containing just `"USD"`) |
| | • Each section gets a unique `account_section` tag for independent balance chain validation |
| | • `Balance Brought Forward` / `Balance Carried Forward` mark section boundaries |

### 8.8 Citibank

| Aspect | Details |
|--------|---------|
| **Extraction tier** | Tier 2 (Word-position) or Tier 3 (LLM) depending on PDF structure |
| **Product identifiers** | Citi Priority, Citigold |

### 8.9 Maybank

| Aspect | Details |
|--------|---------|
| **Extraction tier** | Tier 2 (Word-position) |
| **Product identifiers** | iSAVvy Savings, Maybank SaveUp |

### 8.10 Fintech / Digital Banks

**GXS Bank**, **Trust Bank**, **MariBank**, **Revolut**, **Wise**, **Airwallex** — all supported via Tier 2 (word-position) or Tier 3 (LLM) fallback. These typically produce clean, modern PDF formats that work well with generic column discovery.

---

## 9. Column Mapping & Header Aliases

Two alias dictionaries map raw PDF column headers to canonical names:

### Table-Based Extraction (`_HEADER_ALIASES`)

Used by `_try_extract_tables()` → `_normalise_header()`:

| Canonical Name | Raw Aliases |
|----------------|-------------|
| `transaction_date` | `date`, `txn date`, `trans date`, `transaction date`, `posting date`, `value date` |
| `value_date` | `value date`, `posting date`, `effective date` |
| `description` | `description`, `particulars`, `details`, `narrative`, `remarks`, `transaction details` |
| `debit` | `debit`, `withdrawal`, `withdrawals`, `dr`, `debit amount`, `payments` |
| `credit` | `credit`, `deposit`, `deposits`, `cr`, `credit amount`, `receipts` |
| `balance` | `balance`, `running balance`, `closing balance`, `available balance`, `ledger balance` |
| `cheque` | `cheque`, `chq`, `cheque no` |
| `reference` | `reference`, `ref`, `ref no` |

### Word-Position Extraction (`_COL_HEADER_ALIASES`)

Used by `_discover_column_layout()`:

| Canonical Name | Raw Aliases |
|----------------|-------------|
| `transaction_date` | `transaction date`, `txn date`, `trans date`, `date`, `date & time`, `date and time`, `transaction`, `trans` |
| `value_date` | `value date`, `posting date`, `effective date` |
| `description` | `description`, `particulars`, `details`, `narrative`, `remarks`, `transaction details` |
| `counterparty` | `counterparty`, `payee`, `beneficiary`, `sender` |
| `cheque` | `cheque`, `chq`, `check`, `cheque no` |
| `reference` | `reference`, `ref`, `ref no`, `reference no` |
| `withdrawal` | `withdrawal`, `withdrawals`, `debit`, `debits`, `debit amount`, `withdrawal amount`, `payments` |
| `deposit` | `deposit`, `deposits`, `credit`, `credits`, `credit amount`, `deposit amount`, `receipts` |
| `balance` | `balance`, `running balance`, `closing balance`, `available balance`, `ledger balance` |

---

## 10. Date Normalisation

**Function:** `_normalise_date_to_dd_mmm(raw_date: str) -> str`

All transaction dates are normalised to **`DD MMM`** format (e.g. `01 DEC`, `30 SEP`).

| Input Format | Example | Bank(s) | Regex Pattern |
|-------------|---------|---------|---------------|
| `DD-MMM-YYYY` | `01-Sep-2025` | DBS | `(\d{1,2})-(Jan\|Feb\|...)-(\d{4})` |
| `DD MMM YYYY` | `01 DEC 2025` | OCBC, Aspire, ANEXT | `(\d{1,2})\s+(JAN\|FEB\|...)\s+\d{4}` |
| `DD/MM/YYYY` | `01/12/2025` | Various | `(\d{1,2})/(\d{1,2})/(\d{2,4})` |
| `DDMMMYYYY` | `30SEP2025` | **HSBC** (no separator) | `(\d{2})(JAN\|FEB\|...)(\d{4})` |
| `DD MMM` | `01 DEC` | OCBC/UOB (no year) | Already normalised — returned as-is |

---

## 11. Amount Parsing

### Table Path (`_parse_amount`)

- Strips commas: `1,234.56` → `1234.56`
- Handles parentheses as negatives: `(500.00)` → `-500.00`
- Returns `float` or `None`

### Word-Position Path (`_extract_amount`)

- Strips spaces from concatenated text
- Regex: `([\d,]+\.\d{2})\s*(DR)?`
- **DR suffix** (HSBC convention): `1,234.56DR` → `-1234.56` (only when `allow_dr=True`, used for balance column)
- Dash `'-'` treated as zero/empty (Aspire convention)

---

## 12. Multi-Currency / Multi-Account PDFs

**Primary use case:** ANEXT statements with SGD + USD sections.

### Detection

1. **Above-header currency codes** — standalone ISO currency codes (e.g. `SGD`, `USD`) appearing above the data area on a page.
2. **Mid-page currency codes** — a row in the data area containing only an ISO currency code.
3. **Balance Brought Forward** boundaries — each `BALANCE BROUGHT FORWARD` after a `BALANCE CARRIED FORWARD` marks a new section.

### Handling

- Each section is assigned an `account_section` integer (0, 1, 2, ...).
- Each section is tagged with its `currency` (e.g. `SGD`, `USD`).
- **Balance chain validation** runs independently per section.
- **Metrics** include a `currency_breakdown` dict when multiple currencies are detected.

### Supported Currency Codes

SGD, USD, EUR, GBP, CNY, JPY, AUD, HKD, MYR, IDR, THB, PHP, INR, KRW, NZD, CHF, CAD, TWD, VND.

---

## 13. Balance Chain Validation

**Function:** `_validate_balance_chain(transactions)`

Verifies that running balances form a mathematically consistent chain.

### Algorithm

For each consecutive pair of **credit/debit** transactions within the same section:

$$
\text{expected\_balance}_i =
\begin{cases}
\text{balance}_{i-1} - \text{amount}_i & \text{if debit} \\
\text{balance}_{i-1} + \text{amount}_i & \text{if credit}
\end{cases}
$$

A transition is **valid** if:

$$
|\text{expected\_balance}_i - \text{actual\_balance}_i| \leq 0.02
$$

(2-cent tolerance for floating-point rounding.)

### Multi-Section Support

If transactions carry `account_section` tags, the chain is validated **per section**. Otherwise, section boundaries are inferred from `opening_balance` transaction types.

### Output

```python
{
    "total_checked": 89,        # pairs checked
    "valid": 89,                # valid transitions
    "invalid": 0,               # broken transitions
    "chain_accuracy_pct": 100.0,
    "breaks": [],               # up to 20 break details
    "sections": 1,              # independent sections found
}
```

---

## 14. Accuracy Scoring

**Function:** `_compute_accuracy_score(transactions, metrics, balance_chain)`

Computes an overall score (0–100) from five weighted signals:

| Signal | Weight | What It Measures |
|--------|--------|-----------------|
| **Balance chain continuity** | 40% | `chain_accuracy_pct` from validation |
| **Opening/closing balance present** | 20% | Both present = 100, one = 50, none = 0 |
| **Accounting equation** | 20% | $\text{opening} + \Sigma\text{credits} - \Sigma\text{debits} \approx \text{closing}$ |
| **Completeness** | 10% | % of transactions with amounts (each 1% missing = -5 pts) |
| **Balance completeness** | 10% | % of transactions with balances (each 1% null = -5 pts) |

### Grading Scale

| Score Range | Grade |
|-------------|-------|
| ≥ 95 | A+ |
| ≥ 90 | A |
| ≥ 80 | B |
| ≥ 70 | C |
| ≥ 50 | D |
| < 50 | F |

### Special Rule

If `chain_accuracy_pct ≥ 99.9%`, the accounting equation score is automatically set to 100% (the chain validation is the strongest proof of correctness).

---

## 15. Transaction Enrichment

Each extracted transaction is enriched with:

### Channel Detection (`_detect_channel`)

| Pattern in Description | Channel |
|-----------------------|---------|
| `FAST`, `FAST PAYMENT` | `FAST` |
| `GIRO`, `IBG`, `INTERBANK GIRO` | `GIRO` / `IBG` |
| `REMITTANCE`, `TELEGRAPHIC` | `REMITTANCE` |
| `ATM` | `ATM` |
| `DEBIT PURCHASE`, `DEBIT PURC`, `VISA` | `DEBIT PURCHASE` |
| `CHEQUE`, `CHQ` | `CHEQUE` |
| `NETS`, `NETS QR` | `NETS` |
| `PAYNOW` | `PayNow` |
| `TRANSFER`, `TRF` | `PAYMENT/TRANSFER` |

### Counterparty Extraction (`_extract_counterparty`)

1. Strips out reference patterns (alphanumeric codes like `SG3P251128972769`).
2. Strips out known channel keywords.
3. Returns the remaining text as the counterparty (typically a company or person name).

### Transaction Categorisation (`_categorize_transaction`)

15 categories based on keyword matching in description:

`salary_payroll`, `rent`, `utilities`, `food_beverage`, `transport`, `supplier_payment`, `revenue`, `loan`, `tax_government`, `insurance`, `fees_charges`, `transfer`, `purchase`, `other`

### Cash & Cheque Flags

- `is_cash` — ATM, CASH DEPOSIT, CDM, etc.
- `is_cheque` — CHEQUE, CHQ, etc.

---

## 16. Noise Filtering & Page Skipping

### Page-Level Skip Patterns (`SKIP_PATTERNS`)

Pages are skipped if they contain dominant text matching:
- `TRANSACTION CODE DESCRIPTION` (legend pages)
- `IMPORTANT INFORMATION` / `TERMS AND CONDITIONS`
- `Interest Rate` (rate schedule pages)

A page is only skipped if the skip pattern occupies >40% of the page content AND the page lacks monetary amounts and date patterns.

### Bank-Specific Noise (`BANK_NOISE_PATTERNS`)

Per-bank regex patterns that are stripped from page text before LLM processing:

| Bank | Noise Removed |
|------|--------------|
| OCBC | `OVERSEA-CHINESE BANKING...`, page numbers, `ACCOUNT STATEMENT`, `Statement Date`, `Deposit Insurance Scheme` |
| DBS | `DBS Bank Ltd`, page numbers, `Deposit Insurance Scheme`, `DBS BusinessCare` |
| UOB | `United Overseas Bank`, page numbers, `Deposit Insurance Scheme` |
| SCB | `Standard Chartered Bank`, page numbers, `Please examine...`, `Deposit Insurance Scheme` |
| HSBC | `HSBC`, `Hongkong and Shanghai`, page numbers, `Issued by` |
| _default | Generic page numbers, `Deposit Insurance Scheme`, `Terms and Conditions` |

### Word-Position Extraction Filters

- **Summary rows** — `Total Withdrawal`, `Total Deposit`, `Grand Total`, `END OF STATEMENT`, etc.
- **Footer rows** — Deposit Insurance disclaimers, `Issued by The Hongkong`, etc.
- **HSBC page summaries** — `WITHDRAWALS 305,465.02DR ASAT 31OCT2025` — detected via `hsbc_summary_re`.
- **Currency sub-labels** — standalone `(SGD)` rows from multi-line headers.
- **Past-closing rows** — after `BALANCE CARRIED FORWARD`, all rows are skipped until `BALANCE BROUGHT FORWARD`.

---

## 17. Deduplication

**Function:** `_deduplicate_transactions(transactions)`

Two-pass deduplication for LLM-extracted transactions (where overlapping batches may produce duplicates):

### Pass 1: Exact Fingerprint

Key = `{date}|{desc[:60]}|{amount:.2f}|{balance:.2f}|{type}`

Removes exact duplicates.

### Pass 2: Balance-Based Fuzzy

Key = `{date}|{balance:.2f}|{type}|{amount:.2f}`

Catches near-duplicates from overlapping page batches where descriptions may differ slightly.

> **Note:** Tiers 1 and 2 generally don't produce duplicates since they process each page exactly once. Deduplication primarily benefits Tier 3 (LLM) extractions.

---

## 18. Adding Support for a New Bank

To add support for a new Singapore bank:

### Step 1: Add Bank Identifiers

In `BANK_IDENTIFIERS`, add a new entry:

```python
"New Bank": ["New Bank", "NB"],  # text identifiers
```

### Step 2: Add Product Identifiers (optional but recommended)

In `BANK_PRODUCT_IDENTIFIERS`:

```python
"New Bank": ["New Bank SuperSaver", "New Bank BizAccount"],
```

### Step 3: Add Noise Patterns

In `BANK_NOISE_PATTERNS`:

```python
"New Bank": [
    r'New Bank Ltd\.?.*$',
    r'Page\s+\d+\s+of\s+\d+',
    # ... other headers/footers specific to this bank
],
```

### Step 4: Test with a Sample Statement

1. Upload a PDF from the new bank.
2. Check logs for which tier was used (`table`, `words`, or `llm`).
3. Verify balance chain accuracy (target: 100%).
4. If Tier 2 doesn't discover headers, check if the bank uses unusual column names → add them to `_COL_HEADER_ALIASES`.

### Step 5: Handle Special Formats (if needed)

If the new bank has unique formatting:

- **New date format** — add a pattern to `_normalise_date_to_dd_mmm()`.
- **Special amount notation** — update `_extract_amount()` or `_parse_amount()`.
- **Unusual column headers** — add aliases to `_HEADER_ALIASES` and `_COL_HEADER_ALIASES`.
- **Summary/footer contamination** — add patterns to `summary_re`, `footer_re`, or `hsbc_summary_re`.

### Step 6: Verify & Commit

Run the extraction and confirm:
- ✅ Balance chain accuracy = 100%
- ✅ All transactions captured (compare with manual count)
- ✅ Opening/closing balances detected
- ✅ Extraction method = `table` or `words` (not `llm` unless scanned)

---

## Appendix: Key Function Reference

| Function | Location | Purpose |
|----------|----------|---------|
| `ExtractionAgent.run()` | L2010 | Main orchestration — runs the full pipeline |
| `_try_extract_tables()` | L340 | Tier 1: bordered table extraction |
| `_try_extract_words()` | L820 | Tier 2: word-position extraction |
| `_discover_column_layout()` | L550 | Auto-discovers column layout from header row |
| `_assign_words_to_columns()` | L710 | Assigns words to columns by x-position |
| `_detect_bank()` | L1470 | Bank detection (vision + text) |
| `_detect_bank_from_logo()` | L1390 | Vision-based bank logo detection |
| `_detect_bank_from_text()` | L1430 | Text-based bank detection fallback |
| `_validate_balance_chain()` | L1635 | Multi-section balance chain validation |
| `_compute_accuracy_score()` | L1730 | Weighted accuracy scoring |
| `_compute_metrics()` | L1900 | Compute 25+ financial KPIs |
| `_normalise_date_to_dd_mmm()` | L240 | Date format normalisation |
| `_parse_amount()` | L225 | Amount parsing (table path) |
| `_extract_counterparty()` | L290 | Counterparty name extraction |
| `_detect_channel()` | L270 | Transaction channel detection |
| `_categorize_transaction()` | L1840 | Transaction categorisation (15 categories) |
| `_deduplicate_transactions()` | L1580 | Two-pass deduplication |
| `_clean_page_text()` | L1500 | Bank-specific noise removal |
| `_batch_pages_with_overlap()` | L1510 | Adaptive page batching for LLM |
| `_parse_account_info_table()` | L1300 | DBS-style account info table parsing |
| `_extract_account_info_from_text()` | L750 | Generic regex-based account info extraction |
| `_is_skip_page()` | L1360 | Page skip heuristic |
| `_has_transactions()` | L1385 | Transaction page detection |
| `_is_transaction_page()` | L730 | Word-position transaction page check |
