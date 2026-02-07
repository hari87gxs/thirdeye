# Third Eye — Project Status & Context Document
> **Last Updated:** 2026-02-08  
> **Purpose:** Running doc to provide context for AI assistant continuity across sessions.

---

## 📋 Project Overview

**Third Eye AI** is a multi-agent document intelligence platform for **bank statement analysis**. Users upload PDF bank statements, and 4 specialized AI agents analyze them.

### Tech Stack
| Layer | Tech |
|-------|------|
| **Backend** | Python 3, FastAPI, SQLAlchemy, SQLite, Azure OpenAI (GPT-4o) |
| **Frontend** | Next.js 13.5.6 (App Router), React 18, TypeScript, Tailwind CSS, Recharts, Lucide icons |
| **PDF Processing** | PyMuPDF (fitz), custom extraction agents |

### Architecture
```
┌─────────────────────────────────────────────────────┐
│  Frontend (Next.js :3000)                            │
│  ├── / (Home) — Upload + Document List               │
│  ├── /documents/[id] — Overview + Agent Cards         │
│  ├── /documents/[id]/extraction — Transaction data    │
│  ├── /documents/[id]/insights — Cash flow, categories │
│  ├── /documents/[id]/tampering — PDF integrity checks │
│  └── /documents/[id]/fraud — Anomaly & risk checks    │
└────────────────────┬────────────────────────────────┘
                     │ REST API (http://localhost:8000/api)
┌────────────────────┴────────────────────────────────┐
│  Backend (FastAPI :8000)                             │
│  ├── routers/documents.py — Upload, list, delete      │
│  ├── routers/analysis.py — Trigger analysis, results  │
│  ├── orchestrator.py — Runs 4 agents in sequence      │
│  └── agents/                                          │
│      ├── extraction.py — PDF → transactions + metrics  │
│      ├── insights.py — Cash flow, categories, health   │
│      ├── tampering.py — PDF integrity checks           │
│      └── fraud.py — Transaction anomaly detection      │
└─────────────────────────────────────────────────────┘
```

---

## 🗄️ Database Models (SQLite)

