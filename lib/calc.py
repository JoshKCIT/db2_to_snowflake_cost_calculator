"""
Copyright (c) 2025 JoshKCIT

Core calculation logic for Snowflake Budget Calculator

This module contains the core calculation engine that converts Db2 for z/OS metrics
into Snowflake cost estimates. It implements the 10-step calculation methodology:
1. Convert Db2 CPU seconds to Snowflake XS hours using k-factor calibration
2. Account for concurrent workload requirements
3. Select optimal warehouse size based on batch window constraints
4. Calculate warehouse credits consumed
5. Calculate Cloud Services credits (with 10% waiver rule)
6. Calculate serverless credits (Snowpipe, Search Optimization, Tasks)
7. Scale to monthly credits based on execution frequency
8. Convert credits to dollars using region/edition pricing
9. Add storage costs (regular + Time Travel + Fail-safe)
10. Add data transfer (egress) costs

This module is used by the CLI script (scripts/cli.py) and can be imported
by other Python modules. It provides the same calculation logic as lib/calc.js
but implemented in Python for command-line usage.
"""

from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class InputModel:
    """
    Data model for calculation input parameters.
    
    This dataclass represents all the inputs needed to calculate Snowflake costs
    from Db2 for z/OS metrics. It provides type safety and clear parameter documentation.
    
    Attributes:
        db2_cpu_seconds_per_day: Db2 for z/OS CPU seconds consumed per day
        batch_window_hours: Batch window constraint in hours (SLA requirement)
        concurrency: Number of concurrent jobs running simultaneously
        uncompressed_tb_at_rest: Uncompressed data size in TB (for storage costs)
        frequency_per_month: How many times per month the workload runs
        egress_tb: Data egress volume in TB/month
        egress_route: Egress route type ("intraRegion", "interRegion", "crossCloud", "internet", "accountTransfer")
        region: Snowflake region code (e.g., "aws-us-east-1")
        edition: Snowflake edition ("standard", "enterprise", "business_critical", "vps")
        family: Workload family for k-factor selection ("elt_batch", "reporting", "cdc")
        snowpipe_files_per_day: Snowpipe files processed per day (Standard/Enterprise only, default: 0.0)
        snowpipe_compute_hours_per_day: Snowpipe compute hours per day (Standard/Enterprise only, default: 0.0)
        snowpipe_uncompressed_gb_per_day: Snowpipe data volume in GB/day (Business-Critical/VPS only, default: 0.0)
        searchopt_compute_hours_per_day: Search Optimization compute hours per day (default: 0.0)
        tasks_hours_per_day: Serverless Tasks hours per day (default: 0.0)
        time_travel_tb: Time Travel storage in TB/month (default: 0.0)
        failsafe_tb: Fail-safe storage in TB/month (default: 0.0)
        warehouse_type: Warehouse type ("standard", "multi_cluster", "serverless", default: "standard")
        cluster_count: Number of clusters (for multi-cluster warehouses, default: 1)
    """
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
    """
    Selects the optimal Snowflake warehouse size based on workload requirements.
    
    This function implements the warehouse sizing algorithm: it finds the smallest
    warehouse size that can complete the workload within the specified batch window.
    Larger warehouses cost more per hour but complete work faster, so we select
    the smallest size that meets the time constraint to minimize costs.
    
    Business Logic:
    - Each warehouse size has a "size factor" (XS=1×, S=2×, M=4×, L=8×, etc.)
    - A 2× warehouse completes work in half the time of XS
    - We multiply XS hours by concurrency to get total compute need
    - We divide total need by size factor to get actual warehouse hours
    - We select the smallest size where warehouse hours ≤ batch window
    
    Args:
        xs_hours: XS-equivalent hours needed (after k-factor conversion)
        window_h: Batch window constraint in hours (SLA requirement)
        concurrency: Number of concurrent jobs running simultaneously
        size_factor: Dictionary mapping warehouse sizes to their speed factors
                     (e.g., {"XS": 1, "S": 2, "M": 4, "L": 8, "XL": 16, "2XL": 32, ...})
    
    Returns:
        Warehouse size code (e.g., "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL")
    
    Example:
        >>> # If you need 36 XS hours with 2 concurrent jobs in a 4-hour window:
        >>> # Total need = 36 × 2 = 72 XS-equivalent hours
        >>> # Try XL (16×): 72 ÷ 16 = 4.5 hours (too long)
        >>> # Try 2XL (32×): 72 ÷ 32 = 2.25 hours (fits in 4h window) ✓
        >>> pick_size(36, 4, 2, {"XS":1, "S":2, "M":4, "L":8, "XL":16, "2XL":32})
        '2XL'
    """
    # Calculate total compute need: XS hours × concurrent jobs
    # Concurrency represents jobs that must run simultaneously, not sequentially
    # Example: 2 concurrent jobs means we need 2× the compute capacity
    need = xs_hours * max(1, concurrency)
    
    # Try warehouse sizes from smallest to largest (cost-optimization strategy)
    # We want the smallest size that meets the time constraint
    order = ["XS","S","M","L","XL","2XL","3XL","4XL"]
    
    for s in order:
        # Calculate how many hours this warehouse size would take
        # Formula: Total Need ÷ Size Factor = Warehouse Hours
        # Example: 72 XS-hours ÷ 16 (XL factor) = 4.5 hours
        wh_hours = need / size_factor[s]
        
        # If this size completes work within the batch window, use it
        # This is the smallest size that meets the SLA requirement
        if wh_hours <= window_h:
            return s
    
    # If even 4XL can't meet the window, return 4XL anyway
    # (This indicates the workload may need to be split or window extended)
    return "4XL"

