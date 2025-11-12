"""
Copyright (c) 2025 JoshKCIT

Command-line interface for Snowflake Budget Calculator

This module provides a command-line interface (CLI) for running cost calculations
from the terminal or scripts. It's useful for:
- Automation and scripting (CI/CD pipelines, batch processing)
- Integration with other tools (spreadsheets, monitoring systems)
- Headless environments (servers without GUI)

The CLI reads configuration from config/*.json files and accepts all calculation
parameters as command-line arguments. Results can be output as JSON (stdout or file)
or CSV (file).

Usage Example:
    python scripts/cli.py \\
      --db2-cpu-seconds 72000 \\
      --batch-window-hours 4 \\
      --concurrency 2 \\
      --uncompressed-tb 30 \\
      --frequency-per-month 30 \\
      --region aws-us-east-1 \\
      --edition enterprise \\
      --workload-family elt_batch \\
      --out result.json \\
      --csv result.csv
"""

import argparse, json, csv, sys
from pathlib import Path
from lib.calc import InputModel, compute

# Root directory of the project (parent of scripts/)
# Used to locate config files relative to project root
ROOT = Path(__file__).parent.parent

def load_json(p: Path):
  """
  Loads a JSON file and returns the parsed object.
  
  This is a utility function for loading configuration files.
  Uses UTF-8 encoding to handle international characters correctly.
  
  Args:
    p: Path object pointing to the JSON file
  
  Returns:
    Parsed JSON object (dict, list, etc.)
  
  Raises:
    FileNotFoundError: If the file doesn't exist
    json.JSONDecodeError: If the file contains invalid JSON
  """
  with p.open("r", encoding="utf-8") as f:
    return json.load(f)