- `Document` — uploaded file metadata, status tracking
- `RawTransaction` — individual extracted transactions per doc
- `StatementMetrics` — per-statement computed metrics
- `AggregatedMetrics` — cross-statement group metrics
- `AgentResult` — JSON results per agent per document (results stored as flexible JSON)

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload` | Upload PDFs |
| GET | `/api/documents` | List all docs |
| GET | `/api/documents/{id}` | Get one doc |
| DELETE | `/api/documents/{id}` | Delete doc |
| POST | `/api/analyze/{document_id}` | Trigger analysis (background) |
| POST | `/api/analyze/group/{group_id}` | Trigger for group |
| GET | `/api/results/{document_id}` | All agent results for doc |
| GET | `/api/results/{document_id}/{agent_type}` | Single agent result |
| GET | `/api/transactions/{document_id}` | Extracted transactions |
| GET | `/api/metrics/{document_id}` | Statement metrics |
| GET | `/health` | Health check |

---

## 📊 Actual API Data Shapes (IMPORTANT — what backend returns)

### Extraction Agent Results
```json
{
  "account_info": { "account_holder": "...", "bank": "...", "account_number": "...", "currency": "SGD", "statement_period": "..." },
  "metrics": { /* same shape as StatementMetrics model */ },
  "transaction_count": 649,
  "pages_processed": 72,
  "extraction_method": "words",
  "accuracy": {
    "overall_score": 100.0,
    "grade": "A+",
    "breakdown": { "balance_chain": { "value": 100, "weight": 40 }, ... },
    "balance_chain_detail": { "total_checked": 646, "valid": 646, "invalid": 0, "chain_accuracy_pct": 100, "breaks": [] }
  }
}
```
> ⚠️ Accuracy is **nested** under `results.accuracy.overall_score`, NOT flat `results.accuracy_score`.

### Insights Agent Results
```json
{
  "category_breakdown": {
    "debit_categories": [{ "category": "other", "label": "Other / Uncategorized", "count": 93, "total": 495477.06, "percentage": 51.3 }],
    "credit_categories": [...]
  },
  "cash_flow": {
    "total_inflow": 901003.81, "total_outflow": 966968.62, "net_flow": -65964.81,
    "weekly_breakdown": [{ "week": "week_1 (1-7)", "inflow": 161292.43, "outflow": 137066.16, "net": 24226.27 }],
    "daily_flow": [{ "day": 1, "inflow": 22551.91, "outflow": 70552.02, "net": -48000.11 }]
  },
  "top_counterparties": {
    "top_vendors": [{ "name": "...", "count": 4, "total": 16728.69 }],
    "top_customers": [{ "name": "...", "count": 15, "total": 165000.0 }]
  },
  "unusual_transactions": {
    "large_transactions": [{ "type": "large_debit", "date": "01 DEC", "description": "...", "amount": 9171.95, "reason": "..." }],
    "round_number_transactions": [...],
    "same_day_large_movements": [...],
    "low_balance_events": [...],
    "total_flags": 48
  },
  "day_of_month_patterns": {
    "daily_pattern": [{ "day": 1, "count": 30 }],
    "busiest_day": ..., "quietest_day": ..., "active_days": 26
  },
  "channel_analysis": {
    "channels": [{ "channel": "OTHER", "count": 306, "total": 866194.79, "percentage": 46.4 }],
    "dominant_channel": "OTHER"
  },
  "business_health": {
    "score": 25, "assessment": "Concern — significant cash flow issues observed",
    "indicators": { "cash_runway_months": ..., "revenue_coverage_ratio": ..., "balance_change": ... }
  },
  "narrative": {  // ⚠️ OBJECT not string!
    "executive_summary": "...",
    "spending_analysis": "...",
    "income_analysis": "...",
    "cash_flow_assessment": "...",
    "risk_observations": "...",
    "recommendations": ["...", "...", "..."]
  }
}
```

### Tampering & Fraud Agent Results
```json
{
  "checks": [{ "check": "Metadata Date Check", "status": "pass", "details": "..." }],
  "risk_score": 3,
  "pass_count": 7,
  "fail_count": 1,
  "warning_count": 0,
  "total_checks": 8
}
```
> ⚠️ Uses `pass_count`/`fail_count`/`warning_count` NOT `passed`/`failed`/`warnings`.
> Check items may NOT have a `metadata` field.

---

## ✅ Issues Fixed (2026-02-08)

### 1. Insights Page Crash — "Objects are not valid as a React child"
- **Root Cause:** The `narrative` field from insights agent is a **dict/object** (with keys: executive_summary, spending_analysis, etc.), not a string. The JSX was rendering `{narrative}` directly.
- **Fix:** Added normalization logic — if narrative is an object, render each section as a titled block. If string, render as before.

### 2. Extraction Accuracy Always Showing 0%
- **Root Cause:** Frontend read `results.accuracy_score` (flat key) but backend returns `results.accuracy.overall_score` (nested object). Same for grade.
- **Fix:** Updated extraction page and document overview AgentCard to read from `results.accuracy.overall_score` with fallback to legacy flat keys.

### 3. Insights Category Breakdown Mismatch
- **Root Cause:** Frontend expected `Record<string, {count, total}>` but backend returns `{debit_categories: [...], credit_categories: [...]}`.
- **Fix:** Added normalization to detect new array-based format and convert for chart display.

### 4. Insights Channel Analysis Mismatch
- **Root Cause:** Frontend expected `Record<string, number>` but backend returns `{channels: [{channel, count, total}], dominant_channel}`.
- **Fix:** Added normalization to extract from channels array.

### 5. Insights Cash Flow — No Monthly Flows
- **Root Cause:** Frontend only used `monthly_flows` but backend provides `weekly_breakdown` and `daily_flow`.
- **Fix:** Falls back to `weekly_breakdown` when `monthly_flows` is absent. Chart X-axis reads `month || week`.

### 6. Insights Unusual Transactions — Object Instead of Array
- **Root Cause:** Frontend expected flat array, backend returns categorized object `{large_transactions, round_number_transactions, ...}`.
- **Fix:** Flattens all sub-arrays into a unified list.

### 7. Insights Business Health — No Grade, Uses Assessment/Indicators
- **Root Cause:** `health.grade` is null; backend uses `health.assessment` string and `health.indicators` (dict, not array of factors).
- **Fix:** Falls back to `assessment` for grade display, converts indicators dict to factor array.

### 8. Insights Day Patterns — `day_of_month_patterns` Not `day_of_week_patterns`
- **Root Cause:** Backend key is `day_of_month_patterns` with nested `daily_pattern` array. Each item has `{day, transaction_count, total_amount}` — frontend was looking for `count` (wrong field name), and the data was never being mapped correctly.
- **Fix:** Updated normalization to read `transaction_count` (not `count`), sort by day number, renamed section heading to "Transaction Activity by Day of Month". Tooltip shows "Day X" format.

### 9. Tampering/Fraud Pass Counts — Wrong Key Names
- **Root Cause:** Frontend used `results.passed`/`results.failed`/`results.warnings` but backend returns `pass_count`/`fail_count`/`warning_count`.
- **Fix:** Added fallback: `pass_count ?? passed ?? ...` in all three pages (tampering, fraud, document overview).

### 10. Insights Top Counterparties — Different Key Names
- **Root Cause:** Frontend expected `by_credit`/`by_debit`, backend returns `top_customers`/`top_vendors`.
- **Fix:** Falls back: `by_credit || top_customers`, `by_debit || top_vendors`.

### 11. Category Pie Chart Overcrowded — Labels Overlapping
- **Root Cause:** Debit + credit categories were merged raw, creating up to 18 slices (12 debit + 6 credit). Duplicate labels (same category appearing in both debit & credit) doubled entries. Inline `label` prop on `<Pie>` caused text overlap.
- **Fix:** (a) Merge same-label categories across debit/credit. (b) Keep only top 5 by total amount, aggregate rest into "Other". (c) Replaced inline pie labels with a clean side legend table showing color swatch, name, percentage, and amount.

---

## 🔧 Known Environment Notes

- **Node.js:** System has 18.16.0. Next.js 13.5.6 works with it, but newer Next.js versions (14+) require Node >= 20.9.0.
- **Python venv:** Located at `/Users/harikrishnan.r/Downloads/third-eye/.venv/` — activate with `source .venv/bin/activate`.
- **Backend start:** `cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000`
- **Frontend start:** `cd frontend && npx next dev --port 3000`
- **Backend uses Azure OpenAI** — requires `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` env vars.
- **CORS** is configured for `localhost:3000`.

---

## 📝 Files Modified in This Session

| File | Changes |
|------|---------|
| `frontend/src/lib/types.ts` | Updated all result interfaces to match actual API shapes (ExtractionResults, InsightsResults, TamperingResults, FraudResults) |
| `frontend/src/app/documents/[id]/extraction/page.tsx` | Read accuracy from nested `results.accuracy.overall_score`, fix transaction count, balance chain |
| `frontend/src/app/documents/[id]/insights/page.tsx` | Major rewrite of data normalization — narrative, categories, channels, counterparties, unusual txns, health, day patterns |
| `frontend/src/app/documents/[id]/tampering/page.tsx` | Use `pass_count`/`fail_count`/`warning_count` with fallbacks |
| `frontend/src/app/documents/[id]/fraud/page.tsx` | Use `pass_count`/`fail_count`/`warning_count` with fallbacks |
| `frontend/src/app/documents/[id]/page.tsx` | Fix AgentCard score display for extraction accuracy + tampering/fraud counts |

---

## 🚧 Pending / Future Items

- [ ] Multi-currency display (ANEXT statements with SGD + USD + other currencies) — currently metrics show only single currency from StatementMetrics
- [ ] Extraction page "Transactions" count card shows `—` when `transaction_count` is stored at top-level but `total_transactions` was the old key
- [ ] Consider upgrading Next.js (13.5.6 is outdated) — but needs Node.js >= 20.9.0
- [ ] The `_*.py` debug/test files in `backend/` should probably be cleaned up or moved to a `scripts/` folder
- [ ] Frontend has no error boundary — a single component crash kills the whole page
