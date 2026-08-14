# Integrum Energy — Bill Analysis & Solar Options Status

**Product:** Integrum Energy — Residential Electricity Bill Analysis  
**Scope (v1):** Karnataka · BESCOM · Domestic / Residential  
**Document purpose:** What each module does, where calculations live, what the API/UI return, and current completion status.

**Last updated:** August 2026

---

## 1. Executive summary

| Question | Answer |
|----------|--------|
| What can a user do today? | Upload bill → review required fields → confirm → see monthly summary → **compare solar options (individual / VNM / GNM)**. |
| What DISCOM is supported for full analysis? | **BESCOM only** (Karnataka domestic). |
| What happens for AP / other bills? | Extraction runs; status = **unsupported**; no confirm / solar engines. |
| Where are ₹ calculations done? | **Python only** — never Gemini. See §8 (calculator map). |
| Module 1 (Bill Analysis) | **Complete** for v1 vertical slice. |
| Module 2 (Solar options) | **Complete** for v1 pre-screen + savings comparison UI. |

---

## 2. Module map

| Module | User-facing name | Backend entry | UI |
|--------|------------------|---------------|-----|
| **1** | Bill Analysis | `POST /bills/extract`, `POST /bills/{id}/confirm` | Upload, review form, summary |
| **2** | Solar options compare | `GET/POST /bills/{id}/solar-options/*` | Compare panel after `ready` |
| — | Standalone engines (dev/Swagger) | `POST /vnm/analyze`, `POST /gnm/analyze`, `POST /solar/analyze` | Not separate tabs |

---

## 3. End-to-end pipeline — Module 1 (Bill Analysis)

```
User uploads PDF/JPG/PNG
        │
        ▼
┌───────────────────┐
│ File validation   │  type, size, empty, corrupt
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Gemini Vision     │  ← AI reads image (structured JSON)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Validate/Normalize│  ₹ strings → numbers, LT1 → LT-1
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Classify          │  LT-1 → DOMESTIC (rules, not LLM)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Consistency check │  meter delta vs units, charges vs total
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Support gate      │  BESCOM + domestic?
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Save to database  │  consumer linked by RR / Account ID
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ User review UI    │  required fields marked *
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ User confirms     │  corrections + accept_as_printed
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ BillCalculator    │  cost/unit, annualized estimate
└─────────┬─────────┘
          ▼
   status: ready  →  Module 2 available
```

**Principle:** AI extracts. Python validates, classifies, calculates. User confirms.

---

## 4. End-to-end pipeline — Module 2 (Solar options)

```
Bill status = ready  (Module 1 complete, BESCOM domestic)
        │
        ▼
┌───────────────────────────┐
│ GET …/solar-options/prefill│  units, load, tariff, suggested kWp from bill
└─────────┬─────────────────┘
          ▼
┌───────────────────────────┐
│ User sets plant kWp, roof   │  optional VNM flats / GNM RR numbers
└─────────┬─────────────────┘
          ▼
┌───────────────────────────┐
│ POST …/solar-options        │  CompareSolarOptionsUseCase
└─────────┬─────────────────┘
          │
    ┌─────┼─────┐
    ▼     ▼     ▼
 Solar  VNM   GNM
Engine Engine Engine
    │     │     │
    └─────┴─────┘
          ▼
   Side-by-side option cards (saving ₹, status, disclaimers)
```

**Orchestrator:** `app/application/use_cases/compare_solar_options.py`  
**Bill → inputs mapper:** `app/application/services/bill_to_solar_inputs.py`  
**DTOs:** `app/domain/models/solar_options.py`  
**API:** `app/api/routes/solar_options.py`  
**UI:** `frontend/components/solar-options/SolarOptionsPanel.tsx`

---

## 5. Required vs optional fields (Module 1 confirm gate)

Defined in: `app/domain/models/bill_field_requirements.py`  
Confirm gate logic: `app/domain/services/bill_confirmation_needs.py`

### Required (must verify to reach `ready`)

| Section | Fields |
|---------|--------|
| Consumer | `consumer_name`, `account_id`, `address` |
| Connection | `utility`, `discom`, `tariff_code`, `sanctioned_load` |
| Billing | `billing_period`, `bill_date` |
| Meter | `units_consumed` |
| Charges | `energy_charge`, `fixed_charge`, `total_amount` |
| Document | `document_language`, `is_bescom_bill` |

### Optional (shown when extracted; never block confirm)

`rr_number`, `consumer_category` (derived from tariff in UI), `due_date`, meter readings, `electricity_tax`, `fppca`, `other_charges`, `arrears`, `late_payment_charge`

### Special

