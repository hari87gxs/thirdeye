<p align="center">
  <img src="frontend/public/logo.png" alt="ThirdEye AI" width="200" />
</p>

<h1 align="center">ThirdEye AI</h1>
<p align="center">
  <strong>Multi-Agent Financial Document Analyzer</strong><br />
  Upload bank statements. Let 4 specialized AI agents do the rest.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" />
  <img src="https://img.shields.io/badge/Next.js-13.5-black?logo=next.js" />
  <img src="https://img.shields.io/badge/GPT--4o-Azure%20OpenAI-orange?logo=openai" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker" />
</p>

---

## What is ThirdEye?

ThirdEye AI is an **intelligent multi-agent platform** that analyzes bank statement PDFs using four specialized AI agents:

| Agent | Purpose | Key Capability |
|-------|---------|----------------|
| 🔵 **Extraction** | Extracts transactions, balances, account info | Zero-LLM table/word-position parsing for 18+ bank formats |
| 🟣 **Insights** | Cash flow, spending patterns, business health | Composite health score (0–100) with 7 indicators |
| 🟡 **Tampering** | PDF integrity & manipulation detection | 8 checks including CV2 sharpness analysis + GPT-4o Vision |
| 🔴 **Fraud** | Anomaly detection & risk assessment | Statistical outlier detection + LLM counterparty risk analysis |

### Supported Banks (Singapore Focus)

DBS · POSB · OCBC · UOB · Standard Chartered · HSBC · Citibank · Maybank · CIMB · Bank of China · ICBC · GXS Bank · Trust Bank · MariBank · Revolut · Wise · **Aspire** · **Airwallex (ANEXT)**

---

## Local Deployment Guide (macOS)

### Prerequisites

| Requirement | Minimum Version | Check Command |
|-------------|----------------|---------------|
| **Python** | 3.10+ | `python3 --version` |
| **Node.js** | 18.0+ | `node --version` |
| **npm** | 9.0+ | `npm --version` |
| **Git** | Any | `git --version` |
| **Azure OpenAI Access** | GPT-4o deployment | — |

