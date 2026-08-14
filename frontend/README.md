# Integrum Energy — Frontend

Production UI for **Module 1 (Bill Analysis)** and **Module 2 (Solar options compare)**.

| Module | UI component | When shown |
|--------|--------------|--------------|
| Bill upload & processing | `UploadPanel`, `ProcessingSteps` | Always |
| Bill review & confirm | `BillReviewForm` | `status: needs_review` |
| Unsupported bill notice | `UnsupportedBillNotice` | `status: unsupported` |
| Bill summary | `AnalysisSummary` | Right panel |
| Solar compare | `SolarOptionsPanel` | After `status: ready` + BESCOM supported |

---

## Run locally

```bash
# Terminal 1 — API (from repo root)
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Terminal 2 — UI
cd frontend
copy .env.local.example .env.local
npm install
npm run dev
```

| URL | Service |
|-----|---------|
| http://localhost:3000 | Frontend |
| http://127.0.0.1:8000/docs | API Swagger |

---

## Environment

```env
# frontend/.env.local
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```

For production, set `NEXT_PUBLIC_API_BASE` to your public API URL and ensure that origin is listed in backend `CORS_ORIGINS`.

---

## User flow

```
Upload bill
    → Processing steps (upload, extract, validate, check)
    → Review form (required fields marked *)
    → Confirm & continue
    → Monthly summary banner + side panel
    → Compare solar options (rooftop / VNM / GNM)
```

### Review form

- Calls `POST /bills/{analysis_id}/confirm`
- Required fields validated client-side before submit
- Account ID shown masked; real value sent on confirm
- Subsidy hidden unless detected on bill image

### Solar options panel

- `GET /bills/{id}/solar-options/prefill` on load
- `POST /bills/{id}/solar-options` on **Compare options**
- User can add VNM participants (flats + share %) or GNM installations (RR + priority + host)
- Result cards show status, estimated monthly saving, and disclaimers

---

## Build for production

```bash
npm run build
npm start
```

Or deploy the `.next` output to your hosting platform (Vercel, container, etc.) with `NEXT_PUBLIC_API_BASE` set at build time.

---

## Key files

| Path | Purpose |
|------|---------|
| `app/page.tsx` | Main bill analysis + solar options page |
| `components/bill-analysis/` | Upload, review, summary |
| `components/solar-options/SolarOptionsPanel.tsx` | Module 2 compare UI |
| `lib/bill-analysis.ts` | Bill API types |
| `lib/solar-options.ts` | Solar options types |
| `lib/api.ts` | HTTP client |
| `app/globals.css` | Integrum navy / orange theme |

---

## API mapping

| UI action | API |
|-----------|-----|
| Upload single bill | `POST /bills/extract` |
| Upload multiple | `POST /bills/extract-batch` |
| Confirm review | `POST /bills/{analysis_id}/confirm` |
| Solar prefill | `GET /bills/{analysis_id}/solar-options/prefill` |
| Solar compare | `POST /bills/{analysis_id}/solar-options` |

See root [`README.md`](../README.md) and [`docs/BILL_ANALYSIS_MODULE_STATUS.md`](../docs/BILL_ANALYSIS_MODULE_STATUS.md) for full backend documentation.
