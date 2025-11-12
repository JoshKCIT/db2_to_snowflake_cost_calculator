/**
 * Copyright (c) 2025 JoshKCIT
 * 
 * Core calculation logic for Snowflake Budget Calculator
 */
(function(global){
  "use strict";

  const pickSize = (xsHours, windowH, concurrency, sizeFactor) => {
    const need = xsHours * Math.max(1, concurrency);
    const order = ["XS","S","M","L","XL","2XL","3XL","4XL"];
    for (const s of order) {
      const whHours = need / sizeFactor[s];
      if (whHours <= windowH) return s;
    }
    return "4XL";
  };

  const compute = (inp, pricing, rules, calib) => {
    // Validate inputs to prevent runtime errors
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

    const k = calib.workloadFamilies[inp.family]?.k_xs_seconds_per_db2_cpu_second
      ?? calib.workloadFamilies[calib.defaultFamily].k_xs_seconds_per_db2_cpu_second;

    const xsHours = (inp.db2CpuSecondsPerDay * k) / 3600.0;
    const size = pickSize(xsHours, inp.batchWindowHours, inp.concurrency, rules.sizeFactor);
    const creditsPerHour = rules.warehouseCreditsPerHour[size];

    const need = xsHours * Math.max(1, inp.concurrency);
    let whHoursDay = need / rules.sizeFactor[size];
    let whCreditsDay = whHoursDay * creditsPerHour;

    // Multi-cluster support: multiply credits by cluster count
    if (inp.warehouseType === "multi_cluster") {
      whCreditsDay = whCreditsDay * (inp.clusterCount || 1);
      whHoursDay = whHoursDay * (inp.clusterCount || 1); // For display purposes
    }

    // Cloud Services calculation with configurable waiver percentage
    const csCap = rules.cloudServices.capCreditsPerHour * whHoursDay;
    const waiverPct = rules.cloudServices.waiverPctOfDailyWH || 0.10; // Backward compatibility
    const csTenPct = waiverPct * whCreditsDay;
    const csCreditsDay = Math.min(csCap, csTenPct);

    // Snowpipe calculation - edition-specific logic
    const isBCVPS = inp.edition === "business_critical" || inp.edition === "vps";
    let snowpipeCreditsDay = 0.0;
    
    if (isBCVPS) {
      // Business-Critical/VPS: per-GB model
      const snowpipeConfig = pricing.serverless?.snowpipe?.businessCriticalVPS || {};
      const ratePerGB = snowpipeConfig.rateCreditsPerGB || 0.0037;
      snowpipeCreditsDay = (inp.snowpipeUncompressedGBPerDay || 0) * ratePerGB;
    } else {
      // Standard/Enterprise: per-file + compute multiplier
      const snowpipeConfig = pricing.serverless?.snowpipe?.standardEnterprise || {};
      const ratePer1000 = snowpipeConfig.rateCreditsPer1000Files || 0.06;
      const computeMultiplier = snowpipeConfig.multiplierCompute || 1.25;
      const fileCredits = (inp.snowpipeFilesPerDay / 1000.0) * ratePer1000;
      const computeCredits = (inp.snowpipeComputeHoursPerDay || 0) * computeMultiplier;
      snowpipeCreditsDay = fileCredits + computeCredits;
    }

    // Search Optimization: compute multipliers (daily, not monthly)
    const searchOptConfig = pricing.serverless?.searchOptimization || {};
    const searchOptComputeMultiplier = searchOptConfig.multiplierCompute || 2;
    const searchOptCSMultiplier = searchOptConfig.multiplierCloudServices || 1;
    const searchOptComputeCreditsDay = (inp.searchOptComputeHoursPerDay || 0) * searchOptComputeMultiplier;
    const searchOptCSCreditsDay = (inp.searchOptComputeHoursPerDay || 0) * searchOptCSMultiplier;
    const searchOptCreditsDay = searchOptComputeCreditsDay + searchOptCSCreditsDay;

    // Serverless Tasks: correct multipliers
    const tasksConfig = pricing.serverless?.serverlessTasks || {};
    let tasksCreditsDay = 0;
    if (tasksConfig.multiplierCompute !== undefined) {
      const tasksComputeMultiplier = tasksConfig.multiplierCompute || 0.9;
      const tasksCSMultiplier = tasksConfig.multiplierCloudServices || 1;
      const tasksComputeCreditsDay = (inp.tasksHoursPerDay || 0) * tasksComputeMultiplier;
      const tasksCSCreditsDay = (inp.tasksHoursPerDay || 0) * tasksCSMultiplier;
      tasksCreditsDay = tasksComputeCreditsDay + tasksCSCreditsDay;
    } else {
      // Backward compatibility: fallback to old config
      tasksCreditsDay = (inp.tasksHoursPerDay || 0) * (pricing.serverless.tasksOverheadCreditsPerHour || 0.25);
    }

    const serverlessCreditsDay = snowpipeCreditsDay + searchOptCreditsDay + tasksCreditsDay;

    const monthlyCredits = (whCreditsDay + csCreditsDay + serverlessCreditsDay) * inp.frequencyPerMonth;

    // Handle VPS edition - fallback to business_critical if VPS pricing not available
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

    // Storage costs: regular storage + Time Travel + Fail-safe (all charged at same rate)
    const storageRate = regionPricing.storagePerTBMonth || 0;
    const regularStorageMonthly = (inp.uncompressedTBAtRest || 0) * storageRate;
    const timeTravelStorageMonthly = (inp.timeTravelTB || 0) * storageRate;
    const failsafeStorageMonthly = (inp.failsafeTB || 0) * storageRate;
    const storageMonthly = regularStorageMonthly + timeTravelStorageMonthly + failsafeStorageMonthly;

    // Handle egress route - support new transfer types
    const egressRates = regionPricing.egressPerTB || {};
    // Map new route names to existing ones if needed
    let egressRouteKey = inp.egressRoute;
    if (inp.egressRoute === "crossCloud" && !egressRates.crossCloud) {
      egressRouteKey = "internet"; // Cross-cloud typically priced like internet
    }
    if (inp.egressRoute === "accountTransfer" && !egressRates.accountTransfer) {
      egressRouteKey = "interRegion"; // Account transfer typically priced like inter-region
    }
    const egressRate = egressRates[egressRouteKey] || egressRates[inp.egressRoute] || 0;
    const transferMonthly = (inp.egressTB || 0) * egressRate;

    const grandTotal = monthlyDollars + storageMonthly + transferMonthly;

    return {
      selection: { size, creditsPerHour, whHoursDay, clusterCount: inp.clusterCount || 1 },
      daily: { 
        xsHours, 
        whCreditsDay, 
        csCreditsDay, 
        serverlessCreditsDay,
        snowpipeCreditsDay,
        searchOptCreditsDay,
        tasksCreditsDay
      },
      monthly: {
        credits: totalMonthlyCredits,
        dollarsCompute: monthlyDollars,
        dollarsStorage: storageMonthly,
        dollarsStorageRegular: regularStorageMonthly,
        dollarsStorageTimeTravel: timeTravelStorageMonthly,
        dollarsStorageFailsafe: failsafeStorageMonthly,
        dollarsTransfer: transferMonthly,
        grandTotal
      },
      inputsEcho: inp
    };
  };

  global.Calc = { compute };
})(window);

