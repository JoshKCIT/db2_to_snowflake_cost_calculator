/**
 * Copyright (c) 2025 JoshKCIT
 * 
 * Core calculation logic for Snowflake Budget Calculator
 * 
 * This file contains the core calculation engine that converts Db2 for z/OS metrics
 * into Snowflake cost estimates. It implements the 10-step calculation methodology:
 * 1. Convert Db2 CPU seconds to Snowflake XS hours using k-factor calibration
 * 2. Account for concurrent workload requirements
 * 3. Select optimal warehouse size based on batch window constraints
 * 4. Calculate warehouse credits consumed
 * 5. Calculate Cloud Services credits (with 10% waiver rule)
 * 6. Calculate serverless credits (Snowpipe, Search Optimization, Tasks)
 * 7. Scale to monthly credits based on execution frequency
 * 8. Convert credits to dollars using region/edition pricing
 * 9. Add storage costs (regular + Time Travel + Fail-safe)
 * 10. Add data transfer (egress) costs
 * 
 * This module is used by both the browser UI (index.html) and can be imported
 * by other JavaScript modules. It exports a global Calc object with a compute() method.
 */
(function(global){
  "use strict";

  /**
   * Selects the optimal Snowflake warehouse size based on workload requirements.
   * 
   * This function implements the warehouse sizing algorithm: it finds the smallest
   * warehouse size that can complete the workload within the specified batch window.
   * Larger warehouses cost more per hour but complete work faster, so we select
   * the smallest size that meets the time constraint to minimize costs.
   * 
   * Business Logic:
   * - Each warehouse size has a "size factor" (XS=1×, S=2×, M=4×, L=8×, etc.)
   * - A 2× warehouse completes work in half the time of XS
   * - We multiply XS hours by concurrency to get total compute need
   * - We divide total need by size factor to get actual warehouse hours
   * - We select the smallest size where warehouse hours ≤ batch window
   * 
   * @param {number} xsHours - XS-equivalent hours needed (after k-factor conversion)
   * @param {number} windowH - Batch window constraint in hours (SLA requirement)
   * @param {number} concurrency - Number of concurrent jobs running simultaneously
   * @param {Object} sizeFactor - Object mapping warehouse sizes to their speed factors
   *                              (e.g., {XS: 1, S: 2, M: 4, L: 8, XL: 16, "2XL": 32, ...})
   * @returns {string} Warehouse size code (e.g., "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL")
   * 
   * @example
   * // If you need 36 XS hours with 2 concurrent jobs in a 4-hour window:
   * // Total need = 36 × 2 = 72 XS-equivalent hours
   * // Try XL (16×): 72 ÷ 16 = 4.5 hours (too long)
   * // Try 2XL (32×): 72 ÷ 32 = 2.25 hours (fits in 4h window) ✓
   * pickSize(36, 4, 2, {XS:1, S:2, M:4, L:8, XL:16, "2XL":32}) // Returns "2XL"
   */
  const pickSize = (xsHours, windowH, concurrency, sizeFactor) => {
    // Calculate total compute need: XS hours × concurrent jobs
    // Concurrency represents jobs that must run simultaneously, not sequentially
    // Example: 2 concurrent jobs means we need 2× the compute capacity
    const need = xsHours * Math.max(1, concurrency);
    
    // Try warehouse sizes from smallest to largest (cost-optimization strategy)
    // We want the smallest size that meets the time constraint
    const order = ["XS","S","M","L","XL","2XL","3XL","4XL"];
    
    for (const s of order) {
      // Calculate how many hours this warehouse size would take
      // Formula: Total Need ÷ Size Factor = Warehouse Hours
      // Example: 72 XS-hours ÷ 16 (XL factor) = 4.5 hours
      const whHours = need / sizeFactor[s];
      
      // If this size completes work within the batch window, use it
      // This is the smallest size that meets the SLA requirement
      if (whHours <= windowH) return s;
    }
    
    // If even 4XL can't meet the window, return 4XL anyway
    // (This indicates the workload may need to be split or window extended)
    return "4XL";
  };

  /**
   * Main calculation function: converts Db2 for z/OS metrics to Snowflake monthly cost estimate.
   * 
   * This is the core calculation engine that implements the complete cost estimation methodology.
   * It performs all 10 calculation steps in sequence and returns a comprehensive result object
   * containing warehouse selection, daily credits, monthly credits, and cost breakdowns.
   * 
   * Calculation Flow:
   * 1. Validates configuration files (pricing, rules, calibration)
   * 2. Converts Db2 CPU seconds to Snowflake XS hours using k-factor
   * 3. Selects optimal warehouse size based on batch window
   * 4. Calculates warehouse credits (with multi-cluster support)
   * 5. Calculates Cloud Services credits (with 10% waiver rule)
   * 6. Calculates serverless credits (Snowpipe, Search Optimization, Tasks)
   * 7. Scales daily credits to monthly based on execution frequency
   * 8. Converts credits to dollars using region/edition pricing
   * 9. Calculates storage costs (regular + Time Travel + Fail-safe)
   * 10. Calculates data transfer (egress) costs
   * 11. Sums all costs for grand total
   * 
   * @param {Object} inp - Input parameters object containing:
   *   @param {number} inp.db2CpuSecondsPerDay - Db2 for z/OS CPU seconds consumed per day
   *   @param {number} inp.batchWindowHours - Batch window constraint in hours (SLA requirement)
   *   @param {number} inp.concurrency - Number of concurrent jobs running simultaneously
   *   @param {number} inp.uncompressedTBAtRest - Uncompressed data size in TB (for storage costs)
   *   @param {number} inp.frequencyPerMonth - How many times per month the workload runs
   *   @param {string} inp.region - Snowflake region code (e.g., "aws-us-east-1")
   *   @param {string} inp.edition - Snowflake edition ("standard", "enterprise", "business_critical", "vps")
   *   @param {string} inp.family - Workload family for k-factor selection ("elt_batch", "reporting", "cdc")
   *   @param {number} inp.egressTB - Data egress volume in TB/month
   *   @param {string} inp.egressRoute - Egress route type ("intraRegion", "interRegion", "crossCloud", "internet", "accountTransfer")
   *   @param {number} inp.timeTravelTB - Time Travel storage in TB/month
   *   @param {number} inp.failsafeTB - Fail-safe storage in TB/month
   *   @param {number} inp.snowpipeFilesPerDay - Snowpipe files processed per day (Standard/Enterprise only)
   *   @param {number} inp.snowpipeComputeHoursPerDay - Snowpipe compute hours per day (Standard/Enterprise only)
   *   @param {number} inp.snowpipeUncompressedGBPerDay - Snowpipe data volume in GB/day (Business-Critical/VPS only)
   *   @param {number} inp.searchOptComputeHoursPerDay - Search Optimization compute hours per day
   *   @param {number} inp.tasksHoursPerDay - Serverless Tasks hours per day
   *   @param {string} inp.warehouseType - Warehouse type ("standard", "multi_cluster", "serverless")
   *   @param {number} inp.clusterCount - Number of clusters (for multi-cluster warehouses)
   * @param {Object} pricing - Pricing configuration object (from config/pricing.json)
   * @param {Object} rules - Rules configuration object (from config/rules.json)
   * @param {Object} calib - Calibration configuration object (from config/calibration.json)
   * @returns {Object} Result object containing:
   *   @returns {Object} selection - Warehouse selection details (size, creditsPerHour, whHoursDay, clusterCount)
   *   @returns {Object} daily - Daily credit breakdown (xsHours, whCreditsDay, csCreditsDay, serverlessCreditsDay, ...)
   *   @returns {Object} monthly - Monthly cost breakdown (credits, dollarsCompute, dollarsStorage, dollarsTransfer, grandTotal, ...)
   *   @returns {Object} inputsEcho - Echo of input parameters for reference
   * 
   * @throws {Error} If configuration is invalid or required data is missing
   */
  const compute = (inp, pricing, rules, calib) => {
    // ============================================================================
    // STEP 0: VALIDATE CONFIGURATION FILES
    // ============================================================================
    // Ensure all required configuration data is present before starting calculations
    // This prevents cryptic runtime errors and provides clear error messages
    
    if (!pricing || !pricing.regions || !pricing.regions[inp.region]) {
      throw new Error(`Invalid pricing config: region '${inp.region}' not found`);
    }
    
    const regionPricing = pricing.regions[inp.region];
    if (!regionPricing.pricePerCredit) {
      throw new Error(`Invalid pricing config: pricePerCredit not found for region '${inp.region}'`);
    }
    
    if (!calib || !calib.workloadFamilies) {
      throw new Error("Invalid calibration config: workloadFamilies not found");
    }
    
    if (!rules || !rules.sizeFactor || !rules.warehouseCreditsPerHour) {
      throw new Error("Invalid rules config: required fields missing");
    }

    // ============================================================================
    // STEP 1: CONVERT DB2 FOR Z/OS CPU SECONDS TO SNOWFLAKE XS HOURS
    // ============================================================================
    // The k-factor (calibration factor) accounts for workload-specific performance
    // differences between Db2 for z/OS and Snowflake. Different workload types
    // have different k-values:
    // - ELT Batch: k = 1.8 (transformation-heavy, moderate overhead)
    // - Reporting: k = 2.4 (query-heavy, higher Snowflake overhead for complex analytics)
    // - CDC: k = 1.2 (simple incremental loads, minimal overhead)
    // 
    // Formula: XS Hours = (Db2 CPU seconds/day × k) ÷ 3600
    // We divide by 3600 to convert seconds to hours
    
    const k = calib.workloadFamilies[inp.family]?.k_xs_seconds_per_db2_cpu_second
      ?? calib.workloadFamilies[calib.defaultFamily].k_xs_seconds_per_db2_cpu_second;

    const xsHours = (inp.db2CpuSecondsPerDay * k) / 3600.0;
    
    // ============================================================================
    // STEP 2 & 3: SELECT OPTIMAL WAREHOUSE SIZE
    // ============================================================================
    // Select the smallest warehouse size that can complete the workload within
    // the batch window. This minimizes costs while meeting SLA requirements.
    
    const size = pickSize(xsHours, inp.batchWindowHours, inp.concurrency, rules.sizeFactor);
    
    // Get the credit consumption rate for the selected warehouse size
    // Credits per hour vary by size: XS=1.35, S=2.7, M=5.4, L=10.8, XL=21.6, etc.
    const creditsPerHour = rules.warehouseCreditsPerHour[size];

    // ============================================================================
    // STEP 4: CALCULATE WAREHOUSE CREDITS PER DAY
    // ============================================================================
    // Calculate actual warehouse hours needed (accounting for concurrency and size factor)
    // Then multiply by credits per hour to get daily warehouse credits
    
    const need = xsHours * Math.max(1, inp.concurrency);
    let whHoursDay = need / rules.sizeFactor[size];
    let whCreditsDay = whHoursDay * creditsPerHour;

    // Multi-cluster warehouses: multiply credits by cluster count
    // Multi-cluster warehouses allow horizontal scaling by adding clusters
    // Each cluster consumes credits independently, so total credits = credits × clusters
    // Example: If single cluster uses 100 credits/day, 3 clusters = 300 credits/day
    if (inp.warehouseType === "multi_cluster") {
      whCreditsDay = whCreditsDay * (inp.clusterCount || 1);
      whHoursDay = whHoursDay * (inp.clusterCount || 1); // For display purposes (total hours across all clusters)
    }

    // ============================================================================
    // STEP 5: CALCULATE CLOUD SERVICES CREDITS PER DAY
    // ============================================================================
    // Cloud Services credits cover metadata operations, query compilation, and coordination.
    // Snowflake provides a waiver: Cloud Services are free if ≤ 10% of warehouse credits.
    // There's also a cap based on warehouse hours to prevent runaway costs.
    // 
    // Formula: CS Credits = min(10% of Warehouse Credits, Cap per Hour × Warehouse Hours)
    // The cap is typically 4.4 credits/hour × warehouse hours
    
    const csCap = rules.cloudServices.capCreditsPerHour * whHoursDay;
    const waiverPct = rules.cloudServices.waiverPctOfDailyWH || 0.10; // Default 10% waiver (configurable)
    const csTenPct = waiverPct * whCreditsDay;
    // Take the minimum: either 10% waiver amount or the cap
    // This ensures CS credits never exceed the cap, and are waived if under 10%
    const csCreditsDay = Math.min(csCap, csTenPct);

    // ============================================================================
    // STEP 6: CALCULATE SERVERLESS CREDITS PER DAY
    // ============================================================================
    // Serverless features (Snowpipe, Search Optimization, Tasks) have different
    // pricing models than warehouses. They're billed separately and don't require
    // warehouse resources to be running.
    
    // --- Snowpipe Credits ---
    // Snowpipe pricing differs by edition:
    // - Business-Critical/VPS: Pay per GB of data processed
    // - Standard/Enterprise: Pay per 1000 files + compute multiplier for processing time
    
    const isBCVPS = inp.edition === "business_critical" || inp.edition === "vps";
    let snowpipeCreditsDay = 0.0;
    
    if (isBCVPS) {
      // Business-Critical/VPS: per-GB pricing model
      // Formula: Credits = GB/day × Rate per GB
      // Typical rate: ~0.0037 credits per GB
      const snowpipeConfig = pricing.serverless?.snowpipe?.businessCriticalVPS || {};
      const ratePerGB = snowpipeConfig.rateCreditsPerGB || 0.0037;
      snowpipeCreditsDay = (inp.snowpipeUncompressedGBPerDay || 0) * ratePerGB;
    } else {
      // Standard/Enterprise: per-file + compute multiplier model
      // Formula: Credits = (Files ÷ 1000 × Rate per 1000) + (Compute Hours × Multiplier)
      // Typical rate: ~0.06 credits per 1000 files, ~1.25× multiplier for compute
      const snowpipeConfig = pricing.serverless?.snowpipe?.standardEnterprise || {};
      const ratePer1000 = snowpipeConfig.rateCreditsPer1000Files || 0.06;
      const computeMultiplier = snowpipeConfig.multiplierCompute || 1.25;
      const fileCredits = (inp.snowpipeFilesPerDay / 1000.0) * ratePer1000;
      const computeCredits = (inp.snowpipeComputeHoursPerDay || 0) * computeMultiplier;
      snowpipeCreditsDay = fileCredits + computeCredits;
    }

    // --- Search Optimization Credits ---
    // Search Optimization uses compute multipliers: 2× for compute + 1× for Cloud Services
    // Formula: Credits = Compute Hours × (2 compute + 1 Cloud Services) = Hours × 3
    // Note: This is calculated daily, not monthly (unlike some other features)
    
    const searchOptConfig = pricing.serverless?.searchOptimization || {};
    const searchOptComputeMultiplier = searchOptConfig.multiplierCompute || 2;
    const searchOptCSMultiplier = searchOptConfig.multiplierCloudServices || 1;
    const searchOptComputeCreditsDay = (inp.searchOptComputeHoursPerDay || 0) * searchOptComputeMultiplier;
    const searchOptCSCreditsDay = (inp.searchOptComputeHoursPerDay || 0) * searchOptCSMultiplier;
    const searchOptCreditsDay = searchOptComputeCreditsDay + searchOptCSCreditsDay;

    // --- Serverless Tasks Credits ---
    // Tasks use multipliers: 0.9× for compute + 1× for Cloud Services
    // Formula: Credits = Task Hours × (0.9 compute + 1 Cloud Services) = Hours × 1.9
    // Backward compatibility: If old config format exists, use overhead rate instead
    
    const tasksConfig = pricing.serverless?.serverlessTasks || {};
    let tasksCreditsDay = 0;
    if (tasksConfig.multiplierCompute !== undefined) {
      // New multiplier-based approach (preferred)
      const tasksComputeMultiplier = tasksConfig.multiplierCompute || 0.9;
      const tasksCSMultiplier = tasksConfig.multiplierCloudServices || 1;
      const tasksComputeCreditsDay = (inp.tasksHoursPerDay || 0) * tasksComputeMultiplier;
      const tasksCSCreditsDay = (inp.tasksHoursPerDay || 0) * tasksCSMultiplier;
      tasksCreditsDay = tasksComputeCreditsDay + tasksCSCreditsDay;
    } else {
      // Backward compatibility: fallback to old overhead rate config
      // Old format: Credits = Task Hours × Overhead Rate (typically 0.25 credits/hour)
      tasksCreditsDay = (inp.tasksHoursPerDay || 0) * (pricing.serverless.tasksOverheadCreditsPerHour || 0.25);
    }

    // Total serverless credits = sum of all serverless features
    const serverlessCreditsDay = snowpipeCreditsDay + searchOptCreditsDay + tasksCreditsDay;

    // ============================================================================
    // STEP 7: CALCULATE MONTHLY CREDITS
    // ============================================================================
    // Scale daily credits to monthly based on execution frequency
    // Formula: Monthly Credits = (Warehouse + Cloud Services + Serverless) × Runs per Month
    // Example: If daily credits = 100 and runs = 30/month, monthly credits = 3,000
    
    const monthlyCredits = (whCreditsDay + csCreditsDay + serverlessCreditsDay) * inp.frequencyPerMonth;

    // ============================================================================
    // STEP 8: CONVERT CREDITS TO DOLLARS
    // ============================================================================
    // Credit pricing varies by region and edition:
    // - Standard: ~$2/credit
    // - Enterprise: ~$3/credit
    // - Business Critical: ~$4/credit
    // - VPS: ~$6/credit (falls back to Business Critical if pricing not available)
    // 
    // Formula: Monthly Dollars = Monthly Credits × Price per Credit
    
    // Handle VPS edition - fallback to business_critical if VPS pricing not available
    // VPS pricing may not be configured for all regions, so we use Business Critical as fallback
    const editionKey = inp.edition === "vps" && !regionPricing.pricePerCredit.vps 
      ? "business_critical" 
      : inp.edition;
    
    // Validate edition exists, with fallback to business_critical
    if (!regionPricing.pricePerCredit[editionKey] && !regionPricing.pricePerCredit.business_critical) {
      throw new Error(`Invalid pricing config: edition '${editionKey}' and fallback 'business_critical' not found for region '${inp.region}'`);
    }
    const pricePerCredit = regionPricing.pricePerCredit[editionKey] || regionPricing.pricePerCredit.business_critical;

    const totalMonthlyCredits = monthlyCredits;
    const monthlyDollars = totalMonthlyCredits * pricePerCredit;

    // ============================================================================
    // STEP 9: CALCULATE STORAGE COSTS
    // ============================================================================
    // Storage is charged separately from compute. Snowflake charges for:
    // - Regular storage: Active data at rest
    // - Time Travel: Historical data (configurable retention period)
    // - Fail-safe: Disaster recovery backup (7-day retention)
    // 
    // All storage types are charged at the same rate per TB/month
    // Typical rate: ~$23/TB/month (varies by region)
    // Formula: Storage Cost = (Regular TB + Time Travel TB + Fail-safe TB) × Rate per TB
    
    const storageRate = regionPricing.storagePerTBMonth || 0;
    const regularStorageMonthly = (inp.uncompressedTBAtRest || 0) * storageRate;
    const timeTravelStorageMonthly = (inp.timeTravelTB || 0) * storageRate;
    const failsafeStorageMonthly = (inp.failsafeTB || 0) * storageRate;
    const storageMonthly = regularStorageMonthly + timeTravelStorageMonthly + failsafeStorageMonthly;

    // ============================================================================
    // STEP 10: CALCULATE DATA TRANSFER (EGRESS) COSTS
    // ============================================================================
    // Snowflake charges for data leaving their platform (egress), not for data entering (ingress).
    // Egress pricing varies by transfer route:
    // - Intra-Region: $0/TB (within same region)
    // - Inter-Region: ~$20/TB (between regions, same cloud provider)
    // - Cross-Cloud: ~$90/TB (between cloud providers)
    // - Internet: ~$90/TB (to public internet)
    // - Account Transfer: ~$20/TB (between Snowflake accounts)
    // 
    // Formula: Transfer Cost = Egress TB × Rate per TB (based on route)
    
    const egressRates = regionPricing.egressPerTB || {};
    // Map route names to existing pricing keys if needed (for backward compatibility)
    let egressRouteKey = inp.egressRoute;
    if (inp.egressRoute === "crossCloud" && !egressRates.crossCloud) {
      egressRouteKey = "internet"; // Cross-cloud typically priced like internet
    }
    if (inp.egressRoute === "accountTransfer" && !egressRates.accountTransfer) {
      egressRouteKey = "interRegion"; // Account transfer typically priced like inter-region
    }
    const egressRate = egressRates[egressRouteKey] || egressRates[inp.egressRoute] || 0;
    const transferMonthly = (inp.egressTB || 0) * egressRate;

    // ============================================================================
    // STEP 11: GRAND TOTAL
    // ============================================================================
    // Sum all cost components: Compute + Storage + Transfer
    // This is the complete monthly cost estimate for budget planning
    
    const grandTotal = monthlyDollars + storageMonthly + transferMonthly;

    // ============================================================================
    // RETURN RESULTS
    // ============================================================================
    // Return comprehensive result object with all calculation details
    // This allows the UI to display step-by-step breakdowns and detailed cost analysis
    
    return {
      // Warehouse selection details (what size was chosen and why)
      selection: { size, creditsPerHour, whHoursDay, clusterCount: inp.clusterCount || 1 },
      
      // Daily credit breakdown (for understanding daily consumption patterns)
      daily: { 
        xsHours,                    // XS-equivalent hours (after k-factor conversion)
        whCreditsDay,               // Warehouse credits per day
        csCreditsDay,               // Cloud Services credits per day
        serverlessCreditsDay,       // Total serverless credits per day
        snowpipeCreditsDay,         // Snowpipe credits per day (breakdown)
        searchOptCreditsDay,        // Search Optimization credits per day (breakdown)
        tasksCreditsDay             // Tasks credits per day (breakdown)
      },
      
      // Monthly cost breakdown (for budget planning)
      monthly: {
        credits: totalMonthlyCredits,           // Total monthly credits
        dollarsCompute: monthlyDollars,         // Compute cost (credits × price)
        dollarsStorage: storageMonthly,         // Total storage cost
        dollarsStorageRegular: regularStorageMonthly,      // Regular storage cost (breakdown)
        dollarsStorageTimeTravel: timeTravelStorageMonthly, // Time Travel storage cost (breakdown)
        dollarsStorageFailsafe: failsafeStorageMonthly,   // Fail-safe storage cost (breakdown)
        dollarsTransfer: transferMonthly,       // Data transfer (egress) cost
        grandTotal                               // Grand total monthly cost
      },
      
      // Echo of input parameters (for reference and validation)
      inputsEcho: inp
    };
  };

  // Export the calculation engine to the global window object
  // This allows index.html and other scripts to access it via window.Calc.compute()
  global.Calc = { compute };
})(window);