| Field | Rule |
|-------|------|
| `subsidy` | Hidden unless non-zero value detected on bill |
| `extraction_notes` | Never shown in review UI |

---

## 6. All extractable fields (27 fields)

Every field uses:

```json
{
  "value": "<string | number | boolean | null>",
  "confidence": 0.0,
  "source": "bill | inferred | user | unknown",
  "level": "HIGH | MEDIUM | LOW | MISSING"
}
```

| # | Field | Section |
|---|-------|---------|
| 1–6 | utility, discom, consumer_name, account_id, rr_number, address | Consumer / Connection |
| 7–9 | consumer_category, tariff_code, billing_period | Connection / Billing |
| 10–11 | bill_date, due_date | Billing |
| 12–15 | previous_meter_reading, current_meter_reading, units_consumed, sanctioned_load | Meter / Connection |
| 16–24 | energy_charge … total_amount | Charges |
| 25–27 | document_language, is_bescom_bill, extraction_notes | Document |

Samples: `docs/samples/bescom_extract_clean.json`, `bescom_api_extract_response.json`, `bescom_api_confirm_response.json`

---

## 7. API shapes (Module 1)

### After extract — `POST /bills/extract`

- `status`: `needs_review` | `unsupported`
- `needs_confirmation`: list of **required** fields still weak/missing
- `calculations`: `null` until confirmed

### After confirm — `POST /bills/{id}/confirm`

- `status`: `ready`
- `message`: e.g. *"Bill confirmed. You paid ₹349.67 for 57 kWh for Jul-2026."*
- `calculations`: from `BillCalculator` (cost/unit, annualized)

---

## 8. Where calculators live (important)

There is **no single “VNM/GNM calculator” class**. Savings are computed inside **domain engines** that all share **`TariffEngine`** for retail bill amounts.

### Calculator map

| Purpose | Class / file | What it computes |
|---------|--------------|------------------|
| **Module 1 bill summary** | `BillCalculator` — `app/domain/services/bill_calculator.py` | `cost_per_unit`, charge-line sum vs total, annualized units/₹ |
| **Module 1 presenter** | `BillAnalysisPresenter` — `app/application/services/bill_analysis_presenter.py` | Calls `BillCalculator`; builds UI DTOs |
| **Retail tariff (shared)** | `TariffEngine` — `app/domain/engines/tariff.py` | DOMESTIC LT slab bill from units + sanctioned load + `as_of` date |
| **Individual rooftop** | `SolarAnalysisEngine` — `app/domain/engines/solar.py` | Plant sizing, generation, **monthly saving** vs baseline retail |
| **VNM savings** | `VNMAnalysisEngine` — `app/domain/engines/vnm.py` | Per-flat allocation + **group monthly saving** |
| **GNM savings** | `GNMAnalysisEngine` — `app/domain/engines/gnm.py` | Priority waterfall + host 20% rule + **group monthly saving** |
| **Module 2 orchestration** | `CompareSolarOptionsUseCase` — `app/application/use_cases/compare_solar_options.py` | Runs the three engines; picks best option |

**Rules (YAML, not code magic):**

| Engine | Rules file |
|--------|------------|
| Tariff | `rules/karnataka/bescom/tariff/*.yaml` |
| Solar | `rules/karnataka/bescom/solar/rooftop_v1.yaml` |
| VNM | `rules/karnataka/bescom/solar/vnm_v1.yaml` |
| GNM | `rules/karnataka/bescom/solar/gnm_v1.yaml` |

---

## 9. How VNM saver calculation works

**Engine:** `VNMAnalysisEngine.analyze()` in `app/domain/engines/vnm.py`

### Step 1 — Eligibility pre-screen (SOP rules from YAML)

- ≥ 2 participants, same category, procurement shares sum to 100%
- Plant ≥ 5 kWp, plant ≤ combined sanctioned load
- Same DISCOM area declared
- Technical feasibility **never** auto-approved

### Step 2 — Generation estimate

```
monthly_gen = proposed_kwp × (specific_yield_kwh_per_kwp_year / 12)
```

Default yield: **1480 kWh/kWp/year** from `vnm_v1.yaml` (or caller-supplied `estimated_monthly_generation_kwh`).

### Step 3 — Allocate credit per participant (by procurement share %)

```
allocated_kwh = monthly_gen × (procurement_share_percent / 100)
residual_units = max(0, monthly_units − allocated_kwh)
surplus_kwh    = max(0, allocated_kwh − monthly_units)
```

### Step 4 — ₹ per participant (uses TariffEngine)

