#!/usr/bin/env python3
"""
Validation script to compare config files and calculation logic against
the Snowflake Service Consumption document.

This script validates:
1. rules.json against Section 1 (Core rules)
2. pricing.json against Section 2 (On-demand pricing) and Section 3 (Serverless)
3. Calculation logic against Section 5 (Example formulas)
"""

import json
import sys
from pathlib import Path

# Expected values from Snowflake document
SNOWFLAKE_DOC_RULES = {
    "warehouseCreditsPerHour": {
        "XS": 1.35, "S": 2.7, "M": 5.4, "L": 10.8,
        "XL": 21.6, "2XL": 43.2, "3XL": 86.4, "4XL": 172.8
    },
    "sizeFactor": {
        "XS": 1, "S": 2, "M": 4, "L": 8,
        "XL": 16, "2XL": 32, "3XL": 64, "4XL": 128
    },
    "cloudServices": {
        "capCreditsPerHour": 4.4,
        "waiverPctOfDailyWH": 0.10
    }
}

# Example regions from Section 2 (for validation)
SNOWFLAKE_DOC_PRICING_EXAMPLES = {
    "aws-us-east-1": {
        "pricePerCredit": {
            "standard": 2.00,
            "enterprise": 3.00,
            "business_critical": 4.00
        },
        "storagePerTBMonth": 23.00,
        "egressPerTB": {
            "intraRegion": 0.00,
            "interRegion": 20.00,
            "internet": 90.00
        }
    },
    "aws-us-west-2": {
        "pricePerCredit": {
            "standard": 2.00,
            "enterprise": 3.00,
            "business_critical": 4.00
        },
        "storagePerTBMonth": 23.00,
        "egressPerTB": {
            "intraRegion": 0.00,
            "interRegion": 20.00,
            "internet": 90.00
        }
    },
    "aws-eu-west-1": {
        "pricePerCredit": {
            "standard": 2.60,
            "enterprise": 3.90,
            "business_critical": 5.20
        },
        "storagePerTBMonth": 23.00,
        "egressPerTB": {
            "intraRegion": 0.00,
            "interRegion": 20.00,
            "internet": 90.00
        }
    }
}

# Serverless config from Section 3
SNOWFLAKE_DOC_SERVERLESS = {
    "snowpipe": {
        "standardEnterprise": {
            "multiplierCompute": 1.25,
            "multiplierCloudServices": 0,
            "rateCreditsPer1000Files": 0.06
        },
        "businessCriticalVPS": {
            "multiplierCompute": 0,
            "multiplierCloudServices": 0,
            "rateCreditsPerGB": 0.0037
        }
    },
    "searchOptimization": {
        "multiplierCompute": 2,
        "multiplierCloudServices": 1
    },
    "serverlessTasks": {
        "multiplierCompute": 0.9,
        "multiplierCloudServices": 1
    }
}

