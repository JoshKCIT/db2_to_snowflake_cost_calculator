"""
Copyright (c) 2025 JoshKCIT

Core calculation logic for Snowflake Budget Calculator
"""

from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class InputModel:
    db2_cpu_seconds_per_day: float
    batch_window_hours: float
    concurrency: int
    uncompressed_tb_at_rest: float
    frequency_per_month: int
    egress_tb: float
    egress_route: str
    region: str
    edition: str
    family: str
    snowpipe_files_per_day: float = 0.0
    snowpipe_compute_hours_per_day: float = 0.0
    snowpipe_uncompressed_gb_per_day: float = 0.0
    searchopt_compute_hours_per_day: float = 0.0
    tasks_hours_per_day: float = 0.0
    time_travel_tb: float = 0.0
    failsafe_tb: float = 0.0
    warehouse_type: str = "standard"
    cluster_count: int = 1

def pick_size(xs_hours: float, window_h: float, concurrency: int, size_factor: Dict[str,int]) -> str:
    need = xs_hours * max(1, concurrency)
    order = ["XS","S","M","L","XL","2XL","3XL","4XL"]
    for s in order:
        wh_hours = need / size_factor[s]
        if wh_hours <= window_h:
            return s
    return "4XL"

def compute(inp: InputModel, pricing: Dict[str,Any], rules: Dict[str,Any], calib: Dict[str,Any]) -> Dict[str,Any]:
    # Validate inputs to prevent runtime errors
    if not pricing or "regions" not in pricing or inp.region not in pricing["regions"]:
        raise ValueError(f"Invalid pricing config: region '{inp.region}' not found")
    
    region_pricing = pricing["regions"][inp.region]
    if "pricePerCredit" not in region_pricing:
        raise ValueError(f"Invalid pricing config: pricePerCredit not found for region '{inp.region}'")
    
    if not calib or "workloadFamilies" not in calib:
        raise ValueError("Invalid calibration config: workloadFamilies not found")
    
    if not rules or "sizeFactor" not in rules or "warehouseCreditsPerHour" not in rules:
        raise ValueError("Invalid rules config: required fields missing")
    
    wf = inp.family if inp.family in calib["workloadFamilies"] else calib["defaultFamily"]
    k = calib["workloadFamilies"][wf]["k_xs_seconds_per_db2_cpu_second"]

    xs_hours = (inp.db2_cpu_seconds_per_day * k) / 3600.0
    size = pick_size(xs_hours, inp.batch_window_hours, inp.concurrency, rules["sizeFactor"])
    credits_per_hour = rules["warehouseCreditsPerHour"][size]

    need = xs_hours * max(1, inp.concurrency)
    wh_hours_day = need / rules["sizeFactor"][size]
    wh_credits_day = wh_hours_day * credits_per_hour

    # Multi-cluster support: multiply credits by cluster count
    if inp.warehouse_type == "multi_cluster":
        wh_credits_day = wh_credits_day * inp.cluster_count
        wh_hours_day = wh_hours_day * inp.cluster_count  # For display purposes

    # Cloud Services calculation with configurable waiver percentage
    cs_cap = rules["cloudServices"]["capCreditsPerHour"] * wh_hours_day
    waiver_pct = rules["cloudServices"].get("waiverPctOfDailyWH", 0.10)  # Backward compatibility
    cs_tenpct = waiver_pct * wh_credits_day
    cs_credits_day = min(cs_cap, cs_tenpct)

    # Snowpipe calculation - edition-specific logic
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

    # Search Optimization: compute multipliers (daily, not monthly)
    searchopt_config = pricing["serverless"].get("searchOptimization", {})
    searchopt_compute_multiplier = searchopt_config.get("multiplierCompute", 2)
    searchopt_cs_multiplier = searchopt_config.get("multiplierCloudServices", 1)
    searchopt_compute_credits_day = (inp.searchopt_compute_hours_per_day or 0.0) * searchopt_compute_multiplier
    searchopt_cs_credits_day = (inp.searchopt_compute_hours_per_day or 0.0) * searchopt_cs_multiplier
    searchopt_credits_day = searchopt_compute_credits_day + searchopt_cs_credits_day

    # Serverless Tasks: correct multipliers
    tasks_config = pricing["serverless"].get("serverlessTasks", {})
    tasks_credits_day = 0.0
    if tasks_config.get("multiplierCompute") is not None:
        # New multiplier-based approach
        tasks_compute_multiplier = tasks_config.get("multiplierCompute", 0.9)
        tasks_cs_multiplier = tasks_config.get("multiplierCloudServices", 1)
        tasks_compute_credits_day = (inp.tasks_hours_per_day or 0.0) * tasks_compute_multiplier
        tasks_cs_credits_day = (inp.tasks_hours_per_day or 0.0) * tasks_cs_multiplier
        tasks_credits_day = tasks_compute_credits_day + tasks_cs_credits_day
    else:
        # Backward compatibility: fallback to old config
        tasks_credits_day = (inp.tasks_hours_per_day or 0.0) * pricing["serverless"].get("tasksOverheadCreditsPerHour", 0.25)

    serverless_credits_day = snowpipe_credits_day + searchopt_credits_day + tasks_credits_day

    monthly_credits = (wh_credits_day + cs_credits_day + serverless_credits_day) * inp.frequency_per_month

    # Handle VPS edition - fallback to business_critical if VPS pricing not available
    edition_key = inp.edition
    if inp.edition == "vps" and "vps" not in region_pricing["pricePerCredit"]:
        edition_key = "business_critical"
    
    # Validate edition exists, with fallback to business_critical
    if edition_key not in region_pricing["pricePerCredit"] and "business_critical" not in region_pricing["pricePerCredit"]:
        raise ValueError(f"Invalid pricing config: edition '{edition_key}' and fallback 'business_critical' not found for region '{inp.region}'")
    price_per_credit = region_pricing["pricePerCredit"].get(edition_key) or region_pricing["pricePerCredit"]["business_critical"]

    total_monthly_credits = monthly_credits
    monthly_dollars = total_monthly_credits * price_per_credit

    # Storage costs: regular storage + Time Travel + Fail-safe (all charged at same rate)
    storage_rate = region_pricing.get("storagePerTBMonth", 0.0)
    regular_storage_monthly = (inp.uncompressed_tb_at_rest or 0.0) * storage_rate
    time_travel_storage_monthly = (inp.time_travel_tb or 0.0) * storage_rate
    failsafe_storage_monthly = (inp.failsafe_tb or 0.0) * storage_rate
    storage_monthly = regular_storage_monthly + time_travel_storage_monthly + failsafe_storage_monthly

    # Handle egress route - support new transfer types
    egress_rates = region_pricing.get("egressPerTB", {})
    egress_route_key = inp.egress_route
    if inp.egress_route == "crossCloud" and "crossCloud" not in egress_rates:
        egress_route_key = "internet"  # Cross-cloud typically priced like internet
    if inp.egress_route == "accountTransfer" and "accountTransfer" not in egress_rates:
        egress_route_key = "interRegion"  # Account transfer typically priced like inter-region
    egress_rate = egress_rates.get(egress_route_key) or egress_rates.get(inp.egress_route) or 0.0
    transfer_monthly = (inp.egress_tb or 0.0) * egress_rate

    grand_total = monthly_dollars + storage_monthly + transfer_monthly

    return {
        "selection": {"size": size, "creditsPerHour": credits_per_hour, "whHoursDay": wh_hours_day, "clusterCount": inp.cluster_count},
        "daily": {"xsHours": xs_hours, "whCreditsDay": wh_credits_day, "csCreditsDay": cs_credits_day,
                  "serverlessCreditsDay": serverless_credits_day},
        "monthly": {
            "credits": total_monthly_credits,
            "dollarsCompute": monthly_dollars,
            "dollarsStorage": storage_monthly,
            "dollarsStorageRegular": regular_storage_monthly,
            "dollarsStorageTimeTravel": time_travel_storage_monthly,
            "dollarsStorageFailsafe": failsafe_storage_monthly,
            "dollarsTransfer": transfer_monthly,
            "grandTotal": grand_total
        },
        "inputsEcho": {
            "db2CpuSecondsPerDay": inp.db2_cpu_seconds_per_day,
            "batchWindowHours": inp.batch_window_hours,
            "concurrency": inp.concurrency,
            "uncompressedTBAtRest": inp.uncompressed_tb_at_rest,
            "frequencyPerMonth": inp.frequency_per_month,
            "egressTB": inp.egress_tb,
            "egressRoute": inp.egress_route,
            "region": inp.region,
            "edition": inp.edition,
            "family": inp.family,
            "snowpipeFilesPerDay": inp.snowpipe_files_per_day,
            "snowpipeComputeHoursPerDay": inp.snowpipe_compute_hours_per_day,
            "snowpipeUncompressedGBPerDay": inp.snowpipe_uncompressed_gb_per_day,
            "searchOptComputeHoursPerDay": inp.searchopt_compute_hours_per_day,
            "tasksHoursPerDay": inp.tasks_hours_per_day,
            "timeTravelTB": inp.time_travel_tb,
            "failsafeTB": inp.failsafe_tb,
            "warehouseType": inp.warehouse_type,
            "clusterCount": inp.cluster_count
        }
    }