```
baseline_total = TariffEngine(units = monthly_units, sanctioned_load_kw, tariff_code, as_of)
new_total      = TariffEngine(units = residual_units, …)

excess_rate    = 75% × generic_tariff_inr_per_kwh   # bootstrap ₹3.66 → ₹2.745/kWh
surplus_inr    = surplus_kwh × excess_rate
net_cost       = new_total − surplus_inr
saving         = baseline_total − net_cost
```

### Step 5 — Group result

```
estimated_group_monthly_saving_inr = sum(saving) across all participants
```

Returned on: `result.estimated_group_monthly_saving_inr` and per-participant `estimated_monthly_saving_inr`.

**Status values:** `POTENTIALLY_SUITABLE`, `POTENTIALLY_UNSUITABLE`, `INSUFFICIENT_INFORMATION`, `TECHNICAL_VERIFICATION_REQUIRED`  
**Never:** “You are approved for VNM.”

---

## 10. How GNM saver calculation works

**Engine:** `GNMAnalysisEngine.analyze()` in `app/domain/engines/gnm.py`

### Step 1 — Eligibility pre-screen

- ≥ 2 installations under **same consumer name**
- Exactly one **host** installation
- Unique priorities
- Same plant min/max rules as VNM

### Step 2 — Generation estimate

Same formula as VNM (`proposed_kwp` × yield / 12).

### Step 3 — Host 20% reserve + priority waterfall

```
reserved_kwh = monthly_gen × 20%                    # host band
host_takes   = min(host.monthly_units, reserved)
lapsed_kwh   = reserved − host_takes                # lapses if host use is low
pool         = monthly_gen − reserved

# Waterfall by priority (1 = first):
for each installation in priority order:
    need = monthly_units − credits_so_far
    take = min(need, pool)
    credits[connection] += take
    pool -= take

unallocated = remaining pool → attributed to host as export surplus
```

### Step 4 — ₹ per installation (same TariffEngine pattern as VNM)

For each RR:

```
residual_units = max(0, monthly_units − allocated_credit)
surplus_kwh    = max(0, allocated − monthly_units) + host_export_extra

baseline_total = TariffEngine(monthly_units)
new_total      = TariffEngine(residual_units)
surplus_inr    = surplus_kwh × excess_rate
net_cost       = new_total − surplus_inr
saving         = baseline_total − net_cost
```

### Step 5 — Group result

```
estimated_group_monthly_saving_inr = sum(saving) across installations
```

Also returns: `host_reserved_kwh`, `lapsed_kwh`, `unallocated_generation_kwh`.

---

## 11. How individual rooftop saving differs

**Engine:** `SolarAnalysisEngine` — `app/domain/engines/solar.py`

- Sizes plant from monthly units + roof area + sanctioned load caps
- Estimates generation from YAML yield
- Offsets consumption (simplified model — not full net-metering settlement)
- **Saving** = `TariffEngine(full_units) − TariffEngine(residual_units_after_offset)` minus surplus credit at excess rate

Module 2 passes `roof_area_m2` and `proposed_kwp` from the UI.

---

## 12. Module 2 API

### Prefill — `GET /bills/{analysis_id}/solar-options/prefill`

Requires: bill `ready`, BESCOM domestic supported.

Returns `prefill` from confirmed bill:

- `monthly_units`, `sanctioned_load_kw`, `tariff_code`, `discom`, `as_of`
- `connection_id` (RR or account)
- `suggested_plant_kwp` (from consumption heuristic in `bill_to_solar_inputs.py`)

### Compare — `POST /bills/{analysis_id}/solar-options`

```json
{
  "plant": {
    "proposed_kwp": 5.0,
    "roof_area_m2": 40,
    "same_discom_area": true,
    "same_consumer_name": true
  },
  "vnm_participants": [
    { "connection_id": "Flat-2", "procurement_share_percent": 50, "monthly_units": 250 }
  ],
  "gnm_installations": [
    { "connection_id": "RR-SECOND", "priority": 2, "is_host": true }
  ]
}
```

Response `comparison.options[]` — one card each for `individual_solar`, `vnm`, `gnm`:

- `status`, `monthly_saving_inr`, `plant_kwp`, `message`, `missing_inputs`
- `best_option` — highest saving among suitable statuses

**Note:** With only one connection, VNM/GNM return `INSUFFICIENT_INFORMATION` until user adds a second participant (SOP requires ≥ 2).

---

## 13. What is stored in the database

Table: `bill_analyses`

| Column / JSON | Contents |
|---------------|----------|
| Scalars | `rr_number`, `account_id`, `units_consumed`, `total_amount`, `bill_date`, `category`, … |
| `extraction_json` | Raw AI extraction |
| `validation_json` | Canonical bill + issues + `corrections_audit` |
| `classification_json` | DOMESTIC / confidence / signals |
| `consistency_json` | Meter/charge mismatch warnings |
| `canonical_bill_json` | Typed bill used by all engines |

