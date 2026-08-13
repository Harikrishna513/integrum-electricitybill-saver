# Karnataka rooftop / DSPV — Net Metering vs Gross Metering (digest)

> Companion digest for RAG. Confirm against KERC SRTPV / DSPV orders and consumer PPA.

## Net Metering (individual)
- Bi-directional meter with import and export registers.
- If import > export: consumer pays retail tariff for **net import**.
- If export > import: DISCOM pays / credits **net export** at PPA / generic solar tariff.
- Fixed charges and statutory levies may still apply even when net import is zero.

## Gross Metering
- All generation sold to DISCOM at solar tariff.
- All consumption billed at full retail tariff (no unit-for-unit retail offset).

## Relationship to VNM / GNM
- Individual net / gross: one connection, plant on premises.
- VNM: one plant, many consumers (same category), declared share %.
- GNM: one consumer, many RRs (same name + category), priority order + host 20% rule.

## App endpoints
- `/metering/concepts`, `/metering/settle`, `/metering/compare`
- `/vnm/analyze`, `/gnm/analyze`
- `/rag/search` for official-document snippets
