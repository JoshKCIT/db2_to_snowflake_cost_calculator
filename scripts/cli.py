"""
Copyright (c) 2025 JoshKCIT

Command-line interface for Snowflake Budget Calculator
"""

import argparse, json, csv, sys
from pathlib import Path
from lib.calc import InputModel, compute

ROOT = Path(__file__).parent.parent

def load_json(p: Path):
  with p.open("r", encoding="utf-8") as f:
    return json.load(f)

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--db2-cpu-seconds", type=float, required=True)
  ap.add_argument("--batch-window-hours", type=float, required=True)
  ap.add_argument("--concurrency", type=int, default=1)
  ap.add_argument("--uncompressed-tb", type=float, required=True)
  ap.add_argument("--frequency-per-month", type=int, required=True)
  ap.add_argument("--egress-tb", type=float, default=0.0)
  ap.add_argument("--egress-route", choices=["intraRegion","interRegion","crossCloud","internet","accountTransfer"], default="intraRegion")
  ap.add_argument("--region", required=True)
  ap.add_argument("--edition", choices=["standard","enterprise","business_critical","vps"], required=True)
  ap.add_argument("--timetravel-tb", type=float, default=0.0)
  ap.add_argument("--failsafe-tb", type=float, default=0.0)
  ap.add_argument("--workload-family", default="elt_batch")
  ap.add_argument("--snowpipe-files-per-day", type=float, default=0.0)
  ap.add_argument("--snowpipe-compute-hours-per-day", type=float, default=0.0)
  ap.add_argument("--snowpipe-uncompressed-gb-per-day", type=float, default=0.0)
  ap.add_argument("--searchopt-compute-hours-per-day", type=float, default=0.0)
  ap.add_argument("--tasks-hours-per-day", type=float, default=0.0)
  ap.add_argument("--warehouse-type", choices=["standard","multi_cluster","serverless"], default="standard")
  ap.add_argument("--cluster-count", type=int, default=1)
  ap.add_argument("--out", help="Output JSON file path")
  ap.add_argument("--csv", help="Output CSV file path")
  args = ap.parse_args()

  pricing = load_json(ROOT / "config" / "pricing.json")
  rules = load_json(ROOT / "config" / "rules.json")
  calib = load_json(ROOT / "config" / "calibration.json")

  # Validate inputs
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
    print(f"WARNING: Workload family '{args.workload_family}' not found, using default '{calib['defaultFamily']}'", file=sys.stderr)

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

  res = compute(inp, pricing, rules, calib)
  print(json.dumps(res, indent=2))

  if args.out:
    Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")

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

if __name__ == "__main__":
  try:
    main()
  except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)

