# Snowflake Service Consumption — Cursor‑Ready (Normalized)
**Effective date:** 2025‑11‑10 • **Scope:** Core rules and constants most relevant to warehouse credits, Cloud Services, storage, data transfer, and selected serverless features. Use the JSON blocks as inputs to your offline calculator configs.

> Source: Snowflake Service Consumption Table (authoritative legal + pricing reference). Replace placeholder regions/tables here with the full set you operate in. (Do not rely on this file as a substitute for the original.)

---

## 1) Core rules (for `config/rules.json`)

```json
{
  "warehouseCreditsPerHour": {
    "XS": 1.35, "S": 2.7, "M": 5.4, "L": 10.8,
    "XL": 21.6, "2XL": 43.2, "3XL": 86.4, "4XL": 172.8
  },
  "sizeFactor": { "XS":1, "S":2, "M":4, "L":8, "XL":16, "2XL":32, "3XL":64, "4XL":128 },
  "cloudServices": {
    "capCreditsPerHour": 4.4,
    "waiverPctOfDailyWH": 0.10
  },
  "notes": [
    "Gen2 Virtual Warehouses on AWS. Credits per hour are charged while running (per‑second billing, 60‑second minimum on start/resume).",
    "Cloud Services: charged at 4.4 credits/hour; daily Cloud Services charge is waived if <= 10% of that day’s WH credits."
  ]
}
```

**Interpretation for calculators**
- **WH credits/day** = `warehouse_hours × credits_per_hour(size)`
- **Cloud Services credits/day** = `min(4.4 × warehouse_hours, 0.10 × WH_credits_day)`
- Multi‑cluster: total WH credits multiply by number of active clusters (if used).

---

## 2) On‑demand $/credit and storage ($/TB‑mo) — AWS examples (for `config/pricing.json`)

> Keep region names consistent with your org’s conventions. Add more regions as needed.

```json
{
  "regions": {
    "aws-us-east-1": {
      "pricePerCredit": { "standard": 2.00, "enterprise": 3.00, "business_critical": 4.00 },
      "storagePerTBMonth": 23.00,
      "egressPerTB": { "intraRegion": 0.00, "interRegion": 20.00, "internet": 90.00 }
    },
    "aws-us-west-2": {
      "pricePerCredit": { "standard": 2.00, "enterprise": 3.00, "business_critical": 4.00 },
      "storagePerTBMonth": 23.00,
      "egressPerTB": { "intraRegion": 0.00, "interRegion": 20.00, "internet": 90.00 }
    },
    "aws-eu-west-1": {
      "pricePerCredit": { "standard": 2.60, "enterprise": 3.90, "business_critical": 5.20 },
      "storagePerTBMonth": 23.00,
      "egressPerTB": { "intraRegion": 0.00, "interRegion": 20.00, "internet": 90.00 }
    }
  }
}
```

**Notes**
- Values above come from the On‑Demand Credit Pricing (Table 2) and Standard Storage Pricing (Table 3(a)).
- Use your exact operating regions. Government and outlier regions have different prices.


---

## 3) Serverless features (initial subset for calculators)

Use these for optional add‑ons (Snowpipe, Search Optimization, Tasks). Others exist; add only what you need.

```json
{
  "serverless": {
    "snowpipe": {
      "multiplierCompute": 1.25,
      "multiplierCloudServices": 0,
      "unitCharge": { "kind": "files", "rateCreditsPer1000": 0.06 },
      "notes": "Standard/Enterprise editions. Business‑Critical/VPS use per‑GB unit charge."
    },
    "snowpipeBCVPS": {
      "multiplierCompute": 0,
      "multiplierCloudServices": 0,
      "unitCharge": { "kind": "gb_uncompressed", "rateCreditsPerGB": 0.0037 }
    },
    "searchOptimization": {
      "multiplierCompute": 2,
      "multiplierCloudServices": 1,
      "unitCharge": null
    },
    "serverlessTasks": {
      "multiplierCompute": 0.9,
      "multiplierCloudServices": 1,
      "unitCharge": null
    }
  }
}
```

**Calculator handling**
- **Snowpipe (Std/Ent)** daily credits = `(files_ingested/1000)×0.06 + compute_hours×1.25` (Cloud Services multiplier 0 for the compute‑hour piece).
- **Snowpipe (BC/VPS)** daily credits = `uncompressed_GB_ingested × 0.0037`.
- **Search Optimization** adds both compute and Cloud Services multipliers to its maintenance compute time.
- **Serverless Tasks** credits = `task_runtime_hours × 0.9` (Cloud Services charged with multiplier 1).

---

## 4) Data transfer (egress) — AWS (for `config/pricing.json`)

Most calculators only need coarse routes. Start with these and expand if you model SPCS or Gov clouds:

```json
{
  "egressDefaults": {
    "aws": { "intraRegion": 0.00, "interRegion": 20.00, "internet": 90.00 }
  }
}
```

**Notes**
- SPCS Data Transfer has a daily adjustment vs SPCS Compute (see doc); model separately if you use SPCS.
- Some APAC or special regions have higher internet/inter‑region rates.

---

## 5) Example: roll‑up of a job (pseudo‑formula)

```
xs_hours = (db2_cpu_seconds_per_day × k) / 3600
size = smallest s where (xs_hours × concurrency) / sizeFactor[s] ≤ batch_window_hours
wh_hours_day = (xs_hours × concurrency) / sizeFactor[size]
wh_credits_day = wh_hours_day × credits_per_hour[size]
cs_credits_day = min(4.4 × wh_hours_day, 0.10 × wh_credits_day)

serverless_credits_day = snowpipe + search_optimization + tasks (as configured)
monthly_credits = (wh_credits_day + cs_credits_day + serverless_credits_day) × runs_per_month
total_monthly_credits = monthly_credits + (search_opt_credits_monthly_if_unit_based)
monthly_dollars = total_monthly_credits × pricePerCredit(region, edition)

storage_dollars = tb_at_rest × storagePerTBMonth(region)
transfer_dollars = egressTB × egressPerTB(route)
grand_total = monthly_dollars + storage_dollars + transfer_dollars
```

---

## 6) What to paste where

- Paste **§1** into `config/rules.json` (or merge into your existing rules).
- Merge **§2** into `config/pricing.json` (add/adjust regions).
- Paste **§3** under `serverless` in `config/pricing.json` or keep a separate `serverless.json`.
- Use **§4** if you want a global default for egress routing.
- Keep this entire Markdown next to your repo (`docs/snowflake_consumption_cursor_ready.md`) so Cursor/Copilot can ground completions.
