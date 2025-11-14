# Snowflake Budget Calculator (Offline)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Air‑gapped** cost estimator for Db2 for z/OS→Snowflake migrations. Two entry points:
- Static browser app: double‑click `index.html` (no server).
- CLI: `python scripts/cli.py …` (Python 3.10+ stdlib only).

## Tool UI
<img width="788" height="823" alt="image" src="https://github.com/user-attachments/assets/3b415915-5d58-44b5-ab74-82a6ccb06052" />
<img width="776" height="821" alt="image" src="https://github.com/user-attachments/assets/14c8e3a9-1dd0-413a-9711-d4489c8cd1cc" />
<img width="784" height="751" alt="image" src="https://github.com/user-attachments/assets/2b184273-61d7-4c3f-809f-e3e3d8f81df9" />


## Prerequisites

**For Static Browser App:**
- Modern web browser (Chrome, Firefox, Edge, Safari - latest versions)
- No server or internet connection required (works offline)
- JavaScript enabled

**For CLI:**
- Python 3.10 or higher (check with `python --version`)
- No additional Python packages required (uses stdlib only)
- Works on Windows, macOS, and Linux

## Edit these files to change costs & rules
- `config/pricing.json` — $/credit by region+edition, storage $/TB‑mo, egress $/TB, serverless credit units.
- `config/rules.json` — credits/hour per warehouse size, Cloud Services rule.
- `config/calibration.json` — **k** values per workload family (Db2 for z/OS CPU‑sec → Snowflake XS‑sec).

> **k** = XS‑seconds on Snowflake needed to process 1 Db2 for z/OS CPU‑second for a given workload family.

## Quick start (static app)

**Best for:** Interactive use, visual interface, quick estimates

