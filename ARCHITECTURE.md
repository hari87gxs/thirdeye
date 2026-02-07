# ThirdEye AI — System Architecture

> Detailed technical architecture of the ThirdEye multi-agent financial document analysis platform.

---

## Table of Contents

- [High-Level Overview](#high-level-overview)
- [System Architecture Diagram](#system-architecture-diagram)
- [Request Lifecycle](#request-lifecycle)
- [Backend Architecture](#backend-architecture)
  - [Application Layer](#application-layer)
  - [Database Layer](#database-layer)
  - [Agent Pipeline](#agent-pipeline)
  - [Services Layer](#services-layer)
- [Agent Deep Dives](#agent-deep-dives)
  - [Extraction Agent](#1-extraction-agent)
  - [Insights Agent](#2-insights-agent)
  - [Tampering Agent](#3-tampering-agent)
  - [Fraud Agent](#4-fraud-agent)
- [Frontend Architecture](#frontend-architecture)
- [Data Flow Diagrams](#data-flow-diagrams)
- [LLM Usage Map](#llm-usage-map)
- [Security & Design Decisions](#security--design-decisions)

---

## High-Level Overview

ThirdEye follows a **client-server architecture** with a clear separation of concerns:

```
┌──────────────────────────────────────────────────────────────────┐
│                        BROWSER (Client)                          │
│  Next.js 13 App Router · React 18 · TypeScript · Tailwind CSS   │
│  Recharts · Radix UI · Lucide Icons                              │
└───────────────────────────┬──────────────────────────────────────┘
                            │ REST API (JSON)
                            │ http://localhost:3000 → :8000/api
┌───────────────────────────┴──────────────────────────────────────┐
│                      FASTAPI SERVER (:8000)                       │
│                                                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────────┐ │
│  │  Documents   │  │  Analysis   │  │     Orchestrator         │ │
│  │   Router     │  │   Router    │  │  (Background Tasks)      │ │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬──────────────┘ │
│         │                │                      │                 │
│  ┌──────┴────────────────┴──────────────────────┴──────────────┐ │
│  │                    Agent Pipeline (Sequential)               │ │
│  │  ┌────────────┐ ┌──────────┐ ┌───────────┐ ┌─────────────┐ │ │
│  │  │ Extraction │→│Tampering │→│   Fraud   │→│  Insights   │ │ │
│  │  │   Agent    │ │  Agent   │ │   Agent   │ │   Agent     │ │ │
│  │  └─────┬──────┘ └────┬─────┘ └─────┬─────┘ └──────┬──────┘ │ │
│  └────────┼──────────────┼─────────────┼──────────────┼────────┘ │
│           │              │             │              │           │
│  ┌────────┴──────────────┴─────────────┴──────────────┴────────┐ │
│  │                     Services Layer                           │ │
│  │  ┌──────────────────┐  ┌──────────────────────────────────┐ │ │
│  │  │   LLM Client     │  │       PDF Processor              │ │ │
│  │  │ (Azure OpenAI)   │  │ (PyMuPDF · pdfplumber · OpenCV)  │ │ │
│  │  └──────────────────┘  └──────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              SQLite Database (SQLAlchemy ORM)                │ │
│  │  documents · raw_transactions · statement_metrics            │ │
│  │  aggregated_metrics · agent_results                          │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                            │
                    ┌───────┴────────┐
                    │  Azure OpenAI  │
                    │   GPT-4o       │
                    │ (Chat + Vision)│
                    └────────────────┘
```

---

## Request Lifecycle

### 1. Document Upload Flow

```
User drops PDF → FileUploadZone → POST /api/upload (multipart)
  → Backend validates (.pdf, <50MB)
  → Saves file to /uploads/{uuid}.pdf
  → Creates Document record (status: "uploaded")
  → Extracts page count via PyMuPDF
  → Returns document metadata
  → Frontend auto-triggers POST /api/documents/{id}/analyze
```

### 2. Analysis Flow

```
POST /api/documents/{id}/analyze
  → Creates 4 AgentResult placeholders (status: "pending")
  → Sets document status → "processing"
  → Spawns BackgroundTask → orchestrator.run_analysis()
  → Returns 202 immediately

Orchestrator (background):
  → Extraction Agent → stores results + raw transactions + metrics
  → Tampering Agent → stores check results + risk score
  → Fraud Agent → stores check results + flagged transactions
  → Insights Agent → stores analytics + narrative
  → Sets document status → "completed"
```

### 3. Results Polling Flow

```
Frontend polls GET /api/documents (every 3 seconds)
  → Detects status change: "processing" → "completed"
  → User clicks "View Results"
  → GET /api/documents/{id}/results → all 4 agent results
  → Renders detail pages with charts, tables, and narratives
```

---

## Backend Architecture

### Application Layer

**Entry Point (`main.py`):**
- FastAPI application with CORS middleware
- Two routers mounted under `/api` prefix
- Database table creation on startup
- Health check endpoint at `/health`

**Routers:**

| Router | Prefix | Endpoints |
|--------|--------|-----------|
| `documents.py` | `/api` | `POST /upload`, `GET /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`, `GET /upload-groups` |
| `analysis.py` | `/api` | `POST /documents/{id}/analyze`, `POST /upload-groups/{id}/analyze`, `GET /documents/{id}/results`, `GET /documents/{id}/results/{agent_type}`, `GET /upload-groups/{id}/results`, `GET /documents/{id}/transactions`, `GET /documents/{id}/metrics`, `GET /documents/{id}/full-metrics` |

### Database Layer

**Engine:** SQLAlchemy 2.0 with SQLite (`check_same_thread=False` for async compatibility)

**5 Tables:**

```
┌──────────────────┐     ┌────────────────────┐
│    documents      │────<│  raw_transactions  │
│                   │     └────────────────────┘
│  id (PK, UUID)    │
│  filename         │     ┌────────────────────┐
│  original_filename│────<│  statement_metrics  │
│  file_path        │     └────────────────────┘
│  file_size        │
│  page_count       │     ┌────────────────────┐
│  status           │────<│   agent_results    │
│  upload_group_id  │     └────────────────────┘
│  created_at       │
│  updated_at       │     ┌────────────────────┐
└──────────────────┘     │ aggregated_metrics  │
                          │  (1:1 per document) │
                          └────────────────────┘
```

**Key Design Decisions:**
- **UUIDs as primary keys** — no auto-increment, safe for distributed deployment later
- **JSON columns for agent results** — flexible schema per agent, avoids rigid column definitions
- **Cascade delete-orphan** — deleting a document removes all associated data
- **Upload groups** — multiple PDFs uploaded together share a `upload_group_id` for batch analysis

**Enums:**
- `DocumentStatus`: `uploaded` → `processing` → `completed` | `failed`
- `AgentType`: `extraction`, `insights`, `tampering`, `fraud`
- `AgentStatus`: `pending` → `running` → `completed` | `failed`

### Agent Pipeline

The orchestrator runs all 4 agents **sequentially** in a FastAPI `BackgroundTask`:

```
Extraction ──→ Tampering ──→ Fraud ──→ Insights
    │                                      │
    └──── Stores raw_transactions ─────────┘
           & statement_metrics        (reads them)
```

**Why sequential, not parallel?**
1. **Insights agent depends on extraction data** — needs `raw_transactions` and `statement_metrics` to compute analytics
2. **Resource management** — GPT-4o vision calls are expensive; sequential prevents rate limiting
3. **Failure isolation** — if extraction fails, other agents still attempt to run with available data

**Pipeline behavior:**
- Each agent is wrapped in try/catch — one agent failing doesn't stop others
- Agent status transitions: `pending` → `running` → `completed` | `failed`
- Document marked `completed` only after all agents finish (regardless of individual failures)

### Services Layer

**LLM Client (`llm_client.py`):**
- Singleton Azure OpenAI client
- Two methods: `chat(messages)` → text, `analyze_image(base64, prompt)` → text
- Separate deployment names for chat vs. vision (both default to `gpt-4o`)

**PDF Processor (`pdf_processor.py`):**
- `get_page_count()` — PyMuPDF page count
- `extract_text()` — full text extraction per page
- `extract_tables()` — pdfplumber table extraction
- `get_metadata()` — PDF metadata dictionary
- `page_to_image()` / `all_pages_to_images()` — page rendering at configurable DPI
- `is_scanned_pdf()` — detects scanned PDFs (<20 chars per page)
- `ocr_page()` — GPT-4o Vision OCR for scanned pages

---

## Agent Deep Dives

### 1. Extraction Agent

**The most complex component (2300+ lines).** Responsible for converting raw PDF bank statements into structured transaction data.

#### Three-Tier Extraction Strategy

The agent tries extraction methods in order of accuracy, falling back to the next if the previous produces no results:

```
┌─────────────────────────────────────────────────────────┐
│  Tier 1: Table-Based Extraction                         │
│  ─────────────────────────────                          │
│  For: PDFs with bordered tables (DBS, Standard Chartered│
│  How:  pdfplumber.extract_tables() → parse rows         │
│  LLM:  ZERO calls for transactions                      │
│  Speed: Fastest                                         │
│  Accuracy: Highest (direct cell extraction)             │
└────────────────────┬────────────────────────────────────┘
                     │ Falls back if no tables found
┌────────────────────┴────────────────────────────────────┐
│  Tier 2: Word-Position Extraction                       │
│  ────────────────────────────                           │
│  For: Borderless PDFs (OCBC, Aspire, ANEXT, Airwallex)  │
│  How:  Auto-discover column layout from header row,     │
│        assign words to columns by x-coordinate          │
│  LLM:  ZERO calls for transactions                      │
│  Speed: Fast                                            │
│  Accuracy: High (structure-aware)                       │
└────────────────────┬────────────────────────────────────┘
                     │ Falls back if <3 transactions extracted
┌────────────────────┴────────────────────────────────────┐
│  Tier 3: LLM Text Parsing                              │
│  ─────────────────────                                  │
│  For: Unusual formats, messy layouts                    │
│  How:  Chunk text → send to GPT-4o for JSON extraction  │
│  LLM:  Multiple calls (1 per text chunk)                │
│  Speed: Slowest                                         │
│  Accuracy: Good but variable                            │
│                                                         │
│  Sub-variant: OCR + LLM                                 │
│  For: Scanned/image PDFs                                │
│  How:  GPT-4o Vision OCR each page → then LLM parsing   │
└─────────────────────────────────────────────────────────┘
```

#### Bank Detection Pipeline

```
Step 1: Vision — Crop top 20% of page 1, send to GPT-4o: "What bank issued this?"
Step 2: Product names — Match known products (e.g., "AUTOSAVE" → DBS)
Step 3: Text identifiers — Search for bank names in text
```

#### Post-Processing Pipeline

After raw extraction, every transaction passes through:

```
Raw Transactions
  │
  ├─→ Deduplication (fingerprint + balance-based fuzzy)
  ├─→ Reverse-chronological detection (try both directions)
  ├─→ Balance chain validation (per currency section)
  ├─→ Auto-categorization (15 categories via keyword matching)
  ├─→ Cash/cheque detection from descriptions
  ├─→ Channel identification (FAST, GIRO, ATM, PayNow, etc.)
  ├─→ Counterparty extraction from descriptions
  │
  ├─→ Store to raw_transactions table
  ├─→ Compute statement_metrics (25+ fields)
  └─→ Update aggregated_metrics for upload group
```

#### Accuracy Scoring Algorithm

The extraction accuracy score (0–100) is a weighted composite:

| Component | Weight | What It Measures |
|-----------|:------:|------------------|
| Balance chain continuity | 40% | Do running balances form an unbroken chain? |
| Opening/closing balance found | 20% | Were B/F and C/F balances detected? |
| Accounting equation check | 20% | Does opening + credits − debits = closing? |
| Missing amount ratio | 10% | How many transactions have null amounts? |
| Null balance ratio | 10% | How many transactions have null running balances? |

**Grades:** A+ (≥95) · A (≥90) · B (≥80) · C (≥70) · D (≥50) · F (<50)

#### Multi-Currency Support

For statements with multiple currency sections (common in ANEXT/Airwallex):
- Detects currency section headers (e.g., "SGD", "USD")
- Validates balance chains **independently per section**
- Tags each transaction with its currency

---

### 2. Insights Agent

Generates business intelligence from the extracted transaction data. **7 analytical modules + 1 LLM narrative:**

```
┌─────────────────────────────────────────────────────────┐
│                    INSIGHTS AGENT                        │
│                                                         │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐ │
│  │  Category     │  │  Cash Flow  │  │ Counterparty  │ │
│  │  Analysis     │  │  Analysis   │  │  Analysis     │ │
│  │              │  │             │  │               │ │
│  │ 15 categories │  │ Daily/weekly│  │ Top 15 each   │ │
│  │ debit/credit  │  │ inflow/out  │  │ Recurring     │ │
│  │ percentages   │  │ burn rate   │  │ vendor detect │ │
│  └──────────────┘  └─────────────┘  └───────────────┘ │
│                                                         │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐ │
│  │  Unusual      │  │ Day-of-Month│  │   Channel     │ │
│  │  Transactions │  │  Patterns   │  │   Analysis    │ │
│  │              │  │             │  │               │ │
│  │ Large (>3x)   │  │ Busiest day │  │ FAST/GIRO/ATM│ │
│  │ Round numbers │  │ Quietest day│  │ PayNow/NETS   │ │
│  │ Same-day mvmt │  │ Peak value  │  │ Percentages   │ │
│  │ Low balance   │  │             │  │               │ │
│  └──────────────┘  └─────────────┘  └───────────────┘ │
│                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │           Business Health Score (0–100)             │ │
│  │                                                    │ │
│  │  Cash runway months · Revenue coverage ratio       │ │
│  │  Balance trend · Cash deposit ratio · Fee burden   │ │
│  │  Transaction velocity · Min balance cover days     │ │
│  └────────────────────────────────────────────────────┘ │
│                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │           LLM Narrative Generation                  │ │
│  │  GPT-4o generates structured report:                │ │
│  │  • Executive Summary                                │ │
│  │  • Spending Analysis                                │ │
│  │  • Income Analysis                                  │ │
│  │  • Cash Flow Assessment                             │ │
│  │  • Risk Observations                                │ │
│  │  • Recommendations                                  │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Risk Assessment:**
- `low`: health score ≥70 AND unusual flags <5
- `medium`: health score ≥50 AND flags <15
- `high`: health score ≥30
- `critical`: health score <30

---

### 3. Tampering Agent

Runs **8 independent integrity checks** on the PDF file itself (not the transaction data):

| # | Check | Method | Pass | Fail |
|---|-------|--------|------|------|
| 1 | **Metadata Date Check** | Compare creation vs. modification timestamps | Modification within 60s of creation | Mod >60s after, or mod before creation |
| 2 | **Metadata Creator/Producer** | Check for editing tool signatures | Standard bank software | Canva, ilovepdf, Smallpdf, Sejda, Foxit, Nitro, LibreOffice, Chrome, etc. |
| 3 | **Metadata Keywords** | Scan for suspicious keyword patterns | Clean metadata | Long hex strings or tracking identifiers |
| 4 | **Font Consistency** | Extract all fonts, check page-to-page variation | Consistent fonts | Known editing fonts detected, or >3 font differences between pages |
| 5 | **Page Dimensions** | Render at 300 DPI, check minimum size | All pages ≥1000×800px | Undersized pages (possible splicing) |
| 6 | **Page Clarity** | Laplacian variance per page (OpenCV) | Sharpness variance ≥500 | Low clarity (possible image manipulation) |
| 7 | **Sharpness Spread** | Cross-page sharpness consistency | All pages within normal range | Min <50% of max OR std dev >100 |
| 8 | **Visual Tampering (LLM)** | GPT-4o Vision on first page | No visual inconsistencies detected | Font irregularities, alignment issues, pasted content, editing artifacts |

**Risk Scoring:** Each `fail` = 3 points, `warning` = 1 point
- `critical`: ≥4 fails
- `high`: ≥2 fails
- `medium`: ≥1 fail OR ≥3 warnings
- `low`: all other cases

---

### 4. Fraud Agent

Runs **8 fraud detection checks** (7 statistical/rule-based + 1 LLM-powered):

| # | Check | Detection Logic | Thresholds |
|---|-------|-----------------|------------|
| 1 | **Round-Amount Transactions** | Amounts divisible by $1,000 and ≥$5,000 | ≥5 found → fail |
| 2 | **Duplicate/Near-Duplicate** | Same date + amount + counterparty | ≥6 duplicates → fail |
| 3 | **Rapid Succession** | ≥10 transactions in a single day | Any day with 10+ → warning |
| 4 | **Large Outlier Transactions** | Amount > mean + 3σ (standard deviations) | ≥3 outliers → fail |
| 5 | **Balance Anomalies** | Swing >50% of max balance AND >$10,000 | ≥3 swings → fail |
| 6 | **Cash-Heavy Activity** | Cash transactions as % of total volume | >30% → warning; >50% → fail |
| 7 | **Unusual Timing Patterns** | Transactions concentrated at month edges (days 1-3, 28-31) | >60% at edges → warning |
| 8 | **Counterparty Risk (LLM)** | GPT-4o analyzes top 30 counterparties for: shell companies, money service businesses, gambling entities, personal accounts in business context | LLM flags → fail |

---

## Frontend Architecture

### Technology Stack
- **Framework:** Next.js 13.5 with App Router (server + client components)
- **Styling:** Tailwind CSS with dark theme
- **Charts:** Recharts (responsive, composable)
- **UI Primitives:** Radix UI (Dialog, Dropdown, Progress, Tabs, Tooltip)
- **Icons:** Lucide React

### Page Structure

```
/                              → HomePage (upload + document list)
/documents/[id]                → DocumentOverview (4 agent cards with scores)
/documents/[id]/extraction     → ExtractionPage (accuracy, transactions, balance chart)
/documents/[id]/insights       → InsightsPage (cash flow, categories, health, narrative)
/documents/[id]/tampering      → TamperingPage (8 check results, risk score)
/documents/[id]/fraud          → FraudPage (8 check results, flagged transactions)
```

### Data Flow

```
Component mounts
  → useEffect calls API function (e.g., getDocumentResults)
  → API function fetches from backend REST endpoint
  → Response parsed as TypeScript interfaces
  → Data normalized (handles multiple backend response shapes)
  → Rendered with Recharts charts + Tailwind-styled cards
```

### Key Design Patterns

1. **Data Normalization Layer** — Each detail page normalizes API responses to handle multiple backend data shapes (backward compatibility with format changes)
2. **Polling Pattern** — Home page polls `GET /documents` every 3 seconds to detect analysis completion
3. **Auto-Analysis** — Upload automatically triggers analysis, no manual "Analyze" step needed
4. **Responsive Layout** — Full-width with `max-w-6xl` centered content, top navbar

---

## LLM Usage Map

ThirdEye uses Azure OpenAI GPT-4o at **7 specific points** across the pipeline:

| # | Agent | Mode | Purpose | When Used |
|---|-------|------|---------|-----------|
| 1 | Extraction | 🖼️ Vision | Bank logo identification | Always (page 1 crop) |
| 2 | Extraction | 💬 Chat | Account info extraction | Always |
| 3 | Extraction | 💬 Chat | Transaction parsing | Only for Tier 3 (LLM path) |
| 4 | Extraction | 🖼️ Vision | OCR for scanned PDFs | Only for scanned PDFs |
| 5 | Tampering | 🖼️ Vision | Visual tampering detection | Always (page 1) |
| 6 | Fraud | 💬 Chat | Counterparty risk assessment | Always |
| 7 | Insights | 💬 Chat | Narrative report generation | Always |

**Cost Optimization:** For natively digital PDFs (majority of cases), the extraction agent makes **zero LLM calls for transaction data** — using table or word-position parsing instead. This dramatically reduces token usage and latency.

---

## Security & Design Decisions

### Why SQLite?
- **Zero-config** — no database server to install or manage
- **Single-file** — easy backup, portable across machines
- **Sufficient** — bank statement analysis is not high-concurrency; SQLite handles it well
- **Upgrade path** — SQLAlchemy ORM means switching to PostgreSQL requires only a connection string change

### Why Sequential Agents?
- **Data dependencies** — Insights agent requires extraction output
- **Rate limiting** — Prevents Azure OpenAI throttling from parallel Vision calls
- **Debuggability** — Clear execution order, easy to trace failures
- **Resilience** — Each agent is independently try/catch wrapped

### Why Background Tasks?
- **Non-blocking** — API returns 202 immediately, user sees "Processing" status
- **Long-running** — Full analysis takes 30-90 seconds (multiple LLM calls)
- **Progress tracking** — Each agent updates its status independently

### File Storage
- PDFs stored locally in `backend/uploads/` as `{uuid}.pdf`
- Original filename preserved in database for display
- Cascade delete removes file from disk when document is deleted

### CORS Configuration
- Allows `localhost:3000` and `127.0.0.1:3000`
- All HTTP methods and headers permitted (development configuration)
- Credentials enabled for potential future auth
