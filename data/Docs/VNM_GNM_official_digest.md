# BESCOM / KERC — Virtual Net Metering (VNM) & Group Net Metering (GNM)

> Official-source digest for BESCOM Bill Saver AI RAG.
> Primary references:
> - Common SOP VNM & GNM (BESCOM, dated 12.05.2026)
> - KERC tariff order introducing VNM/GNM (09.07.2025)
> - Local corpus: `data/Docs/KSEC regulations.pdf`
>
> This file is a structured digest for retrieval. Always confirm against the
> latest official BESCOM SRTPV / KERC PDFs before production claims.

## Virtual Net Metering (VNM)

### Definition
Energy generated from a solar plant (roof or ground, with or without battery)
within the distribution licensee area is exported to the grid. Credits are
allocated to **more than one** electricity service connection of participating
consumers belonging to the **same consumer category** within the same licensee area.

### Eligible consumers (VNM)
- Domestic consumers
- Group housing societies
- Charitable institutions / organisations
- Government buildings including schools
- Buildings belonging to local authorities

### Participating consumers
A group of **two or more** consumers from the **same consumer category**.

### Procurement ratio (shares)
Each participating consumer declares a **share (%)** of plant generation.
Billing uses the declared shares in the application / PPA.
Shares may be changed **once at the beginning of a financial year** with
**two months' advance notice**.

### Plant size (VNM)
- **Minimum:** 5 kW
- **Maximum:** combined sanctioned load / contract demand of all participating consumers

### Billing (VNM) — practical summary
1. Monthly billing cycle aligned with BESCOM practices.
2. Generation meter and all participant meters read on the **same reading date**.
3. Total solar generation is **apportioned** by declared procurement shares.
4. Each participant is billed independently after adjusting apportioned solar against consumption.
5. Net import after adjustment → billed at **retail tariff**.
6. Net export surplus after adjustment → purchased at **75% of the applicable generic tariff**
   for ground-mounted / distributed solar (as determined by KERC for the control period).
7. Open-access charges may apply when generation and consumption are on **different 11 kV feeders**;
   same DT / same feeder may be exempt — confirm current SOP.

### Technical feasibility
BESCOM officers assess scenarios such as:
- Same distribution transformer (DT)
- Same 11 kV feeder, different DTs
- Same substation, multiple feeders
- Multiple substations (joint assessment)

**This application only pre-screens. It never approves technical feasibility or PPA.**

## Group Net Metering (GNM)

### Definition
Surplus energy from a solar plant at **one of a consumer's installations**
is exported and adjusted against **other installations of the same consumer name
and same category** within the licensee area.

### Eligible consumers (GNM)
Consumers of **all categories** may install under GNM (broader than VNM).

### Participating connections
Same consumer name + same tariff category + same licensee area.
Minimum practical case: **two or more installations**.

### Priority order
Consumer declares **priority** of installations for credit allocation in the PPA.
Priority may change once at the beginning of each FY with two months' notice.

### Plant size (GNM)
- **Minimum:** 5 kW
- **Maximum:** combined sanctioned load / contract demand of the consumer's installations

### Host / source connection 20% rule
The service connection where the plant is located shall consume at least
**20% of total generation** in a billing month.
Unused portion of that 20% reserve is treated as **lapsed energy**
(not transferred to other RRs).

### Billing (GNM) — practical summary
1. Monthly cycle; synchronized meter readings.
2. Credits applied by **priority waterfall** after host reserved band.
3. Residual retail billed at retail tariff.
4. Surplus net export valued at **75% of generic tariff** (same family as VNM).
5. Open-access rules similar to VNM based on feeder topology.

## Product rules for this app
- Engines: `VNMAnalysisEngine`, `GNMAnalysisEngine` (preliminary analysis only).
- Never say "approved".
- Money / residual retail uses `TariffEngine` for DOMESTIC v1.
- Excess purchase rate uses versioned YAML bootstrap generic tariff × 0.75.
- Official next step: BESCOM SRTPV / DSPV portal + PPA.

## Official portals
- https://srtpv.bescom.org/
- Common SOP PDF: https://srtpv.bescom.org/SRTPV/document/Common%20SOP%20VNM_GNM%2012.05.2026.pdf
