# Integrum Energy — BESCOM Bill Saver AI

AI-assisted **residential electricity bill analysis** for Karnataka / BESCOM domestic consumers, with deterministic validation, bill review, and preliminary **solar options comparison** (individual rooftop, VNM, GNM).

| | |
|---|---|
| **Product** | Integrum Energy — Bill Analysis & Solar Options |
| **Scope (v1)** | Karnataka · BESCOM · Domestic / Residential |
| **Stack** | FastAPI (Python) + Next.js 15 + SQLite + Gemini Vision |
| **Status** | Module 1 & 2 production-ready vertical slice · 114 tests passing |

---

## What it does

### Module 1 — Bill Analysis (UI + API)

1. Upload a BESCOM bill (PDF / JPG / PNG)
2. Gemini extracts structured fields; Python validates and classifies
3. User reviews **required fields only** and confirms
4. App shows a monthly summary: units, amount, cost per unit, annualized estimate

### Module 2 — Solar options compare (UI + API)

After bill confirmation (`status: ready`):

1. Pre-fills consumption, sanctioned load, and tariff from the confirmed bill
2. Compares **individual rooftop solar**, **VNM** (apartment / community), and **GNM** (same-name multi-RR)
3. Shows estimated monthly savings, eligibility status, and official next steps

> **Important:** All ₹ amounts are computed in Python (`TariffEngine` + domain engines). Gemini is used **only for extraction**, never for money math. VNM/GNM results are **preliminary pre-screens**, not BESCOM approval.

---

## Architecture

```
Upload → Gemini extract → Validate → Classify → Consistency → Support gate
                                                                    │
                                    User confirm ← Review form ←────┘
                                         │
                    BillCalculator (Module 1 summary)
                                         │
              CompareSolarOptionsUseCase (Module 2)
                    │         │         │
              SolarEngine  VNMEngine  GNMEngine
                    └─────────┴─────────┘
                              │
                        TariffEngine
```

| Layer | Path | Role |
|-------|------|------|
| API | `app/api/routes/` | HTTP endpoints, CORS, request IDs |
| Application | `app/application/` | Use cases, presenters |
| Domain | `app/domain/` | Engines, models, validation rules |
| Infrastructure | `app/infrastructure/` | Gemini, DB, YAML rules, RAG |
| Frontend | `frontend/` | Integrum-branded Next.js UI |
| Rules | `rules/karnataka/bescom/` | Versioned tariff, solar, VNM, GNM YAML |

**Design principle:** AI extracts → domain validates → rules classify → user confirms → Python calculates.

---

## Scope & gating

| Supported | Not in v1 UI |
|-----------|----------------|
| Karnataka / BESCOM | Other states / DISCOMs |
| Domestic (LT-1) | Commercial / industrial |
| Bill extract + confirm + solar compare | Login, accounts, installer quotes |
| Preliminary VNM / GNM pre-screen | BESCOM sanction / PPA |

Non-BESCOM bills are extracted but **gated** (`status: unsupported`) — no confirm or solar engines.

---