**Solar comparison results are not persisted yet** — computed on demand per request.

---

## 14. Module completion matrix

### Module 1 — Bill Analysis ✅

| Capability | Backend | UI |
|------------|---------|-----|
| Upload / extract / batch | ✅ | ✅ |
| Required vs optional field gate | ✅ | ✅ (`*` markers) |
| Subsidy hide-unless-detected | ✅ | ✅ |
| Category from tariff (display) | ✅ | ✅ |
| Confirm + audit trail | ✅ | ✅ |
| Monthly summary message | ✅ | ✅ |
| `BillCalculator` summary | ✅ | ✅ side panel |
| Unsupported bill notice | ✅ | ✅ |
| Consumption history | ✅ | ⚠️ partial after confirm |
| Plain-language bill explain | ❌ | ❌ |

### Module 2 — Solar options compare ✅

| Capability | Backend | UI |
|------------|---------|-----|
| Prefill from confirmed bill | ✅ | ✅ |
| Individual rooftop estimate | ✅ | ✅ |
| VNM pre-screen + saving | ✅ | ✅ |
| GNM pre-screen + saving | ✅ | ✅ |
| Add extra flats / RRs | ✅ | ✅ |
| Best-option highlight | ✅ | ✅ |
| Persist comparison results | ❌ | — |
| NET vs GROSS metering compare in UI | ❌ | — |

### Other backends (not in Integrum UI)

Tariff, Gruha Jyothi, savings, appliances, metering, RAG, agent — APIs exist; no production UI tab.

---

## 15. User journey (updated)

```
Upload → needs_review → confirm → ready (Module 1)
                                    │
                                    ▼
                         Compare solar options (Module 2)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            Individual rooftop    VNM (≥2 flats)   GNM (≥2 RRs)
```

---

## 16. Tests & quality

- **114 automated tests** passing (includes Module 2: `tests/test_solar_options.py`)
- VNM engine: `tests/test_vnm_analysis.py`
- GNM engine: `tests/test_gnm_analysis.py`
- Field requirements: `tests/test_bill_field_requirements.py`
- Frontend builds (Next.js 15)

---

## 17. Sample files & live commands

| File | Description |
|------|-------------|
| `docs/samples/bescom_extract_clean.json` | Layer A — raw extraction |
| `docs/samples/bescom_api_extract_response.json` | After extract |
| `docs/samples/bescom_api_confirm_response.json` | After confirm (`ready`) |
| `docs/samples/ap_extract_partial.json` | AP bill — unsupported |

```powershell
# API
uvicorn app.main:app --reload

# Module 1
curl -X POST "http://127.0.0.1:8000/bills/extract" -F "file=@data/bes-bills/Jan2026.jpeg"

# Module 2 (after confirm → analysis_id)
curl "http://127.0.0.1:8000/bills/{analysis_id}/solar-options/prefill"
curl -X POST "http://127.0.0.1:8000/bills/{analysis_id}/solar-options" ^
  -H "Content-Type: application/json" ^
  -d "{\"plant\":{\"proposed_kwp\":5,\"roof_area_m2\":40}}"
```

Swagger: http://127.0.0.1:8000/docs

---

## 18. Recommended next steps

1. **Persist** solar comparison runs against `analysis_id`
2. **NET vs GROSS** metering compare in UI (`POST /metering/compare`)
3. **Consumption trends** chart from 3+ stored bills
4. **Plain-language bill explanation** from confirmed fields

---

## 19. Key source files (quick reference)

| Topic | Path |
|-------|------|
| Bill field requirements | `app/domain/models/bill_field_requirements.py` |
| Confirm gate | `app/domain/services/bill_confirmation_needs.py` |
| Module 1 calculator | `app/domain/services/bill_calculator.py` |
| Module 1 presenter | `app/application/services/bill_analysis_presenter.py` |
| Tariff (retail ₹) | `app/domain/engines/tariff.py` |
| VNM engine + saving | `app/domain/engines/vnm.py` |
| GNM engine + saving | `app/domain/engines/gnm.py` |
| Solar engine + saving | `app/domain/engines/solar.py` |
| Module 2 use case | `app/application/use_cases/compare_solar_options.py` |
| Bill → solar prefill | `app/application/services/bill_to_solar_inputs.py` |
| Module 2 API | `app/api/routes/solar_options.py` |
| Module 2 UI | `frontend/components/solar-options/SolarOptionsPanel.tsx` |
| VNM rules | `rules/karnataka/bescom/solar/vnm_v1.yaml` |
| GNM rules | `rules/karnataka/bescom/solar/gnm_v1.yaml` |
