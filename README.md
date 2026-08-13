# BESCOM Bill Saver AI

Karnataka / BESCOM residential electricity bill advisor with **VNM / GNM** preliminary analysis and official-document RAG.

## Current milestone

**Milestone 24 complete** — user confirmation & field correction

| M | Focus |
|---|--------|
| 20 | RAG over `data/Docs` (`/rag/*`, agent tool `search_official_docs`) |
| 21 | Evaluation framework (`/eval/run`, `app/evaluation`) |
| 22 | Next.js frontend (`frontend/`) — bills, VNM, GNM, docs, agent |
| 23 | Production hardening (CORS, request IDs, security headers, support gate) |
| 24 | `POST /bills/{analysis_id}/confirm` — correct / accept OCR fields, re-validate |

```bash
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

- Swagger: http://127.0.0.1:8000/docs
- Confirm fields: `POST /bills/{analysis_id}/confirm`
- RAG: `GET /rag/sources`, `POST /rag/search`
- VNM: `POST /vnm/analyze`
- GNM: `POST /gnm/analyze`
- Eval: `GET /eval/run`
- Frontend: see `frontend/README.md`

### Confirm body example

```json
{
  "corrections": { "units_consumed": 286, "rr_number": "RR123" },
  "confirm_category": "DOMESTIC",
  "accept_extracted_as_printed": ["total_amount"],
  "note": "Checked against printed bill"
}
```

Corrected fields are stored with `source: "user"` and confidence `1.0`, then validation / category / consistency re-run on the **same** `analysis_id`.

## Official docs corpus

Place PDFs / digests in:

```text
data/Docs/
  KSEC regulations.pdf
  VNM_GNM_official_digest.md
  net_metering_digest.md
```

**Git:** `.env`, bill images, uploads, DBs, and `data/Docs/*.pdf` / `_extracted*` are gitignored. Commit only `.env.example` / `frontend/.env.local.example`. Copy secrets and official PDFs locally after clone.

RAG retrieves snippets for policy Q&A. **Engines still own ₹ / eligibility math.** Never treat RAG or the agent as BESCOM approval.

## Scope

- State: **Karnataka**
- DISCOM: **BESCOM**
- Category v1: **DOMESTIC**
- Non-BESCOM uploads extract but are **gated** via `support_gate.supported_for_money_engines`