## Quick start (development)

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Gemini API key](https://aistudio.google.com/apikey)

### 1. Backend

```powershell
cd bescom-bill-saver-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env — set GEMINI_API_KEY

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API: http://127.0.0.1:8000  
- Swagger: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/health  

### 2. Frontend

```powershell
cd frontend
copy .env.local.example .env.local
npm install
npm run dev
```

- UI: http://localhost:3000  

### 3. Run tests

```powershell
.\.venv\Scripts\Activate.ps1
pytest -q
cd frontend && npm run build
```

---

## Production deployment

### Environment variables

Copy `.env.example` → `.env` and set:

| Variable | Production notes |
|----------|------------------|
| `GEMINI_API_KEY` | Required. Store in secrets manager, not in git. |
| `GEMINI_MODEL` | Default `gemini-2.5-flash` |
| `DATABASE_URL` | Use PostgreSQL for production (`postgresql://...`) |
| `UPLOAD_DIR` | Persistent volume (e.g. `/var/data/uploads`) |
| `MAX_UPLOAD_BYTES` | Default 10 MB |
| `APP_ENV` | Set to `production` |
| `LOG_LEVEL` | `INFO` or `WARNING` |
| `CORS_ORIGINS` | Your frontend origin(s), comma-separated |
| `API_PUBLIC_URL` | Public API URL (e.g. `https://api.example.com`) |
| `DOCS_DIR` | Path to official PDFs for RAG (optional) |

Frontend (`frontend/.env.local`):

| Variable | Value |
|----------|--------|
| `NEXT_PUBLIC_API_BASE` | Public API URL |

### Recommended production setup

```text
[Browser] → [CDN / Next.js] → [Reverse proxy TLS] → [Uvicorn / Gunicorn workers]
                                                          │
                                                    [PostgreSQL]
                                                    [Upload volume]
                                                    [Gemini API]
```

- Run API with multiple workers: `gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4`
- Serve Next.js via `npm run build && npm start` or static export behind CDN
- Enable HTTPS; restrict `CORS_ORIGINS` to your domain
- Back up `DATABASE_URL` and `UPLOAD_DIR` regularly
- Do **not** commit `.env`, bill images, databases, or `data/Docs/*.pdf`

### Security

- Request ID + security headers middleware (`app/api/middleware.py`)
- Upload size and file-type validation
- Account ID masked in review UI
- No authentication in v1 — add auth before public multi-tenant deployment

---

## API reference (production modules)

### Module 1 — Bill Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/bills/extract` | Upload single bill → extract + validate |
| `POST` | `/bills/extract-batch` | Upload multiple bills |
| `POST` | `/bills/{analysis_id}/confirm` | User corrections / attestation |
| `GET` | `/bills/{analysis_id}` | Reload analysis view |
| `GET` | `/bills` | List recent analyses |
| `GET` | `/consumers/{consumer_id}/history` | Consumption history by RR/account |

**Confirm body example:**

```json
{
  "corrections": { "units_consumed": 286 },
  "confirm_category": "DOMESTIC",
  "accept_extracted_as_printed": ["total_amount", "energy_charge"],
  "note": "Checked against printed bill"
}
```

### Module 2 — Solar options

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/bills/{analysis_id}/solar-options/prefill` | Prefill from confirmed bill |
| `POST` | `/bills/{analysis_id}/solar-options` | Compare rooftop / VNM / GNM |

**Compare body example:**

```json
{
  "plant": { "proposed_kwp": 5.0, "roof_area_m2": 40 },
  "vnm_participants": [
    { "connection_id": "Flat-2", "procurement_share_percent": 50, "monthly_units": 250 }
  ],
  "gnm_installations": [
    { "connection_id": "RR-SECOND", "priority": 2, "is_host": true }
  ]
}
```

### Standalone engines (Swagger / integrations — no dedicated UI tab)

| Endpoint | Engine |
|----------|--------|
| `POST /solar/analyze` | Individual rooftop sizing |
| `POST /vnm/analyze` | Virtual Net Metering pre-screen |
| `POST /gnm/analyze` | Group Net Metering pre-screen |
| `POST /tariff/calculate` | DOMESTIC tariff calculation |
| `POST /metering/compare` | NET vs GROSS metering |
| `POST /schemes/gruha-jyothi/analyze` | Gruha Jyothi eligibility |
| `POST /savings/analyze` | Savings recommendations |
| `POST /rag/search` | Official document RAG |
| `POST /agent/ask` | Tool-calling agent |

---

## Where calculations live

| Calculator | File | Used for |
|------------|------|----------|
| Bill summary | `app/domain/services/bill_calculator.py` | Cost/unit, annualized (Module 1) |
| Retail tariff | `app/domain/engines/tariff.py` | DOMESTIC bill from units + load |
| Rooftop solar | `app/domain/engines/solar.py` | Individual plant + saving |
| VNM | `app/domain/engines/vnm.py` | Share allocation + group saving |
| GNM | `app/domain/engines/gnm.py` | Priority waterfall + group saving |
| Orchestration | `app/application/use_cases/compare_solar_options.py` | Module 2 compare |

Rules: `rules/karnataka/bescom/solar/*.yaml`, `rules/karnataka/bescom/tariff/*.yaml`

---

## Project structure

```text
bescom-bill-saver-ai/
├── app/
│   ├── api/routes/          # HTTP endpoints
│   ├── application/         # Use cases, presenters
│   ├── domain/              # Engines, models, services
│   ├── infrastructure/      # Gemini, DB, rules loaders, RAG
│   └── main.py
├── frontend/                # Next.js UI (Integrum theme)
├── rules/                   # Versioned YAML business rules
├── data/
│   ├── uploads/             # Bill uploads (gitignored)
│   └── Docs/                # Official PDFs for RAG (gitignored)
├── docs/
│   ├── BILL_ANALYSIS_MODULE_STATUS.md   # Full module + calculator docs
│   └── samples/             # API response examples
├── tests/                   # pytest suite (114 tests)
├── requirements.txt
└── .env.example
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [`docs/BILL_ANALYSIS_MODULE_STATUS.md`](docs/BILL_ANALYSIS_MODULE_STATUS.md) | Module 1 & 2 status, field requirements, VNM/GNM formulas, API shapes |
| [`docs/samples/`](docs/samples/) | Example extract / confirm JSON responses |
| [`frontend/README.md`](frontend/README.md) | Frontend setup and UI flow |
| http://127.0.0.1:8000/docs | Interactive OpenAPI (Swagger) |

---

## Official docs corpus (RAG)

Place PDFs and digests in `data/Docs/`:

```text
data/Docs/
  VNM_GNM_official_digest.md
  net_metering_digest.md
  KSEC regulations.pdf          # optional
```

RAG supports policy Q&A via `/rag/search` and the agent. **Engines own all ₹ and eligibility math** — never treat RAG or the agent as BESCOM approval.

---

## Disclaimers

- Extraction is AI-assisted; users must confirm required fields before calculations run.
- VNM/GNM/solar outputs are **preliminary estimates** based on bootstrap YAML rules (`verification_status: REQUIRES_VERIFICATION`).
- This application does **not** approve net metering, clear technical feasibility, or execute PPAs.
- Confirm against the latest [BESCOM SRTPV portal](https://srtpv.bescom.org/) and KERC orders before advising consumers.

---

## Roadmap

| Priority | Item |
|----------|------|
| Next | Persist solar comparison results per `analysis_id` |
| Next | Consumption history panel after confirm |
| Next | Plain-language bill explanation |
| Later | NET vs GROSS metering in UI |
| Later | User authentication |
| Later | PostgreSQL + containerized deployment manifests |

---

## License & support

Internal Integrum Energy product module. For module status and implementation detail, see [`docs/BILL_ANALYSIS_MODULE_STATUS.md`](docs/BILL_ANALYSIS_MODULE_STATUS.md).
