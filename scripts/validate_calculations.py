#!/usr/bin/env python3
"""
Copyright (c) 2025 JoshKCIT

Comprehensive validation script for DB2 to Snowflake cost calculator.
Verifies calculation logic correctness and consistency.

Usage: python validate_calculations.py
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from lib.calc import InputModel, compute

def load_configs():
    """Load all configuration files."""
    pricing = json.load((ROOT / "config" / "pricing.json").open())
    rules = json.load((ROOT / "config" / "rules.json").open())
    calib = json.load((ROOT / "config" / "calibration.json").open())
    return pricing, rules, calib

def manual_calculation_verification(inp, pricing, rules, calib, result):
    """Manually verify calculations step by step."""
    errors = []
    
    # Step 1: Get K value
    wf = inp.family if inp.family in calib["workloadFamilies"] else calib["defaultFamily"]
    k = calib["workloadFamilies"][wf]["k_xs_seconds_per_db2_cpu_second"]
    
    # Step 2: Calculate XS hours
    xs_hours_expected = (inp.db2_cpu_seconds_per_day * k) / 3600.0
    xs_hours_actual = result["daily"]["xsHours"]
    if abs(xs_hours_expected - xs_hours_actual) > 0.001:
        errors.append(f"XS hours mismatch: expected {xs_hours_expected}, got {xs_hours_actual}")
    
    # Step 3: Size selection
    need = xs_hours_expected * max(1, inp.concurrency)
    size = result["selection"]["size"]
    size_factor = rules["sizeFactor"][size]
    wh_hours_base = need / size_factor
    
    # Multi-cluster support: multiply hours and credits by cluster count
    cluster_count = getattr(inp, 'cluster_count', 1)
    warehouse_type = getattr(inp, 'warehouse_type', 'standard')
    if warehouse_type == "multi_cluster":
        wh_hours_expected = wh_hours_base * cluster_count
    else:
        wh_hours_expected = wh_hours_base
    
    wh_hours_actual = result["selection"]["whHoursDay"]
    if abs(wh_hours_expected - wh_hours_actual) > 0.001:
        errors.append(f"Warehouse hours mismatch: expected {wh_hours_expected}, got {wh_hours_actual}")
    
    # Verify size selection is correct (check base hours, not multiplied)
    if wh_hours_base > inp.batch_window_hours:
        errors.append(f"Selected size {size} requires {wh_hours_base}h but window is {inp.batch_window_hours}h")
    
    # Step 4: Warehouse credits (account for multi-cluster)
    credits_per_hour = rules["warehouseCreditsPerHour"][size]
    wh_credits_base = wh_hours_base * credits_per_hour
    if warehouse_type == "multi_cluster":
        wh_credits_expected = wh_credits_base * cluster_count
    else:
        wh_credits_expected = wh_credits_base
    wh_credits_actual = result["daily"]["whCreditsDay"]
    if abs(wh_credits_expected - wh_credits_actual) > 0.001:
        errors.append(f"Warehouse credits mismatch: expected {wh_credits_expected}, got {wh_credits_actual}")
    
    # Step 5: Cloud Services credits (use adjusted wh_hours_expected for multi-cluster)
    cs_cap = rules["cloudServices"]["capCreditsPerHour"] * wh_hours_expected
    waiver_pct = rules["cloudServices"].get("waiverPctOfDailyWH", 0.10)  # Use configurable value
    cs_tenpct = waiver_pct * wh_credits_expected
    cs_credits_expected = min(cs_cap, cs_tenpct)
    cs_credits_actual = result["daily"]["csCreditsDay"]
    if abs(cs_credits_expected - cs_credits_actual) > 0.001:
        errors.append(f"Cloud Services credits mismatch: expected {cs_credits_expected}, got {cs_credits_actual}")
    
    # Step 6: Serverless credits (edition-specific Snowpipe, Search Optimization, Tasks)
    is_bc_vps = inp.edition == "business_critical" or inp.edition == "vps"
    snowpipe_credits_day = 0.0
    
    if is_bc_vps:
        # Business-Critical/VPS: per-GB model
        snowpipe_config = pricing["serverless"].get("snowpipe", {}).get("businessCriticalVPS", {})
        rate_per_gb = snowpipe_config.get("rateCreditsPerGB", 0.0037)
        snowpipe_credits_day = (inp.snowpipe_uncompressed_gb_per_day or 0.0) * rate_per_gb
    else:
        # Standard/Enterprise: per-file + compute multiplier
        snowpipe_config = pricing["serverless"].get("snowpipe", {}).get("standardEnterprise", {})
        rate_per_1000 = snowpipe_config.get("rateCreditsPer1000Files", 0.06)
        compute_multiplier = snowpipe_config.get("multiplierCompute", 1.25)
        file_credits = (inp.snowpipe_files_per_day / 1000.0) * rate_per_1000
        compute_credits = (inp.snowpipe_compute_hours_per_day or 0.0) * compute_multiplier
        snowpipe_credits_day = file_credits + compute_credits
    
    # Search Optimization: compute multipliers (daily)
    searchopt_config = pricing["serverless"].get("searchOptimization", {})
    searchopt_compute_multiplier = searchopt_config.get("multiplierCompute", 2)
    searchopt_cs_multiplier = searchopt_config.get("multiplierCloudServices", 1)
    searchopt_compute_credits_day = (inp.searchopt_compute_hours_per_day or 0.0) * searchopt_compute_multiplier
    searchopt_cs_credits_day = (inp.searchopt_compute_hours_per_day or 0.0) * searchopt_cs_multiplier
    searchopt_credits_day = searchopt_compute_credits_day + searchopt_cs_credits_day
    
    # Serverless Tasks: multipliers
    tasks_config = pricing["serverless"].get("serverlessTasks", {})
    if tasks_config.get("multiplierCompute") is not None:
        # New multiplier-based approach
        tasks_compute_multiplier = tasks_config.get("multiplierCompute", 0.9)
        tasks_cs_multiplier = tasks_config.get("multiplierCloudServices", 1)
        tasks_compute_credits_day = (inp.tasks_hours_per_day or 0.0) * tasks_compute_multiplier
        tasks_cs_credits_day = (inp.tasks_hours_per_day or 0.0) * tasks_cs_multiplier
        tasks_credits_day = tasks_compute_credits_day + tasks_cs_credits_day
    else:
        # Backward compatibility fallback
        tasks_credits_day = (inp.tasks_hours_per_day or 0.0) * pricing["serverless"].get("tasksOverheadCreditsPerHour", 0.25)
    
    serverless_credits_expected = snowpipe_credits_day + searchopt_credits_day + tasks_credits_day
    serverless_credits_actual = result["daily"]["serverlessCreditsDay"]
    if abs(serverless_credits_expected - serverless_credits_actual) > 0.001:
        errors.append(f"Serverless credits mismatch: expected {serverless_credits_expected}, got {serverless_credits_actual}")
    
    # Step 7: Monthly credits
    total_monthly_credits_expected = (wh_credits_expected + cs_credits_expected + serverless_credits_expected) * inp.frequency_per_month
    total_monthly_credits_actual = result["monthly"]["credits"]
    if abs(total_monthly_credits_expected - total_monthly_credits_actual) > 0.001:
        errors.append(f"Monthly credits mismatch: expected {total_monthly_credits_expected}, got {total_monthly_credits_actual}")
    
    # Step 8: Compute cost
    region_pricing = pricing["regions"][inp.region]
    edition_key = inp.edition
    if inp.edition == "vps" and "vps" not in region_pricing["pricePerCredit"]:
        edition_key = "business_critical"
    price_per_credit = region_pricing["pricePerCredit"].get(edition_key) or region_pricing["pricePerCredit"]["business_critical"]
    compute_cost_expected = total_monthly_credits_expected * price_per_credit
    compute_cost_actual = result["monthly"]["dollarsCompute"]
    if abs(compute_cost_expected - compute_cost_actual) > 0.01:
        errors.append(f"Compute cost mismatch: expected {compute_cost_expected}, got {compute_cost_actual}")
    
    # Step 9: Storage cost
    storage_rate = region_pricing.get("storagePerTBMonth", 0.0)
    regular_storage = (inp.uncompressed_tb_at_rest or 0.0) * storage_rate
    time_travel_storage = (inp.time_travel_tb or 0.0) * storage_rate
    failsafe_storage = (inp.failsafe_tb or 0.0) * storage_rate
    storage_expected = regular_storage + time_travel_storage + failsafe_storage
    storage_actual = result["monthly"]["dollarsStorage"]
    if abs(storage_expected - storage_actual) > 0.01:
        errors.append(f"Storage cost mismatch: expected {storage_expected}, got {storage_actual}")
    
    # Step 10: Transfer cost
    egress_rates = region_pricing.get("egressPerTB", {})
    egress_route_key = inp.egress_route
    if inp.egress_route == "crossCloud" and "crossCloud" not in egress_rates:
        egress_route_key = "internet"
    if inp.egress_route == "accountTransfer" and "accountTransfer" not in egress_rates:
        egress_route_key = "interRegion"
    egress_rate = egress_rates.get(egress_route_key) or egress_rates.get(inp.egress_route) or 0.0
    transfer_expected = (inp.egress_tb or 0.0) * egress_rate
    transfer_actual = result["monthly"]["dollarsTransfer"]
    if abs(transfer_expected - transfer_actual) > 0.01:
        errors.append(f"Transfer cost mismatch: expected {transfer_expected}, got {transfer_actual}")
    
    # Step 11: Grand total
    grand_total_expected = compute_cost_expected + storage_expected + transfer_expected
    grand_total_actual = result["monthly"]["grandTotal"]
    if abs(grand_total_expected - grand_total_actual) > 0.01:
        errors.append(f"Grand total mismatch: expected {grand_total_expected}, got {grand_total_actual}")
    
    return errors

def test_baseline():
    """Test the baseline case from cases.csv"""
    pricing, rules, calib = load_configs()
    inp = InputModel(
        db2_cpu_seconds_per_day=72000,
        batch_window_hours=4,
        concurrency=2,
        uncompressed_tb_at_rest=30,
        frequency_per_month=30,
        egress_tb=2,
        egress_route="interRegion",
        region="aws-us-east-1",
        edition="enterprise",
        family="elt_batch",
        snowpipe_files_per_day=0,
        searchopt_compute_hours_per_day=0,
        tasks_hours_per_day=0,
        time_travel_tb=0,
        failsafe_tb=0
    )
    result = compute(inp, pricing, rules, calib)
    errors = manual_calculation_verification(inp, pricing, rules, calib, result)
    return errors, result

def test_low_cpu():
    """Test the low_cpu case from cases.csv"""
    pricing, rules, calib = load_configs()
    inp = InputModel(
        db2_cpu_seconds_per_day=1800,
        batch_window_hours=2,
        concurrency=1,
        uncompressed_tb_at_rest=5,
        frequency_per_month=30,
        egress_tb=0,
        egress_route="intraRegion",
        region="aws-us-west-2",
        edition="standard",
        family="reporting",
        snowpipe_files_per_day=1000,
        searchopt_compute_hours_per_day=2.0,  # 2 hours/day for search optimization
        tasks_hours_per_day=0.5,
        time_travel_tb=0,
        failsafe_tb=0
    )
    result = compute(inp, pricing, rules, calib)
    errors = manual_calculation_verification(inp, pricing, rules, calib, result)
    return errors, result

def test_edge_cases():
    """Test edge cases"""
    pricing, rules, calib = load_configs()
    all_errors = []
    
    # Test 1: Concurrency = 0 (should use 1)
    inp = InputModel(
        db2_cpu_seconds_per_day=3600,
        batch_window_hours=1,
        concurrency=0,
        uncompressed_tb_at_rest=1,
        frequency_per_month=1,
        egress_tb=0,
        egress_route="intraRegion",
        region="aws-us-east-1",
        edition="standard",
        family="elt_batch",
        snowpipe_files_per_day=0,
        searchopt_compute_hours_per_day=0,
        tasks_hours_per_day=0,
        time_travel_tb=0,
        failsafe_tb=0
    )
    result = compute(inp, pricing, rules, calib)
    errors = manual_calculation_verification(inp, pricing, rules, calib, result)
    if errors:
        all_errors.extend([f"Edge case (concurrency=0): {e}" for e in errors])
    
    # Test 2: VPS edition without VPS pricing (should fallback)
    inp = InputModel(
        db2_cpu_seconds_per_day=3600,
        batch_window_hours=1,
        concurrency=1,
        uncompressed_tb_at_rest=1,
        frequency_per_month=1,
        egress_tb=0,
        egress_route="intraRegion",
        region="aws-us-east-1",
        edition="vps",  # VPS exists in config, but test fallback logic
        family="elt_batch",
        snowpipe_files_per_day=0,
        searchopt_compute_hours_per_day=0,
        tasks_hours_per_day=0,
        time_travel_tb=0,
        failsafe_tb=0
    )
    result = compute(inp, pricing, rules, calib)
    errors = manual_calculation_verification(inp, pricing, rules, calib, result)
    if errors:
        all_errors.extend([f"Edge case (VPS): {e}" for e in errors])
    
    # Test 3: Missing workload family (should use default)
    inp = InputModel(
        db2_cpu_seconds_per_day=3600,
        batch_window_hours=1,
        concurrency=1,
        uncompressed_tb_at_rest=1,
        frequency_per_month=1,
        egress_tb=0,
        egress_route="intraRegion",
        region="aws-us-east-1",
        edition="standard",
        family="nonexistent_family",  # Should fallback to default
        snowpipe_files_per_day=0,
        searchopt_compute_hours_per_day=0,
        tasks_hours_per_day=0,
        time_travel_tb=0,
        failsafe_tb=0
    )
    result = compute(inp, pricing, rules, calib)
    errors = manual_calculation_verification(inp, pricing, rules, calib, result)
    if errors:
        all_errors.extend([f"Edge case (missing family): {e}" for e in errors])
    
    # Test 4: Multi-cluster warehouse
    inp = InputModel(
        db2_cpu_seconds_per_day=72000,
        batch_window_hours=4,
        concurrency=2,
        uncompressed_tb_at_rest=30,
        frequency_per_month=30,
        egress_tb=2,
        egress_route="interRegion",
        region="aws-us-east-1",
        edition="enterprise",
        family="elt_batch",
        snowpipe_files_per_day=0,
        searchopt_compute_hours_per_day=0,
        tasks_hours_per_day=0,
        time_travel_tb=0,
        failsafe_tb=0,
        warehouse_type="multi_cluster",
        cluster_count=3
    )
    result = compute(inp, pricing, rules, calib)
    errors = manual_calculation_verification(inp, pricing, rules, calib, result)
    if errors:
        all_errors.extend([f"Edge case (multi-cluster): {e}" for e in errors])
    # Verify multi-cluster multiplication
    wf = inp.family if inp.family in calib["workloadFamilies"] else calib["defaultFamily"]
    k = calib["workloadFamilies"][wf]["k_xs_seconds_per_db2_cpu_second"]
    xs_hours = (inp.db2_cpu_seconds_per_day * k) / 3600.0
    need = xs_hours * max(1, inp.concurrency)
    size = result["selection"]["size"]
    size_factor = rules["sizeFactor"][size]
    wh_hours_single = need / size_factor
    wh_credits_single = wh_hours_single * rules["warehouseCreditsPerHour"][size]
    wh_credits_expected = wh_credits_single * inp.cluster_count
    if abs(result["daily"]["whCreditsDay"] - wh_credits_expected) > 0.001:
        all_errors.append(f"Multi-cluster credits mismatch: expected {wh_credits_expected}, got {result['daily']['whCreditsDay']}")
    
    # Test 5: Business Critical Snowpipe (per-GB model)
    inp = InputModel(
        db2_cpu_seconds_per_day=3600,
        batch_window_hours=1,
        concurrency=1,
        uncompressed_tb_at_rest=1,
        frequency_per_month=1,
        egress_tb=0,
        egress_route="intraRegion",
        region="aws-us-east-1",
        edition="business_critical",
        family="elt_batch",
        snowpipe_files_per_day=0,
        snowpipe_uncompressed_gb_per_day=1000,  # 1 TB = 1000 GB
        searchopt_compute_hours_per_day=0,
        tasks_hours_per_day=0,
        time_travel_tb=0,
        failsafe_tb=0
    )
    result = compute(inp, pricing, rules, calib)
    errors = manual_calculation_verification(inp, pricing, rules, calib, result)
    if errors:
        all_errors.extend([f"Edge case (BC Snowpipe): {e}" for e in errors])
    
    # Test 6: Zero values (should not crash)
    inp = InputModel(
        db2_cpu_seconds_per_day=0,
        batch_window_hours=1,
        concurrency=1,
        uncompressed_tb_at_rest=0,
        frequency_per_month=0,
        egress_tb=0,
        egress_route="intraRegion",
        region="aws-us-east-1",
        edition="standard",
        family="elt_batch",
        snowpipe_files_per_day=0,
        searchopt_compute_hours_per_day=0,
        tasks_hours_per_day=0,
        time_travel_tb=0,
        failsafe_tb=0
    )
    try:
        result = compute(inp, pricing, rules, calib)
        # Should return zero credits but valid structure
        if result["monthly"]["credits"] != 0:
            all_errors.append(f"Zero input should result in zero credits, got {result['monthly']['credits']}")
    except Exception as e:
        all_errors.append(f"Zero values test crashed: {e}")
    
    return all_errors

def main():
    """Run all validation tests"""
    print("=" * 70)
    print("COMPREHENSIVE CALCULATION VALIDATION")
    print("=" * 70)
    print()
    
    all_errors = []
    
    # Test baseline case
    print("Testing baseline case...")
    errors, result = test_baseline()
    if errors:
        all_errors.extend([f"Baseline: {e}" for e in errors])
        print(f"  [FAIL] {len(errors)} errors")
        for e in errors:
            print(f"    - {e}")
    else:
        print(f"  [PASS]")
        print(f"    Size: {result['selection']['size']}, Monthly Credits: {result['monthly']['credits']:.2f}")
    
    print()
    
    # Test low_cpu case
    print("Testing low_cpu case...")
    errors, result = test_low_cpu()
    if errors:
        all_errors.extend([f"Low CPU: {e}" for e in errors])
        print(f"  [FAIL] {len(errors)} errors")
        for e in errors:
            print(f"    - {e}")
    else:
        print(f"  [PASS]")
        print(f"    Size: {result['selection']['size']}, Monthly Credits: {result['monthly']['credits']:.2f}")
    
    print()
    
    # Test edge cases
    print("Testing edge cases...")
    errors = test_edge_cases()
    if errors:
        all_errors.extend(errors)
        print(f"  [FAIL] {len(errors)} errors")
        for e in errors:
            print(f"    - {e}")
    else:
        print(f"  [PASS]")
    
    print()
    print("=" * 70)
    if all_errors:
        print(f"VALIDATION FAILED: {len(all_errors)} errors found")
        return 1
    else:
        print("VALIDATION PASSED: All calculations are correct!")
        return 0

if __name__ == "__main__":
    exit(main())