def compute(inp: InputModel, pricing: Dict[str,Any], rules: Dict[str,Any], calib: Dict[str,Any]) -> Dict[str,Any]:
    """
    Main calculation function: converts Db2 for z/OS metrics to Snowflake monthly cost estimate.
    
    This is the core calculation engine that implements the complete cost estimation methodology.
    It performs all 10 calculation steps in sequence and returns a comprehensive result dictionary
    containing warehouse selection, daily credits, monthly credits, and cost breakdowns.
    
    Calculation Flow:
    1. Validates configuration files (pricing, rules, calibration)
    2. Converts Db2 CPU seconds to Snowflake XS hours using k-factor
    3. Selects optimal warehouse size based on batch window
    4. Calculates warehouse credits (with multi-cluster support)
    5. Calculates Cloud Services credits (with 10% waiver rule)
    6. Calculates serverless credits (Snowpipe, Search Optimization, Tasks)
    7. Scales daily credits to monthly based on execution frequency
    8. Converts credits to dollars using region/edition pricing
    9. Calculates storage costs (regular + Time Travel + Fail-safe)
    10. Calculates data transfer (egress) costs
    11. Sums all costs for grand total
    
    Args:
        inp: InputModel instance containing all input parameters
        pricing: Pricing configuration dictionary (from config/pricing.json)
        rules: Rules configuration dictionary (from config/rules.json)
        calib: Calibration configuration dictionary (from config/calibration.json)
    
    Returns:
        Dictionary containing:
        - selection: Warehouse selection details (size, creditsPerHour, whHoursDay, clusterCount)
        - daily: Daily credit breakdown (xsHours, whCreditsDay, csCreditsDay, serverlessCreditsDay)
        - monthly: Monthly cost breakdown (credits, dollarsCompute, dollarsStorage, dollarsTransfer, grandTotal, ...)
        - inputsEcho: Echo of input parameters for reference
    
    Raises:
        ValueError: If configuration is invalid or required data is missing
    """
    # ============================================================================
    # STEP 0: VALIDATE CONFIGURATION FILES
    # ============================================================================
    # Ensure all required configuration data is present before starting calculations
    # This prevents cryptic runtime errors and provides clear error messages
    
    if not pricing or "regions" not in pricing or inp.region not in pricing["regions"]:
        raise ValueError(f"Invalid pricing config: region '{inp.region}' not found")
    
    region_pricing = pricing["regions"][inp.region]
    if "pricePerCredit" not in region_pricing:
        raise ValueError(f"Invalid pricing config: pricePerCredit not found for region '{inp.region}'")
    
    if not calib or "workloadFamilies" not in calib:
        raise ValueError("Invalid calibration config: workloadFamilies not found")
    
    if not rules or "sizeFactor" not in rules or "warehouseCreditsPerHour" not in rules:
        raise ValueError("Invalid rules config: required fields missing")
    
    # ============================================================================
    # STEP 1: CONVERT DB2 FOR Z/OS CPU SECONDS TO SNOWFLAKE XS HOURS
    # ============================================================================
    # The k-factor (calibration factor) accounts for workload-specific performance
    # differences between Db2 for z/OS and Snowflake. Different workload types
    # have different k-values:
    # - ELT Batch: k = 1.8 (transformation-heavy, moderate overhead)
    # - Reporting: k = 2.4 (query-heavy, higher Snowflake overhead for complex analytics)
    # - CDC: k = 1.2 (simple incremental loads, minimal overhead)
    # 
    # Formula: XS Hours = (Db2 CPU seconds/day × k) ÷ 3600
    # We divide by 3600 to convert seconds to hours
    
    wf = inp.family if inp.family in calib["workloadFamilies"] else calib["defaultFamily"]
    k = calib["workloadFamilies"][wf]["k_xs_seconds_per_db2_cpu_second"]

    xs_hours = (inp.db2_cpu_seconds_per_day * k) / 3600.0
    
    # ============================================================================
    # STEP 2 & 3: SELECT OPTIMAL WAREHOUSE SIZE
    # ============================================================================
    # Select the smallest warehouse size that can complete the workload within
    # the batch window. This minimizes costs while meeting SLA requirements.
    
    size = pick_size(xs_hours, inp.batch_window_hours, inp.concurrency, rules["sizeFactor"])
    
    # Get the credit consumption rate for the selected warehouse size
    # Credits per hour vary by size: XS=1.35, S=2.7, M=5.4, L=10.8, XL=21.6, etc.
    credits_per_hour = rules["warehouseCreditsPerHour"][size]

    # ============================================================================
    # STEP 4: CALCULATE WAREHOUSE CREDITS PER DAY
    # ============================================================================
    # Calculate actual warehouse hours needed (accounting for concurrency and size factor)
    # Then multiply by credits per hour to get daily warehouse credits
    
    need = xs_hours * max(1, inp.concurrency)
    wh_hours_day = need / rules["sizeFactor"][size]
    wh_credits_day = wh_hours_day * credits_per_hour

    # Multi-cluster warehouses: multiply credits by cluster count
    # Multi-cluster warehouses allow horizontal scaling by adding clusters
    # Each cluster consumes credits independently, so total credits = credits × clusters
    # Example: If single cluster uses 100 credits/day, 3 clusters = 300 credits/day
    if inp.warehouse_type == "multi_cluster":
        wh_credits_day = wh_credits_day * inp.cluster_count
        wh_hours_day = wh_hours_day * inp.cluster_count  # For display purposes (total hours across all clusters)

    # ============================================================================
    # STEP 5: CALCULATE CLOUD SERVICES CREDITS PER DAY
    # ============================================================================
    # Cloud Services credits cover metadata operations, query compilation, and coordination.
    # Snowflake provides a waiver: Cloud Services are free if ≤ 10% of warehouse credits.
    # There's also a cap based on warehouse hours to prevent runaway costs.
    # 
    # Formula: CS Credits = min(10% of Warehouse Credits, Cap per Hour × Warehouse Hours)
    # The cap is typically 4.4 credits/hour × warehouse hours
    
    cs_cap = rules["cloudServices"]["capCreditsPerHour"] * wh_hours_day
    waiver_pct = rules["cloudServices"].get("waiverPctOfDailyWH", 0.10)  # Default 10% waiver (configurable)
    cs_tenpct = waiver_pct * wh_credits_day
    # Take the minimum: either 10% waiver amount or the cap
    # This ensures CS credits never exceed the cap, and are waived if under 10%
    cs_credits_day = min(cs_cap, cs_tenpct)

    # ============================================================================
    # STEP 6: CALCULATE SERVERLESS CREDITS PER DAY
    # ============================================================================
    # Serverless features (Snowpipe, Search Optimization, Tasks) have different
    # pricing models than warehouses. They're billed separately and don't require
    # warehouse resources to be running.
    
    # --- Snowpipe Credits ---
    # Snowpipe pricing differs by edition:
    # - Business-Critical/VPS: Pay per GB of data processed
    # - Standard/Enterprise: Pay per 1000 files + compute multiplier for processing time
    
    is_bc_vps = inp.edition == "business_critical" or inp.edition == "vps"
    snowpipe_credits_day = 0.0
    
    if is_bc_vps:
        # Business-Critical/VPS: per-GB pricing model
        # Formula: Credits = GB/day × Rate per GB
        # Typical rate: ~0.0037 credits per GB
        snowpipe_config = pricing["serverless"].get("snowpipe", {}).get("businessCriticalVPS", {})
        rate_per_gb = snowpipe_config.get("rateCreditsPerGB", 0.0037)
        snowpipe_credits_day = (inp.snowpipe_uncompressed_gb_per_day or 0.0) * rate_per_gb
    else:
        # Standard/Enterprise: per-file + compute multiplier model
        # Formula: Credits = (Files ÷ 1000 × Rate per 1000) + (Compute Hours × Multiplier)
        # Typical rate: ~0.06 credits per 1000 files, ~1.25× multiplier for compute
        snowpipe_config = pricing["serverless"].get("snowpipe", {}).get("standardEnterprise", {})
        rate_per_1000 = snowpipe_config.get("rateCreditsPer1000Files", 0.06)
        compute_multiplier = snowpipe_config.get("multiplierCompute", 1.25)
        file_credits = (inp.snowpipe_files_per_day / 1000.0) * rate_per_1000
        compute_credits = (inp.snowpipe_compute_hours_per_day or 0.0) * compute_multiplier
        snowpipe_credits_day = file_credits + compute_credits

    # --- Search Optimization Credits ---
    # Search Optimization uses compute multipliers: 2× for compute + 1× for Cloud Services
    # Formula: Credits = Compute Hours × (2 compute + 1 Cloud Services) = Hours × 3
    # Note: This is calculated daily, not monthly (unlike some other features)
    
    searchopt_config = pricing["serverless"].get("searchOptimization", {})
    searchopt_compute_multiplier = searchopt_config.get("multiplierCompute", 2)
    searchopt_cs_multiplier = searchopt_config.get("multiplierCloudServices", 1)
    searchopt_compute_credits_day = (inp.searchopt_compute_hours_per_day or 0.0) * searchopt_compute_multiplier
    searchopt_cs_credits_day = (inp.searchopt_compute_hours_per_day or 0.0) * searchopt_cs_multiplier
    searchopt_credits_day = searchopt_compute_credits_day + searchopt_cs_credits_day

    # --- Serverless Tasks Credits ---
    # Tasks use multipliers: 0.9× for compute + 1× for Cloud Services
    # Formula: Credits = Task Hours × (0.9 compute + 1 Cloud Services) = Hours × 1.9
    # Backward compatibility: If old config format exists, use overhead rate instead
    
    tasks_config = pricing["serverless"].get("serverlessTasks", {})
    tasks_credits_day = 0.0
    if tasks_config.get("multiplierCompute") is not None:
        # New multiplier-based approach (preferred)
        tasks_compute_multiplier = tasks_config.get("multiplierCompute", 0.9)
        tasks_cs_multiplier = tasks_config.get("multiplierCloudServices", 1)
        tasks_compute_credits_day = (inp.tasks_hours_per_day or 0.0) * tasks_compute_multiplier
        tasks_cs_credits_day = (inp.tasks_hours_per_day or 0.0) * tasks_cs_multiplier
        tasks_credits_day = tasks_compute_credits_day + tasks_cs_credits_day
    else:
        # Backward compatibility: fallback to old overhead rate config
        # Old format: Credits = Task Hours × Overhead Rate (typically 0.25 credits/hour)
        tasks_credits_day = (inp.tasks_hours_per_day or 0.0) * pricing["serverless"].get("tasksOverheadCreditsPerHour", 0.25)

    # Total serverless credits = sum of all serverless features
    serverless_credits_day = snowpipe_credits_day + searchopt_credits_day + tasks_credits_day

    # ============================================================================
    # STEP 7: CALCULATE MONTHLY CREDITS
    # ============================================================================
    # Scale daily credits to monthly based on execution frequency
    # Formula: Monthly Credits = (Warehouse + Cloud Services + Serverless) × Runs per Month
    # Example: If daily credits = 100 and runs = 30/month, monthly credits = 3,000
    
    monthly_credits = (wh_credits_day + cs_credits_day + serverless_credits_day) * inp.frequency_per_month

    # ============================================================================
    # STEP 8: CONVERT CREDITS TO DOLLARS
    # ============================================================================
    # Credit pricing varies by region and edition:
    # - Standard: ~$2/credit
    # - Enterprise: ~$3/credit
    # - Business Critical: ~$4/credit
    # - VPS: ~$6/credit (falls back to Business Critical if pricing not available)
    # 
    # Formula: Monthly Dollars = Monthly Credits × Price per Credit
    
    # Handle VPS edition - fallback to business_critical if VPS pricing not available
    # VPS pricing may not be configured for all regions, so we use Business Critical as fallback
    edition_key = inp.edition
    if inp.edition == "vps" and "vps" not in region_pricing["pricePerCredit"]:
        edition_key = "business_critical"
    
    # Validate edition exists, with fallback to business_critical
    if edition_key not in region_pricing["pricePerCredit"] and "business_critical" not in region_pricing["pricePerCredit"]:
        raise ValueError(f"Invalid pricing config: edition '{edition_key}' and fallback 'business_critical' not found for region '{inp.region}'")
    price_per_credit = region_pricing["pricePerCredit"].get(edition_key) or region_pricing["pricePerCredit"]["business_critical"]

    total_monthly_credits = monthly_credits
    monthly_dollars = total_monthly_credits * price_per_credit

    # ============================================================================
    # STEP 9: CALCULATE STORAGE COSTS
    # ============================================================================
    # Storage is charged separately from compute. Snowflake charges for:
    # - Regular storage: Active data at rest
    # - Time Travel: Historical data (configurable retention period)
    # - Fail-safe: Disaster recovery backup (7-day retention)
    # 
    # All storage types are charged at the same rate per TB/month
    # Typical rate: ~$23/TB/month (varies by region)
    # Formula: Storage Cost = (Regular TB + Time Travel TB + Fail-safe TB) × Rate per TB
    
    storage_rate = region_pricing.get("storagePerTBMonth", 0.0)
    regular_storage_monthly = (inp.uncompressed_tb_at_rest or 0.0) * storage_rate
    time_travel_storage_monthly = (inp.time_travel_tb or 0.0) * storage_rate
    failsafe_storage_monthly = (inp.failsafe_tb or 0.0) * storage_rate
    storage_monthly = regular_storage_monthly + time_travel_storage_monthly + failsafe_storage_monthly

    # ============================================================================
    # STEP 10: CALCULATE DATA TRANSFER (EGRESS) COSTS
    # ============================================================================
    # Snowflake charges for data leaving their platform (egress), not for data entering (ingress).
    # Egress pricing varies by transfer route:
    # - Intra-Region: $0/TB (within same region)
    # - Inter-Region: ~$20/TB (between regions, same cloud provider)
    # - Cross-Cloud: ~$90/TB (between cloud providers)
    # - Internet: ~$90/TB (to public internet)
    # - Account Transfer: ~$20/TB (between Snowflake accounts)
    # 
    # Formula: Transfer Cost = Egress TB × Rate per TB (based on route)
    
    egress_rates = region_pricing.get("egressPerTB", {})
    # Map route names to existing pricing keys if needed (for backward compatibility)
    egress_route_key = inp.egress_route
    if inp.egress_route == "crossCloud" and "crossCloud" not in egress_rates:
        egress_route_key = "internet"  # Cross-cloud typically priced like internet
    if inp.egress_route == "accountTransfer" and "accountTransfer" not in egress_rates:
        egress_route_key = "interRegion"  # Account transfer typically priced like inter-region
    egress_rate = egress_rates.get(egress_route_key) or egress_rates.get(inp.egress_route) or 0.0
    transfer_monthly = (inp.egress_tb or 0.0) * egress_rate

    # ============================================================================
    # STEP 11: GRAND TOTAL
    # ============================================================================
    # Sum all cost components: Compute + Storage + Transfer
    # This is the complete monthly cost estimate for budget planning
    
    grand_total = monthly_dollars + storage_monthly + transfer_monthly

    # ============================================================================
    # RETURN RESULTS
    # ============================================================================
    # Return comprehensive result dictionary with all calculation details
    # This allows CLI and other scripts to display step-by-step breakdowns and detailed cost analysis
    

    return {
        # Warehouse selection details (what size was chosen and why)
        "selection": {"size": size, "creditsPerHour": credits_per_hour, "whHoursDay": wh_hours_day, "clusterCount": inp.cluster_count},
        
        # Daily credit breakdown (for understanding daily consumption patterns)
        "daily": {
            "xsHours": xs_hours,                    # XS-equivalent hours (after k-factor conversion)
            "whCreditsDay": wh_credits_day,          # Warehouse credits per day
            "csCreditsDay": cs_credits_day,          # Cloud Services credits per day
            "serverlessCreditsDay": serverless_credits_day  # Total serverless credits per day
        },
        
        # Monthly cost breakdown (for budget planning)
        "monthly": {
            "credits": total_monthly_credits,           # Total monthly credits
            "dollarsCompute": monthly_dollars,          # Compute cost (credits × price)
            "dollarsStorage": storage_monthly,          # Total storage cost
            "dollarsStorageRegular": regular_storage_monthly,      # Regular storage cost (breakdown)
            "dollarsStorageTimeTravel": time_travel_storage_monthly, # Time Travel storage cost (breakdown)
            "dollarsStorageFailsafe": failsafe_storage_monthly,   # Fail-safe storage cost (breakdown)
            "dollarsTransfer": transfer_monthly,       # Data transfer (egress) cost
            "grandTotal": grand_total                    # Grand total monthly cost
        },
        
        # Echo of input parameters (for reference and validation)
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