def main():
  """
  Main CLI entry point: parses arguments, validates inputs, runs calculation, outputs results.
  
  This function:
  1. Parses command-line arguments using argparse
  2. Loads configuration files (pricing.json, rules.json, calibration.json)
  3. Validates inputs (region exists, edition available, etc.)
  4. Creates InputModel and runs calculation
  5. Outputs results as JSON (stdout/file) and/or CSV (file)
  
  Exit codes:
    - 0: Success
    - 1: Error (invalid arguments, missing config, calculation error)
  """
  # ============================================================================
  # ARGUMENT PARSING
  # ============================================================================
  # Define all command-line arguments using argparse
  # Required arguments: db2-cpu-seconds, batch-window-hours, uncompressed-tb, frequency-per-month, region, edition
  # Optional arguments: all others have defaults (0.0, 1, "elt_batch", etc.)
  
  ap = argparse.ArgumentParser(
    description="Calculate Snowflake costs from Db2 for z/OS metrics",
    formatter_class=argparse.RawDescriptionHelpFormatter
  )
  
  # Db2 for z/OS DBA Inputs
  ap.add_argument("--db2-cpu-seconds", type=float, required=True,
                  help="Db2 for z/OS CPU seconds consumed per day")
  ap.add_argument("--batch-window-hours", type=float, required=True,
                  help="Batch window constraint in hours (SLA requirement)")
  ap.add_argument("--concurrency", type=int, default=1,
                  help="Number of concurrent jobs running simultaneously (default: 1)")
  ap.add_argument("--uncompressed-tb", type=float, required=True,
                  help="Uncompressed data size in TB (for storage costs)")
  ap.add_argument("--frequency-per-month", type=int, required=True,
                  help="How many times per month the workload runs")
  ap.add_argument("--workload-family", default="elt_batch",
                  help="Workload family for k-factor selection: elt_batch, reporting, or cdc (default: elt_batch)")
  
  # Snowflake Solution Architect Inputs
  ap.add_argument("--region", required=True,
                  help="Snowflake region code (e.g., aws-us-east-1)")
  ap.add_argument("--edition", choices=["standard","enterprise","business_critical","vps"], required=True,
                  help="Snowflake edition: standard, enterprise, business_critical, or vps")
  ap.add_argument("--egress-tb", type=float, default=0.0,
                  help="Data egress volume in TB/month (default: 0.0)")
  ap.add_argument("--egress-route", choices=["intraRegion","interRegion","crossCloud","internet","accountTransfer"],
                  default="intraRegion",
                  help="Egress route type (default: intraRegion)")
  ap.add_argument("--timetravel-tb", type=float, default=0.0,
                  help="Time Travel storage in TB/month (default: 0.0)")
  ap.add_argument("--failsafe-tb", type=float, default=0.0,
                  help="Fail-safe storage in TB/month (default: 0.0)")
  
  # Serverless Features
  ap.add_argument("--snowpipe-files-per-day", type=float, default=0.0,
                  help="Snowpipe files processed per day (Standard/Enterprise only, default: 0.0)")
  ap.add_argument("--snowpipe-compute-hours-per-day", type=float, default=0.0,
                  help="Snowpipe compute hours per day (Standard/Enterprise only, default: 0.0)")
  ap.add_argument("--snowpipe-uncompressed-gb-per-day", type=float, default=0.0,
                  help="Snowpipe data volume in GB/day (Business-Critical/VPS only, default: 0.0)")
  ap.add_argument("--searchopt-compute-hours-per-day", type=float, default=0.0,
                  help="Search Optimization compute hours per day (default: 0.0)")
  ap.add_argument("--tasks-hours-per-day", type=float, default=0.0,
                  help="Serverless Tasks hours per day (default: 0.0)")
  
  # Warehouse Configuration
  ap.add_argument("--warehouse-type", choices=["standard","multi_cluster","serverless"], default="standard",
                  help="Warehouse type: standard, multi_cluster, or serverless (default: standard)")
  ap.add_argument("--cluster-count", type=int, default=1,
                  help="Number of clusters (for multi-cluster warehouses, default: 1)")
  
  # Output Options
  ap.add_argument("--out", help="Output JSON file path (if not specified, prints to stdout)")
  ap.add_argument("--csv", help="Output CSV file path (optional)")
  
  args = ap.parse_args()

  # ============================================================================
  # LOAD CONFIGURATION FILES
  # ============================================================================
  # Load pricing, rules, and calibration configuration from JSON files
  # These files define Snowflake pricing, warehouse rules, and k-factors
  
  pricing = load_json(ROOT / "config" / "pricing.json")
  rules = load_json(ROOT / "config" / "rules.json")
  calib = load_json(ROOT / "config" / "calibration.json")

  # ============================================================================
  # VALIDATE INPUTS
  # ============================================================================
  # Check that region exists in pricing config and edition is available
  # This prevents runtime errors and provides clear error messages
  if args.region not in pricing["regions"]:
    print(f"ERROR: Region '{args.region}' not found in pricing config", file=sys.stderr)
    print(f"Available regions: {', '.join(pricing['regions'].keys())}", file=sys.stderr)
    sys.exit(1)
  
  if args.edition not in pricing["regions"][args.region]["pricePerCredit"]:
    if args.edition == "vps":
      # VPS fallback handled in calc.py
      pass
    else:
      print(f"ERROR: Edition '{args.edition}' not found for region '{args.region}'", file=sys.stderr)
      print(f"Available editions: {', '.join(pricing['regions'][args.region]['pricePerCredit'].keys())}", file=sys.stderr)
      sys.exit(1)
  
  if args.workload_family not in calib["workloadFamilies"]:
    # Warn but don't fail - calc.py will use default family
    print(f"WARNING: Workload family '{args.workload_family}' not found, using default '{calib['defaultFamily']}'", file=sys.stderr)

  # ============================================================================
  # CREATE INPUT MODEL AND RUN CALCULATION
  # ============================================================================
  # Convert command-line arguments to InputModel dataclass
  # Then call the calculation engine (same logic as web UI)
  
  inp = InputModel(
    db2_cpu_seconds_per_day=args.db2_cpu_seconds,
    batch_window_hours=args.batch_window_hours,
    concurrency=args.concurrency,
    uncompressed_tb_at_rest=args.uncompressed_tb,
    frequency_per_month=args.frequency_per_month,
    egress_tb=args.egress_tb,
    egress_route=args.egress_route,
    region=args.region,
    edition=args.edition,
    family=args.workload_family,
    snowpipe_files_per_day=args.snowpipe_files_per_day,
    snowpipe_compute_hours_per_day=args.snowpipe_compute_hours_per_day,
    snowpipe_uncompressed_gb_per_day=args.snowpipe_uncompressed_gb_per_day,
    searchopt_compute_hours_per_day=args.searchopt_compute_hours_per_day,
    tasks_hours_per_day=args.tasks_hours_per_day,
    time_travel_tb=args.timetravel_tb,
    failsafe_tb=args.failsafe_tb,
    warehouse_type=args.warehouse_type,
    cluster_count=args.cluster_count
  )

  # Run the calculation using the core calculation engine
  # This performs all 10 calculation steps and returns comprehensive results
  res = compute(inp, pricing, rules, calib)
  
  # ============================================================================
  # OUTPUT RESULTS
  # ============================================================================
  # Output results as JSON (always to stdout, optionally to file)
  # Optionally output key results as CSV for spreadsheet import
  
  # Always print JSON to stdout (useful for piping to other tools)
  print(json.dumps(res, indent=2))

  # Save JSON to file if --out specified
  if args.out:
    Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")

  # Save CSV to file if --csv specified
  # CSV format: key-value pairs, one per line (easy to import into Excel/Sheets)
  if args.csv:
    rows = [
      ["size", res["selection"]["size"]],
      ["whHoursDay", res["selection"]["whHoursDay"]],
      ["whCreditsDay", res["daily"]["whCreditsDay"]],
      ["csCreditsDay", res["daily"]["csCreditsDay"]],
      ["serverlessCreditsDay", res["daily"]["serverlessCreditsDay"]],
      ["monthlyCredits", res["monthly"]["credits"]],
      ["dollarsCompute", res["monthly"]["dollarsCompute"]],
      ["dollarsStorage", res["monthly"]["dollarsStorage"]],
      ["dollarsTransfer", res["monthly"]["dollarsTransfer"]],
      ["grandTotal", res["monthly"]["grandTotal"]],
    ]
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
      w = csv.writer(f); w.writerows(rows)

# ============================================================================
# ENTRY POINT
# ============================================================================
# Run main() when script is executed directly
# Catch all exceptions and exit with error code 1 on failure

if __name__ == "__main__":
  try:
    main()
  except Exception as e:
    # Print error to stderr (not stdout) so JSON output isn't corrupted
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

