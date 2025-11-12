# Snowflake Budget Calculator (Offline)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Air‑gapped cost estimator for Db2 for z/OS→Snowflake migrations. Two entry points:
- Static browser app: double‑click `index.html` (no server).
- CLI: `python scripts/cli.py …` (Python 3.10+ stdlib only).

## Edit these files to change costs & rules
- `config/pricing.json` — $/credit by region+edition, storage $/TB‑mo, egress $/TB, serverless credit units.
- `config/rules.json` — credits/hour per warehouse size, Cloud Services rule.
- `config/calibration.json` — **k** values per workload family (Db2 for z/OS CPU‑sec → Snowflake XS‑sec).

> **k** = XS‑seconds on Snowflake needed to process 1 Db2 for z/OS CPU‑second for a given workload family.

## Quick start (static app)
1) Review or edit files under `config/`.
2) Open `index.html` from disk.
3) Enter Db2 for z/OS metrics. Click **Calculate**. Use **Export** for JSON/CSV.

The static app uses `config/*.js` (window variables) so it works from `file://`. Keep `*.json` and `*.js` in sync.

## Quick start (CLI)
```bash
python scripts/cli.py \
  --db2-cpu-seconds 72000 \
  --batch-window-hours 4 \
  --concurrency 2 \
  --uncompressed-tb 30 \
  --frequency-per-month 30 \
  --egress-tb 2 --egress-route interRegion \
  --region aws-us-east-1 --edition enterprise \
  --workload-family elt_batch \
  --snowpipe-files-per-day 5000 \
  --searchopt-tb 2 \
  --tasks-hours-per-day 1 \
  --out out.json --csv out.csv
```

## Core model
1) `xs_hours = (db2_cpu_seconds_per_day × k) / 3600` (where db2_cpu_seconds_per_day is Db2 for z/OS CPU seconds)  
2) Pick smallest size `s` where `(xs_hours × max(1, concurrency)) / sizeFactor[s] ≤ batch_window_hours`  
3) `wh_credits_day = (xs_hours × max(1, concurrency) / sizeFactor[s]) × creditsPerHour[s]`  
4) `cs_credits_day = min(cloud.capCreditsPerHour × wh_hours_day, 0.10 × wh_credits_day)`  
5) `monthly_credits = (wh + cs + serverless_daily) × frequency_per_month`  
6) `total_monthly_credits = monthly_credits + searchOptimizationMonthlyCredits`  
7) `monthly_dollars = total_monthly_credits × $/credit(region, edition)`  
8) `storage_monthly = TB × storagePerTBMonth(region)`  
9) `transfer_monthly = TB × egressPerTB(route)`  
10) `grand_total = monthly_dollars + storage_monthly + transfer_monthly`

All numbers in `config/` are placeholders. Replace with your authoritative tables.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**JoshKCIT**

- GitHub: [@JoshKCIT](https://github.com/JoshKCIT)
- Repository: [db2_to_snowflake_cost_calculator](https://github.com/JoshKCIT/db2_to_snowflake_cost_calculator)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