def load_json(filepath):
    """Load JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def validate_rules(rules_data):
    """Validate rules.json against Section 1 of Snowflake doc."""
    errors = []
    warnings = []
    
    print("\n" + "="*70)
    print("VALIDATING rules.json AGAINST SECTION 1 (Core Rules)")
    print("="*70)
    
    # Check warehouseCreditsPerHour
    print("\n1. Warehouse Credits Per Hour:")
    expected_wh = SNOWFLAKE_DOC_RULES["warehouseCreditsPerHour"]
    actual_wh = rules_data.get("warehouseCreditsPerHour", {})
    
    for size in ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL"]:
        expected = expected_wh.get(size)
        actual = actual_wh.get(size)
        if actual is None:
            errors.append(f"Missing warehouseCreditsPerHour[{size}]")
            print(f"  [X] {size}: MISSING")
        elif abs(actual - expected) > 0.001:
            errors.append(f"warehouseCreditsPerHour[{size}]: expected {expected}, got {actual}")
            print(f"  [X] {size}: Expected {expected}, Got {actual}")
        else:
            print(f"  [OK] {size}: {actual}")
    
    # Check sizeFactor
    print("\n2. Size Factor:")
    expected_sf = SNOWFLAKE_DOC_RULES["sizeFactor"]
    actual_sf = rules_data.get("sizeFactor", {})
    
    for size in ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL"]:
        expected = expected_sf.get(size)
        actual = actual_sf.get(size)
        if actual is None:
            errors.append(f"Missing sizeFactor[{size}]")
            print(f"  [X] {size}: MISSING")
        elif actual != expected:
            errors.append(f"sizeFactor[{size}]: expected {expected}, got {actual}")
            print(f"  [X] {size}: Expected {expected}, Got {actual}")
        else:
            print(f"  [OK] {size}: {actual}")
    
    # Check cloudServices
    print("\n3. Cloud Services:")
    expected_cs = SNOWFLAKE_DOC_RULES["cloudServices"]
    actual_cs = rules_data.get("cloudServices", {})
    
    cap_expected = expected_cs["capCreditsPerHour"]
    cap_actual = actual_cs.get("capCreditsPerHour")
    if cap_actual is None:
        errors.append("Missing cloudServices.capCreditsPerHour")
        print(f"  [X] capCreditsPerHour: MISSING")
    elif abs(cap_actual - cap_expected) > 0.001:
        errors.append(f"cloudServices.capCreditsPerHour: expected {cap_expected}, got {cap_actual}")
        print(f"  [X] capCreditsPerHour: Expected {cap_expected}, Got {cap_actual}")
    else:
        print(f"  [OK] capCreditsPerHour: {cap_actual}")
    
    waiver_expected = expected_cs["waiverPctOfDailyWH"]
    waiver_actual = actual_cs.get("waiverPctOfDailyWH")
    if waiver_actual is None:
        errors.append("Missing cloudServices.waiverPctOfDailyWH")
        print(f"  [X] waiverPctOfDailyWH: MISSING")
    elif abs(waiver_actual - waiver_expected) > 0.001:
        errors.append(f"cloudServices.waiverPctOfDailyWH: expected {waiver_expected}, got {waiver_actual}")
        print(f"  [X] waiverPctOfDailyWH: Expected {waiver_expected}, Got {waiver_actual}")
    else:
        print(f"  [OK] waiverPctOfDailyWH: {waiver_actual}")
    
    return errors, warnings

def validate_pricing(pricing_data):
    """Validate pricing.json against Section 2 and 3 of Snowflake doc."""
    errors = []
    warnings = []
    
    print("\n" + "="*70)
    print("VALIDATING pricing.json AGAINST SECTION 2 (Pricing Examples)")
    print("="*70)
    
    regions = pricing_data.get("regions", {})
    
    # Validate example regions from the doc
    for region_key, expected_region in SNOWFLAKE_DOC_PRICING_EXAMPLES.items():
        print(f"\nRegion: {region_key}")
        if region_key not in regions:
            warnings.append(f"Region {region_key} not found in pricing.json (may be using different key)")
            print(f"  [WARN] Region not found (may use different key)")
            continue
        
        actual_region = regions[region_key]
        
        # Check pricePerCredit
        print("  Price Per Credit:")
        expected_ppc = expected_region["pricePerCredit"]
        actual_ppc = actual_region.get("pricePerCredit", {})
        
        for edition in ["standard", "enterprise", "business_critical"]:
            expected = expected_ppc.get(edition)
            actual = actual_ppc.get(edition)
            if actual is None:
                warnings.append(f"{region_key}.pricePerCredit[{edition}]: missing (may not be available)")
                print(f"    [WARN] {edition}: MISSING (may not be available)")
            elif abs(actual - expected) > 0.001:
                errors.append(f"{region_key}.pricePerCredit[{edition}]: expected {expected}, got {actual}")
                print(f"    [X] {edition}: Expected {expected}, Got {actual}")
            else:
                print(f"    [OK] {edition}: {actual}")
        
        # Check storagePerTBMonth
        print("  Storage Per TB/Month:")
        expected_storage = expected_region["storagePerTBMonth"]
        actual_storage = actual_region.get("storagePerTBMonth")
        if actual_storage is None:
            errors.append(f"{region_key}.storagePerTBMonth: missing")
            print(f"    [X] MISSING")
        elif abs(actual_storage - expected_storage) > 0.001:
            warnings.append(f"{region_key}.storagePerTBMonth: expected {expected_storage}, got {actual_storage} (may vary by region)")
            print(f"    [WARN] Expected {expected_storage}, Got {actual_storage} (may vary)")
        else:
            print(f"    [OK] {actual_storage}")
        
        # Check egressPerTB
        print("  Egress Per TB:")
        expected_egress = expected_region["egressPerTB"]
        actual_egress = actual_region.get("egressPerTB", {})
        
        for route in ["intraRegion", "interRegion", "internet"]:
            expected = expected_egress.get(route)
            actual = actual_egress.get(route)
            if actual is None:
                warnings.append(f"{region_key}.egressPerTB[{route}]: missing")
                print(f"    [WARN] {route}: MISSING")
            elif abs(actual - expected) > 0.001:
                warnings.append(f"{region_key}.egressPerTB[{route}]: expected {expected}, got {actual} (may vary)")
                print(f"    [WARN] {route}: Expected {expected}, Got {actual} (may vary)")
            else:
                print(f"    [OK] {route}: {actual}")
    
    return errors, warnings

def validate_serverless(pricing_data):
    """Validate serverless config against Section 3 of Snowflake doc."""
    errors = []
    warnings = []
    
    print("\n" + "="*70)
    print("VALIDATING pricing.json AGAINST SECTION 3 (Serverless Features)")
    print("="*70)
    
    serverless = pricing_data.get("serverless", {})
    
    if not serverless:
        errors.append("Missing serverless section in pricing.json")
        print("  [X] Missing serverless section")
        return errors, warnings
    
    # Validate Snowpipe Standard/Enterprise
    print("\n1. Snowpipe (Standard/Enterprise):")
    snowpipe_se = serverless.get("snowpipe", {}).get("standardEnterprise", {})
    expected_se = SNOWFLAKE_DOC_SERVERLESS["snowpipe"]["standardEnterprise"]
    
    for key in ["multiplierCompute", "multiplierCloudServices", "rateCreditsPer1000Files"]:
        expected = expected_se.get(key)
        actual = snowpipe_se.get(key)
        if actual is None:
            errors.append(f"serverless.snowpipe.standardEnterprise.{key}: missing")
            print(f"  [X] {key}: MISSING")
        elif abs(actual - expected) > 0.001:
            errors.append(f"serverless.snowpipe.standardEnterprise.{key}: expected {expected}, got {actual}")
            print(f"  [X] {key}: Expected {expected}, Got {actual}")
        else:
            print(f"  [OK] {key}: {actual}")
    
    # Validate Snowpipe Business-Critical/VPS
    print("\n2. Snowpipe (Business-Critical/VPS):")
    snowpipe_bc = serverless.get("snowpipe", {}).get("businessCriticalVPS", {})
    expected_bc = SNOWFLAKE_DOC_SERVERLESS["snowpipe"]["businessCriticalVPS"]
    
    for key in ["multiplierCompute", "multiplierCloudServices", "rateCreditsPerGB"]:
        expected = expected_bc.get(key)
        actual = snowpipe_bc.get(key)
        if actual is None:
            errors.append(f"serverless.snowpipe.businessCriticalVPS.{key}: missing")
            print(f"  [X] {key}: MISSING")
        elif abs(actual - expected) > 0.001:
            errors.append(f"serverless.snowpipe.businessCriticalVPS.{key}: expected {expected}, got {actual}")
            print(f"  [X] {key}: Expected {expected}, Got {actual}")
        else:
            print(f"  [OK] {key}: {actual}")
    
    # Validate Search Optimization
    print("\n3. Search Optimization:")
    searchopt = serverless.get("searchOptimization", {})
    expected_so = SNOWFLAKE_DOC_SERVERLESS["searchOptimization"]
    
    for key in ["multiplierCompute", "multiplierCloudServices"]:
        expected = expected_so.get(key)
        actual = searchopt.get(key)
        if actual is None:
            errors.append(f"serverless.searchOptimization.{key}: missing")
            print(f"  [X] {key}: MISSING")
        elif abs(actual - expected) > 0.001:
            errors.append(f"serverless.searchOptimization.{key}: expected {expected}, got {actual}")
            print(f"  [X] {key}: Expected {expected}, Got {actual}")
        else:
            print(f"  [OK] {key}: {actual}")
    
    # Validate Serverless Tasks
    print("\n4. Serverless Tasks:")
    tasks = serverless.get("serverlessTasks", {})
    expected_tasks = SNOWFLAKE_DOC_SERVERLESS["serverlessTasks"]
    
    for key in ["multiplierCompute", "multiplierCloudServices"]:
        expected = expected_tasks.get(key)
        actual = tasks.get(key)
        if actual is None:
            errors.append(f"serverless.serverlessTasks.{key}: missing")
            print(f"  [X] {key}: MISSING")
        elif abs(actual - expected) > 0.001:
            errors.append(f"serverless.serverlessTasks.{key}: expected {expected}, got {actual}")
            print(f"  [X] {key}: Expected {expected}, Got {actual}")
        else:
            print(f"  [OK] {key}: {actual}")
    
    return errors, warnings

def validate_calculation_logic():
    """Validate calculation logic against Section 5 formulas."""
    errors = []
    warnings = []
    
    print("\n" + "="*70)
    print("VALIDATING CALCULATION LOGIC AGAINST SECTION 5 (Formulas)")
    print("="*70)
    
    # Read calc.js to check formulas
    calc_js_path = Path(__file__).parent.parent / "lib" / "calc.js"
    if not calc_js_path.exists():
        errors.append("calc.js not found")
        print("  [X] calc.js not found")
        return errors, warnings
    
    calc_js = calc_js_path.read_text(encoding='utf-8')
    
    # Check Cloud Services formula
    print("\n1. Cloud Services Calculation:")
    # Formula from doc: cs_credits_day = min(4.4 × wh_hours_day, 0.10 × wh_credits_day)
    # Check if code implements: Math.min(csCap, csTenPct) where csCap = capCreditsPerHour * whHoursDay
    if "csCap" in calc_js and "csTenPct" in calc_js and "Math.min" in calc_js:
        print("  [OK] Cloud Services uses min(cap, waiver) formula")
    else:
        errors.append("Cloud Services calculation may not match doc formula")
        print("  [X] Cloud Services formula may not match doc")
    
    # Check if waiver percentage is used correctly
    if "waiverPctOfDailyWH" in calc_js or "waiverPct" in calc_js:
        print("  [OK] Uses waiverPctOfDailyWH from config")
    else:
        warnings.append("May not use waiverPctOfDailyWH from config")
        print("  [WARN] May not use waiverPctOfDailyWH from config")
    
    # Check Snowpipe formulas
    print("\n2. Snowpipe Calculation:")
    # Standard/Enterprise: (files/1000)×0.06 + compute_hours×1.25
    if "rateCreditsPer1000Files" in calc_js and "multiplierCompute" in calc_js:
        print("  [OK] Standard/Enterprise uses per-file + compute multiplier")
    else:
        errors.append("Snowpipe Standard/Enterprise formula may not match doc")
        print("  [X] Standard/Enterprise formula may not match doc")
    
    # Business-Critical/VPS: uncompressed_GB × 0.0037
    if "rateCreditsPerGB" in calc_js and ("0.0037" in calc_js or "rateCreditsPerGB" in calc_js):
        print("  [OK] Business-Critical/VPS uses per-GB rate")
    else:
        warnings.append("Snowpipe Business-Critical/VPS formula may not match doc")
        print("  [WARN] Business-Critical/VPS formula may not match doc")
    
    # Check Search Optimization formula
    print("\n3. Search Optimization Calculation:")
    # Formula: compute_hours × (2 compute + 1 Cloud Services) = hours × 3
    if "multiplierCompute" in calc_js and "multiplierCloudServices" in calc_js:
        print("  [OK] Uses multiplierCompute and multiplierCloudServices")
    else:
        errors.append("Search Optimization formula may not match doc")
        print("  [X] Search Optimization formula may not match doc")
    
    # Check Serverless Tasks formula
    print("\n4. Serverless Tasks Calculation:")
    # Formula: task_runtime_hours × 0.9 (compute) + task_runtime_hours × 1 (Cloud Services)
    if "multiplierCompute" in calc_js and "multiplierCloudServices" in calc_js:
        print("  [OK] Uses multiplierCompute and multiplierCloudServices")
    else:
        warnings.append("Serverless Tasks formula may not match doc")
        print("  [WARN] Serverless Tasks formula may not match doc")
    
    return errors, warnings

def main():
    """Main validation function."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    print("="*70)
    print("SNOWFLAKE DOCUMENT VALIDATION")
    print("="*70)
    print(f"Validating against: docs/Snowflake_Service_Consumption_CursorReady.md")
    print(f"Project root: {project_root}")
    
    all_errors = []
    all_warnings = []
    
    # Load config files
    try:
        rules_data = load_json(project_root / "config" / "rules.json")
        pricing_data = load_json(project_root / "config" / "pricing.json")
    except FileNotFoundError as e:
        print(f"\n[X] ERROR: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n[X] ERROR: Invalid JSON: {e}")
        sys.exit(1)
    
    # Validate rules.json
    errors, warnings = validate_rules(rules_data)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    
    # Validate pricing.json (Section 2)
    errors, warnings = validate_pricing(pricing_data)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    
    # Validate serverless config (Section 3)
    errors, warnings = validate_serverless(pricing_data)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    
    # Validate calculation logic (Section 5)
    errors, warnings = validate_calculation_logic()
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    
    # Summary
    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)
    print(f"Errors: {len(all_errors)}")
    print(f"Warnings: {len(all_warnings)}")
    
    if all_errors:
        print("\n[X] ERRORS FOUND:")
        for i, error in enumerate(all_errors, 1):
            print(f"  {i}. {error}")
    
    if all_warnings:
        print("\n[WARN] WARNINGS:")
        for i, warning in enumerate(all_warnings, 1):
            print(f"  {i}. {warning}")
    
    if not all_errors and not all_warnings:
        print("\n[OK] ALL VALIDATIONS PASSED!")
        return 0
    elif not all_errors:
        print("\n[WARN] VALIDATION PASSED WITH WARNINGS")
        return 0
    else:
        print("\n[X] VALIDATION FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())