> **Don't have these?** Install via [Homebrew](https://brew.sh):
> ```bash
> brew install python@3.12 node@18
> ```
> Or use [nvm](https://github.com/nvm-sh/nvm) for Node.js version management.

---

### Step 1 — Clone the Repository

```bash
git clone <your-repo-url> third-eye
cd third-eye
```

### Step 2 — Backend Setup

```bash
# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
cd backend
pip install -r requirements.txt
```

#### Configure Environment Variables

Create a `.env` file inside the `backend/` directory:

```bash
cat > .env << 'EOF'
# ──── Azure OpenAI Configuration (Required) ────
AZURE_OPENAI_API_KEY=your-azure-openai-api-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/

# ──── Optional Overrides (defaults shown) ────
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_VISION_DEPLOYMENT=gpt-4o
DATABASE_URL=sqlite:///./third_eye.db
EOF
```

> **How to get Azure OpenAI credentials:**
> 1. Go to [Azure Portal](https://portal.azure.com) → Create or open an **Azure OpenAI** resource
> 2. Deploy a **GPT-4o** model (used for both chat and vision capabilities)
> 3. Navigate to **Keys and Endpoint** → copy the **Key** and **Endpoint URL**

#### Start the Backend

```bash
# From the backend/ directory, with venv activated
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Verify it's running:
```bash
curl http://localhost:8000/health
# → {"status": "healthy", "version": "1.0.0"}
```

### Step 3 — Frontend Setup

Open a **new terminal** tab/window:

```bash
cd third-eye/frontend

# Install Node.js dependencies
npm install

# Start the development server
node node_modules/next/dist/bin/next dev --port 3000
```

> **Alternative start commands:**
> ```bash
> ./node_modules/.bin/next dev --port 3000    # Direct binary
> npx --no-install next dev --port 3000       # npx (local only)
> ```

### Step 4 — Open the App

Navigate to **http://localhost:3000** in your browser. You're ready to upload bank statements!

---

### Quick Start (Copy-Paste)

```bash
# ─── Terminal 1: Backend ───
cd third-eye
python3 -m venv .venv && source .venv/bin/activate
cd backend && pip install -r requirements.txt
# ⚠️ Create backend/.env with your Azure OpenAI credentials first!
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# ─── Terminal 2: Frontend ───
cd third-eye/frontend
npm install
node node_modules/next/dist/bin/next dev --port 3000

# ─── Browser ───
# → http://localhost:3000
```

---

## Run with Docker (Recommended)

The easiest way to run ThirdEye — no Python/Node.js installation needed.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Azure OpenAI API key and endpoint

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/hari87gxs/thirdeye.git
cd thirdeye

# 2. Create your .env file
cp .env.example .env
# Edit .env and fill in your Azure OpenAI credentials:
#   AZURE_OPENAI_API_KEY=your-key
#   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/

# 3. Build and start both services
docker compose up --build -d

# 4. Open the app
open http://localhost:3000
```

That's it! Backend runs on port 8000, frontend on port 3000.

### Docker Commands Reference

```bash
# View logs
docker compose logs -f              # all services
docker compose logs -f backend      # backend only

# Stop
docker compose down

# Rebuild after code changes
docker compose up --build -d

# Stop and wipe database + uploads
docker compose down -v
```

> **Deploying to AWS?** See [DEPLOYMENT.md](./DEPLOYMENT.md) for full EC2 and ECS Fargate guides.

---

## Project Structure

```
third-eye/
├── README.md                    ← You are here
├── ARCHITECTURE.md              ← System architecture deep-dive
├── USER_GUIDE.md                ← Feature guide & user manual
├── DEPLOYMENT.md                ← AWS deployment guide (EC2 & ECS)
├── docker-compose.yml           # One-command local Docker deployment
├── .env.example                 # Environment variable template
│
├── backend/
│   ├── Dockerfile               # Backend container image
│   ├── main.py                  # FastAPI app + CORS + startup
│   ├── config.py                # Settings & environment variables
│   ├── database.py              # SQLAlchemy engine & sessions
│   ├── models.py                # 5 database tables + enums
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── orchestrator.py          # Sequential multi-agent pipeline
│   ├── requirements.txt         # Python dependencies
│   ├── agents/
│   │   ├── base.py              # Abstract base agent class
│   │   ├── extraction.py        # Transaction extraction (2300+ lines)
│   │   ├── insights.py          # Cash flow & business health
│   │   ├── tampering.py         # PDF integrity checks
│   │   └── fraud.py             # Anomaly & fraud detection
│   ├── routers/
│   │   ├── documents.py         # Upload, list, delete endpoints
│   │   └── analysis.py          # Analysis trigger & results
│   ├── services/
│   │   ├── llm_client.py        # Azure OpenAI client wrapper
│   │   └── pdf_processor.py     # PDF text/image/metadata utilities
│   └── uploads/                 # Stored PDF files
│
└── frontend/
    ├── Dockerfile               # Frontend container image (multi-stage)
    ├── package.json
    ├── public/logo.png          # ThirdEye logo
    └── src/
        ├── app/
        │   ├── layout.tsx       # Root layout + Navbar
        │   ├── page.tsx         # Home: upload & document list
        │   └── documents/[id]/  # Document detail pages
        │       ├── page.tsx     # Overview + 4 agent cards
        │       ├── extraction/  # Extraction results
        │       ├── insights/    # Insights results
        │       ├── tampering/   # Tampering results
        │       └── fraud/       # Fraud results
        ├── components/
        │   ├── layout/Navbar.tsx
        │   ├── upload/FileUploadZone.tsx
        │   └── documents/DocumentList.tsx
        └── lib/
            ├── api.ts           # Backend API client
            ├── types.ts         # TypeScript interfaces
            └── utils.ts         # Formatting helpers
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `AZURE_OPENAI_API_KEY` | ✅ | — | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | ✅ | — | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_VERSION` | | `2024-12-01-preview` | API version |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | | `gpt-4o` | Chat model deployment name |
| `AZURE_OPENAI_VISION_DEPLOYMENT` | | `gpt-4o` | Vision model deployment name |
| `DATABASE_URL` | | `sqlite:///./third_eye.db` | SQLAlchemy DB connection string |
| `ALLOWED_ORIGINS` | | `http://localhost:3000` | Comma-separated CORS origins |
| `NEXT_PUBLIC_API_URL` | | `http://localhost:8000/api` | Backend URL for frontend |

---

## API Documentation

With the backend running, interactive API docs are available at:

| Format | URL |
|--------|-----|
| **Swagger UI** | http://localhost:8000/docs |
| **ReDoc** | http://localhost:8000/redoc |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Address already in use` (port 8000) | `lsof -ti:8000 \| xargs kill -9` |
| `Address already in use` (port 3000) | `lsof -ti:3000 \| xargs kill -9` |
| Node.js version error `>=20.9.0 required` | Use `node node_modules/next/dist/bin/next dev` instead of `npx` |
| `AZURE_OPENAI_API_KEY` not set | Create `backend/.env` with credentials |
| `ModuleNotFoundError` in Python | Activate venv: `source .venv/bin/activate` |
| Frontend shows no documents | Verify backend is running on port 8000 |
| Analysis stuck at "processing" | Check backend terminal — likely Azure credential issue |
| PDF upload rejected | Must be `.pdf` format, max 50MB per file |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3 · FastAPI · SQLAlchemy · SQLite |
| **PDF Processing** | PyMuPDF · pdfplumber · pdf2image · Pillow |
| **Image Analysis** | OpenCV (headless) · NumPy |
| **AI / LLM** | Azure OpenAI GPT-4o (chat + vision) |
| **Frontend** | Next.js 13 · React 18 · TypeScript · Tailwind CSS |
| **Charts** | Recharts |
| **UI Primitives** | Radix UI |

---

## Documentation

| Document | Description |
|----------|-------------|
| 📐 [ARCHITECTURE.md](./ARCHITECTURE.md) | System design, data flow, agent internals, database schema |
| 📖 [USER_GUIDE.md](./USER_GUIDE.md) | Feature walkthrough, agent capabilities, competitive advantages |
| 🚀 [DEPLOYMENT.md](./DEPLOYMENT.md) | Docker setup + AWS deployment (EC2 & ECS Fargate) |
| 📝 [PROJECT_STATUS.md](./PROJECT_STATUS.md) | Development session log & bug fix history |