1. **Download or clone** this repository
2. **Review configuration** files under `config/` (see [Configuration](#edit-these-files-to-change-costs--rules) section)
3. **Open `index.html`** from disk (double-click or right-click → Open with → Browser)
4. **Enter Db2 for z/OS metrics** in the "DBA Inputs" section
5. **Configure Snowflake settings** in the "Solution Architect Inputs" section
6. **Click Calculate** to see results
7. **Use Export** button to save results as JSON or CSV

**Note:** The static app uses `config/*.js` (window variables) so it works from `file://`. Keep `*.json` and `*.js` in sync using the Configuration tab in the web app.

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
  --searchopt-compute-hours-per-day 0.5 \
  --tasks-hours-per-day 1 \
  --out out.json --csv out.csv
```

## ⚠️ Important: Calibrate Before Use

**All pricing and calibration values in `config/` are placeholders.** Before using this tool for production estimates:

1. **Update pricing**: Replace values in `config/pricing.json` with current Snowflake pricing from your account representative or [Snowflake Pricing Guide](https://www.snowflake.com/pricing/)
2. **Calibrate k-values**: Follow the [Calibration Guide](docs/calibration_guide.html) to determine accurate k-factors for your workloads
3. **Verify warehouse rules**: Confirm `config/rules.json` matches current Snowflake warehouse specifications

**Without proper calibration, estimates can be inaccurate by 50% or more.**

**⚠️ High Availability/Disaster Recovery (HA/DR) Not Included:** This calculator estimates costs for primary production workloads only. HA/DR scenarios require additional cost estimation for standby systems, replication compute, cross-region failover, and related infrastructure. These costs should be calculated separately based on your specific HA/DR requirements.

## Common Use Cases

### Scenario 1: Initial Migration Estimate
**Goal:** Get a rough budget estimate for migrating Db2 for z/OS workloads to Snowflake
- Use [default k-values](docs/calibration_guide.html#origin_of_default_k_values) as starting point
- Run multiple scenarios with different warehouse sizes
- Compare costs across regions/editions

### Scenario 2: Refined Cost Analysis
**Goal:** Accurate cost projection after pilot migration
- Calibrate k-values using pilot workload data
- Update pricing with actual Snowflake contract rates
- Model different concurrency and batch window scenarios

### Scenario 3: What-If Analysis
**Goal:** Optimize costs by testing different configurations
- Compare Standard vs Enterprise editions
- Test multi-cluster vs single-cluster warehouses
- Evaluate impact of different batch windows
- Model serverless features (Snowpipe, Tasks) vs traditional ETL

## Limitations

This calculator provides estimates for **primary production workloads only**. The following are **not included** and should be estimated separately:

- **High Availability (HA)**: Standby systems, active-active configurations, or failover compute resources
- **Disaster Recovery (DR)**: Cross-region replication, DR site compute, backup/restore infrastructure
- **Development/Test Environments**: Non-production environments require separate cost estimates
- **Data Replication**: Cross-region or cross-cloud replication costs beyond basic egress
- **Additional Services**: Third-party tools, monitoring, security services, or other Snowflake ecosystem costs

For HA/DR scenarios, consult with your Snowflake account representative to estimate additional infrastructure costs based on your specific requirements (RTO/RPO targets, replication methods, failover configurations, etc.).

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

*(See [Calculation Logic tab](index.html#calculation-logic-tab) in the web app for detailed explanations)*

**Note:** These formulas are implemented identically in both JavaScript (web app) and Python (CLI) for consistency.

All numbers in `config/` are placeholders. Replace with your authoritative tables.

## Troubleshooting

### Static App Issues

**Problem:** Calculator doesn't load or shows errors
- **Solution:** Check browser console (F12) for JavaScript errors
- Ensure all files are in the correct directory structure
- Try a different browser if issues persist

**Problem:** Configuration changes don't appear
- **Solution:** Hard refresh (Ctrl+F5 or Cmd+Shift+R)
- Verify `config/*.js` files match `config/*.json` files

### CLI Issues

**Problem:** `python: command not found`
- **Solution:** Install Python 3.10+ or use `python3` instead of `python`

**Problem:** `FileNotFoundError` for config files
- **Solution:** Run CLI from project root directory, or use absolute paths

**Problem:** Invalid region or edition error
- **Solution:** Check `config/pricing.json` for available regions/editions
- Use exact region identifier (e.g., `aws-us-east-1`, not `us-east-1`)

### Calculation Issues

**Problem:** Results seem too high/low
- **Solution:** Verify k-values are calibrated for your workload
- Check that pricing values match your Snowflake contract
- Review [Calibration Guide](docs/calibration_guide.html) for k-value guidance

**Problem:** Warehouse size selection seems wrong
- **Solution:** Verify batch window hours matches your SLA requirements
- Check concurrency value (should match actual parallel job count)

## Documentation

### Key Concepts Explained

Understanding these concepts is essential for accurate cost estimates:

- **[k-factor (Calibration Factor)](docs/calibration_guide.html#what-is-k-factor-and-why-do-we-need-it)**: Why performance differs between Db2 for z/OS and Snowflake, and how to calibrate k-values for your workloads
- **[Warehouse Size Factors](docs/calibration_guide.html#understanding-warehouse-size-factors)**: How Snowflake warehouses scale (XS, S, M, L, XL, etc.) and the cost vs speed trade-off
- **[Cloud Services Waiver](index.html#step-5-calculate-cloud-services-credits)**: The 10% waiver rule and what Cloud Services covers
- **[Multi-Cluster Warehouses](docs/snowflake_architects_how_to_use.html#multi-cluster-warehouse)**: Horizontal scaling for high-concurrency workloads
- **[Serverless Features](docs/snowflake_architects_how_to_use.html#serverless-features)**: Snowpipe, Search Optimization, and Tasks pricing models
- **[Storage Types](docs/snowflake_architects_how_to_use.html#storage-types)**: Regular storage, Time Travel, and Fail-safe storage
- **[Egress Routes](docs/snowflake_architects_how_to_use.html#egress-route)**: Data transfer pricing and cost optimization tips
- **[Credits vs Dollars](index.html#step-8-calculate-compute-cost)**: How Snowflake's credit-based billing works

### User Guides

- **[Calibration Guide](docs/calibration_guide.html)**: Step-by-step guide to calibrating k-values for your workloads
- **[Db2 DBA Guide](docs/db2_dba_how_to_use.html)**: Where to find Db2 for z/OS metrics (SMF records, catalog tables)
- **[Snowflake Architect Guide](docs/snowflake_architects_how_to_use.html)**: Snowflake configuration details and where to find metrics
- **[Calculation Logic](index.html#calculation-logic-tab)**: Detailed explanation of the 10-step calculation methodology

### Quick Reference

- **Calculation Formula**: See [Core model](#core-model) section above
- **Configuration Files**: See [Edit these files](#edit-these-files-to-change-costs--rules) section above
- **Example Calculations**: See [Calculation Logic tab](index.html#calculation-logic-tab) in the web app

### External Resources

- **[Snowflake Pricing Guide](https://www.snowflake.com/pricing/)**: Official Snowflake pricing documentation
- **[Snowflake Documentation](https://docs.snowflake.com/)**: Complete Snowflake technical documentation
- **[Snowflake Cost Management](https://docs.snowflake.com/en/user-guide/cost-understanding-overview)**: Understanding Snowflake costs and credits

## Frequently Asked Questions

**Q: Do I need a Snowflake account to use this tool?**  
A: No. This tool works offline and doesn't require a Snowflake account. However, you'll need accurate pricing data from Snowflake for production estimates.

**Q: How accurate are the estimates?**  
A: Accuracy depends on proper calibration of k-values and current pricing data. With calibrated k-values and accurate pricing, estimates are typically within 10-15% of actual costs.

**Q: Can I use this for other database migrations (Oracle, SQL Server, etc.)?**  
A: No. This tool is specifically designed for Db2 for z/OS to Snowflake migrations. The k-factor calibration is based on Db2 for z/OS CPU metrics.

**Q: How often should I update pricing?**  
A: Snowflake pricing changes infrequently, but check annually or when renewing contracts. Always verify pricing with your Snowflake account representative.

**Q: What if my workload doesn't match the predefined families?**  
A: You can add custom workload families in `config/calibration.json`. Follow the [Calibration Guide](docs/calibration_guide.html) to determine appropriate k-values.

**Q: Can I automate calculations?**  
A: Yes! Use the CLI (`scripts/cli.py`) for automation. It can be integrated into scripts, CI/CD pipelines, or other tools.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support & Issues

- **Found a bug?** Open an issue on [GitHub](https://github.com/JoshKCIT/db2_to_snowflake_cost_calculator/issues)
- **Have a question?** Check the [Documentation](#documentation) section or open a discussion
- **Need help with calibration?** See the [Calibration Guide](docs/calibration_guide.html)
- **Want to contribute?** See [Contributing](#contributing) section below

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

