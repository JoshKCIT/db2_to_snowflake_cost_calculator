/**
 * Copyright (c) 2025 JoshKCIT
 * 
 * Main application logic for Snowflake Budget Calculator
 * 
 * This file handles the user interface logic for the calculator web application.
 * It manages:
 * - DOM element references and initialization
 * - Configuration loading and refresh (from config-editor.js)
 * - User input collection and validation
 * - Calculation triggering and result display
 * - Export functionality (JSON/CSV)
 * - Dynamic UI updates (region filtering, cluster count visibility)
 * 
 * This script runs in the browser and interacts with:
 * - index.html: The HTML structure and UI elements
 * - lib/calc.js: The core calculation engine (window.Calc.compute())
 * - js/config-editor.js: Configuration management (window.CONFIG_*)
 */
(function(){
  "use strict";

  // ============================================================================
  // DOM ELEMENT REFERENCES
  // ============================================================================
  // Get references to key HTML elements that we'll interact with
  // These are initialized when the page loads
  
  const regionSel = document.getElementById("region");           // Region dropdown
  const familySel = document.getElementById("family");           // Workload family dropdown
  const cloudProviderSel = document.getElementById("cloud_provider"); // Cloud provider dropdown (AWS/Azure/GCP)
  const outEl = document.getElementById("out");                  // Raw JSON output display element

  // ============================================================================
  // CONFIGURATION MANAGEMENT
  // ============================================================================
  // Configuration is loaded from window.CONFIG_* variables set by config-editor.js
  // These variables are populated from localStorage (if user has custom configs)
  // or from default config files (config/pricing.js, config/rules.js, config/calibration.js)
  // 
  // We maintain local copies that can be refreshed when configs change
  
  let defaultPricing = window.CONFIG_PRICING || {
    regions: {
      "aws-us-east-1": {
        pricePerCredit: { standard: 2.00, enterprise: 3.00, business_critical: 4.00, vps: 5.00 },
        storagePerTBMonth: 23.00,
        egressPerTB: { intraRegion: 0.00, interRegion: 20.00, crossCloud: 90.00, internet: 90.00, accountTransfer: 20.00 }
      }
    },
    serverless: {
      snowpipePer1000FilesCredits: 0.05,
      searchOptimizationPerTBMonthCredits: 1.00,
      tasksOverheadCreditsPerHour: 0.25
    }
  };

  let defaultRules = window.CONFIG_RULES || {
    warehouseCreditsPerHour: {
      XS: 1.35, S: 2.7, M: 5.4, L: 10.8, XL: 21.6, "2XL": 43.2, "3XL": 86.4, "4XL": 172.8
    },
    sizeFactor: { XS:1, S:2, M:4, L:8, XL:16, "2XL":32, "3XL":64, "4XL":128 },
    cloudServices: { capCreditsPerHour: 4.4 }
  };

  let defaultCalib = window.CONFIG_CALIBRATION || {
    workloadFamilies: {
      "elt_batch": { k_xs_seconds_per_db2_cpu_second: 1.8, notes: "placeholder" },
      "reporting": { k_xs_seconds_per_db2_cpu_second: 2.4, notes: "placeholder" },
      "cdc": { k_xs_seconds_per_db2_cpu_second: 1.2, notes: "placeholder" }
    },
    defaultFamily: "elt_batch"
  };

  /**
   * Refreshes configuration data from window.CONFIG_* variables.
   * 
   * This function is called when the user updates configuration in the Configuration tab.
   * It updates local config copies and refreshes dropdown menus to reflect changes.
   * 
   * Why this is needed: The Configuration Editor (config-editor.js) updates window.CONFIG_*
   * variables when users save changes. This function syncs those changes to the calculator.
   */
  function refreshConfigs() {
    // Update local config copies from global window variables
    if (window.CONFIG_PRICING) {
      defaultPricing = window.CONFIG_PRICING;
    }
    if (window.CONFIG_RULES) {
      defaultRules = window.CONFIG_RULES;
    }
    if (window.CONFIG_CALIBRATION) {
      defaultCalib = window.CONFIG_CALIBRATION;
    }
    
    // Refresh dropdown menus to show updated options
    populateRegions(cloudProviderSel.value);
    familySel.innerHTML = '';
    for (const f of Object.keys(defaultCalib.workloadFamilies)) {
      const opt = document.createElement("option");
      opt.value = f; opt.textContent = f;
      familySel.appendChild(opt);
    }
  }

  // Listen for config updates - check periodically and on window focus
  // This allows the calculator to pick up changes made in the Configuration tab
  // without requiring a page refresh
  setInterval(() => {
    if (window.CONFIG_PRICING && window.CONFIG_PRICING !== defaultPricing) {
      refreshConfigs();
    }
  }, 500);
  window.addEventListener('focus', refreshConfigs);

  /**
   * Populates the region dropdown based on selected cloud provider.
   * 
   * Regions are filtered to show only those matching the cloud provider prefix
   * (e.g., "aws-" for AWS regions). If no regions match, all regions are shown as fallback.
   * Regions are sorted alphabetically by display name for better user experience.
   * 
   * @param {string} cloudProvider - Cloud provider code ("aws", "azure", or "gcp")
   */
  function populateRegions(cloudProvider) {
    regionSel.innerHTML = ""; // Clear existing options
    
    // Get all available regions from pricing config
    const regions = Object.keys(defaultPricing.regions);
    
    // Filter regions to match cloud provider prefix (e.g., "aws-us-east-1" for AWS)
    const filteredRegions = regions.filter(r => r.startsWith(cloudProvider + "-"));
    
    if (filteredRegions.length === 0) {
      // Fallback: show all regions if none match the provider
      // This handles edge cases where region naming doesn't follow the pattern
      filteredRegions.push(...regions);
    }
    
    // Sort regions by display name for better UX
    // Display names are user-friendly (e.g., "US East (N. Virginia)") vs keys ("aws-us-east-1")
    filteredRegions.sort((a, b) => {
      const nameA = defaultPricing.regions[a]?.displayName || a;
      const nameB = defaultPricing.regions[b]?.displayName || b;
      return nameA.localeCompare(nameB);
    });
    
    // Create option elements for each region
    for (const r of filteredRegions) {
      const opt = document.createElement("option");
      opt.value = r;
      // Use displayName if available (user-friendly), otherwise use the key (technical)
      opt.textContent = defaultPricing.regions[r]?.displayName || r;
      regionSel.appendChild(opt);
    }
  }

  // Initial population when page loads
  populateRegions(cloudProviderSel.value);
  
  // Update regions dropdown when cloud provider selection changes
  // This provides dynamic filtering: selecting AWS shows only AWS regions, etc.
  cloudProviderSel.addEventListener("change", () => {
    populateRegions(cloudProviderSel.value);
  });

  // ============================================================================
  // WAREHOUSE TYPE AND CLUSTER COUNT MANAGEMENT
  // ============================================================================
  // Multi-cluster warehouses require a cluster count input, but standard and
  // serverless warehouses don't. We show/hide the cluster count field dynamically.
  
  const warehouseTypeSel = document.getElementById("warehouse_type");
  const clusterCountLabel = document.getElementById("cluster_count_label");
  const clusterCountInput = document.getElementById("cluster_count");
  
  /**
   * Shows or hides the cluster count input field based on warehouse type.
   * 
   * Only multi-cluster warehouses need cluster count. For standard and serverless
   * warehouses, we hide the field and reset the value to 1 (default).
   */
  function updateClusterCountVisibility() {
    if (warehouseTypeSel.value === "multi_cluster") {
      // Multi-cluster warehouses: show cluster count field
      clusterCountLabel.style.display = "block";
    } else {
      // Standard/Serverless warehouses: hide cluster count field
      clusterCountLabel.style.display = "none";
      clusterCountInput.value = 1; // Reset to default when hidden
    }
  }
  
  // Update visibility when warehouse type changes
  warehouseTypeSel.addEventListener("change", updateClusterCountVisibility);
  updateClusterCountVisibility(); // Initial call on page load

  // ============================================================================
  // WORKLOAD FAMILY DROPDOWN INITIALIZATION
  // ============================================================================
  // Populate workload family dropdown with available families from calibration config
  // Workload families determine which k-factor is used in calculations
  
  for (const f of Object.keys(defaultCalib.workloadFamilies)) {
    const opt = document.createElement("option");
    opt.value = f; opt.textContent = f;
    familySel.appendChild(opt);
  }

  // ============================================================================
  // CALCULATION BUTTON EVENT HANDLER
  // ============================================================================
  // This is the main calculation trigger. When user clicks "Calculate",
  // we collect all inputs, validate them, run the calculation, and display results.
  
  document.getElementById("calc_btn").addEventListener("click", () => {
    // ============================================================================
    // STEP 1: VALIDATE INPUTS
    // ============================================================================
    // Ensure region exists in pricing config before attempting calculation
    // This prevents runtime errors and provides user-friendly error messages
    
    const region = document.getElementById("region").value;
    if (!defaultPricing.regions[region]) {
      alert(`Error: Region '${region}' not found in pricing config. Please select a valid region.`);
      return;
    }

    // ============================================================================
    // STEP 2: COLLECT USER INPUTS
    // ============================================================================
    // Gather all input values from the HTML form elements
    // These values are converted to numbers where needed for calculations
    
    const inp = {
      db2CpuSecondsPerDay: Number(document.getElementById("db2_cpu").value),
      batchWindowHours: Number(document.getElementById("window_h").value),
      concurrency: Number(document.getElementById("concurrency").value),
      uncompressedTBAtRest: Number(document.getElementById("tb_at_rest").value),
      frequencyPerMonth: Number(document.getElementById("freq").value),
      region: region,
      edition: document.getElementById("edition").value,
      egressTB: Number(document.getElementById("egress_tb").value),
      egressRoute: document.getElementById("egress_route").value,
      timeTravelTB: Number(document.getElementById("timetravel_tb").value),
      failsafeTB: Number(document.getElementById("failsafe_tb").value),
      family: document.getElementById("family").value,
      snowpipeFilesPerDay: Number(document.getElementById("snowpipe_files").value),
      snowpipeComputeHoursPerDay: Number(document.getElementById("snowpipe_compute_hours").value),
      snowpipeUncompressedGBPerDay: Number(document.getElementById("snowpipe_gb").value),
      searchOptComputeHoursPerDay: Number(document.getElementById("searchopt_compute_hours").value),
      tasksHoursPerDay: Number(document.getElementById("tasks_h").value),
      warehouseType: document.getElementById("warehouse_type").value,
      clusterCount: Number(document.getElementById("cluster_count").value) || 1
    };

    // ============================================================================
    // STEP 3: RUN CALCULATION
    // ============================================================================
    // Call the core calculation engine (lib/calc.js) with collected inputs
    // The calculation engine performs all 10 calculation steps and returns results
    
    let res;
    try {
      res = window.Calc.compute(inp, defaultPricing, defaultRules, defaultCalib);
    } catch (error) {
      // Display user-friendly error message if calculation fails
      // Common causes: invalid config, missing data, calculation errors
      alert(`Calculation Error: ${error.message}`);
      console.error("Calculation error:", error);
      return;
    }
    
    // ============================================================================
    // STEP 4: PREPARE INTERMEDIATE VALUES FOR DISPLAY
    // ============================================================================
    // Extract intermediate calculation values to populate the "Calculation Logic" section
    // This shows users step-by-step how the results were calculated
    const k = defaultCalib.workloadFamilies[inp.family]?.k_xs_seconds_per_db2_cpu_second 
      ?? defaultCalib.workloadFamilies[defaultCalib.defaultFamily].k_xs_seconds_per_db2_cpu_second;
    const xsHours = res.daily.xsHours;
    const need = xsHours * Math.max(1, inp.concurrency);
    const sizeFactor = defaultRules.sizeFactor[res.selection.size];
    const creditsPerHour = res.selection.creditsPerHour;
    const whHoursDay = res.selection.whHoursDay;
    const whCreditsDay = res.daily.whCreditsDay;
    const csCap = defaultRules.cloudServices.capCreditsPerHour * whHoursDay;
    const waiverPct = defaultRules.cloudServices.waiverPctOfDailyWH || 0.10;
    const csTenPct = waiverPct * whCreditsDay;
    const csCreditsDay = res.daily.csCreditsDay;
    const snowpipeCreditsDay = res.daily.snowpipeCreditsDay || 0;
    const searchOptCreditsDay = res.daily.searchOptCreditsDay || 0;
    const tasksCreditsDay = res.daily.tasksCreditsDay || 0;
    const serverlessCreditsDay = res.daily.serverlessCreditsDay;
    const dailyTotalCredits = whCreditsDay + csCreditsDay + serverlessCreditsDay;
    const totalMonthlyCredits = res.monthly.credits;
    
    // Use cached region pricing with defensive checks (calculation already validated these exist)
    const regionPricing = defaultPricing.regions[inp.region];
    const editionKey = inp.edition === "vps" && !regionPricing.pricePerCredit.vps ? "business_critical" : inp.edition;
    const pricePerCredit = regionPricing.pricePerCredit[editionKey] || regionPricing.pricePerCredit.business_critical;
    const storageRate = regionPricing.storagePerTBMonth || 0;
    const egressRates = regionPricing.egressPerTB || {};
    let egressRouteKey = inp.egressRoute;
    if (inp.egressRoute === "crossCloud" && !egressRates.crossCloud) {
      egressRouteKey = "internet";
    }
    if (inp.egressRoute === "accountTransfer" && !egressRates.accountTransfer) {
      egressRouteKey = "interRegion";
    }
    const egressRate = egressRates[egressRouteKey] || egressRates[inp.egressRoute] || 0;
    
    // ============================================================================
    // STEP 5: POPULATE CALCULATION LOGIC DISPLAY
    // ============================================================================
    // Update the "Calculation Logic" section with step-by-step breakdown
    // This helps users understand how each result was calculated
    
    // Step 1: Convert Db2 CPU seconds to XS hours using k-factor
    document.getElementById("logic-step1").innerHTML = 
      `<strong>${inp.db2CpuSecondsPerDay.toLocaleString()}</strong> Db2 for z/OS CPU seconds/day × <strong>${k}</strong> (${inp.family} factor) ÷ 3600 = <strong>${xsHours.toFixed(2)}</strong> XS hours`;
    
    // Step 2: Account for concurrent workload
    document.getElementById("logic-step2").innerHTML = 
      `<strong>${xsHours.toFixed(2)}</strong> XS hours × max(1, <strong>${inp.concurrency}</strong> concurrent jobs) = <strong>${need.toFixed(2)}</strong> XS-equivalent hours needed`;
    
    // Step 3: Warehouse size selection (with multi-cluster info)
    // Shows which warehouse size was selected and why (fits within batch window)
    let step3Text = `Size <strong>${res.selection.size}</strong> selected (${sizeFactor}× faster than XS) ⟹ <strong>${need.toFixed(2)}</strong> ÷ ${sizeFactor} = <strong>${(need / sizeFactor).toFixed(2)}</strong> hours`;
    if (inp.warehouseType === "multi_cluster") {
      step3Text += ` × <strong>${inp.clusterCount}</strong> clusters = <strong>${whHoursDay.toFixed(2)}</strong> total warehouse hours`;
    } else {
      step3Text += ` = <strong>${whHoursDay.toFixed(2)}</strong> hours`;
    }
    step3Text += ` (fits in ${inp.batchWindowHours}h window)`;
    document.getElementById("logic-step3").innerHTML = step3Text;
    
    // Step 4: Calculate warehouse credits per day
    document.getElementById("logic-step4").innerHTML = 
      `<strong>${whHoursDay.toFixed(2)}</strong> warehouse hours × <strong>${creditsPerHour}</strong> credits/hour (${res.selection.size}) = <strong>${whCreditsDay.toFixed(2)}</strong> warehouse credits/day`;
    
    // Step 5: Calculate Cloud Services credits (with 10% waiver rule)
    document.getElementById("logic-step5").innerHTML = 
      `min(${(waiverPct * 100).toFixed(0)}% of ${whCreditsDay.toFixed(2)} = <strong>${csTenPct.toFixed(2)}</strong>, cap of ${csCap.toFixed(2)}) = <strong>${csCreditsDay.toFixed(2)}</strong> cloud services credits/day`;
    
    // Step 6: Serverless credits breakdown
    // Shows breakdown of Snowpipe, Search Optimization, and Tasks credits
    const isBCVPS = inp.edition === "business_critical" || inp.edition === "vps";
    let step6Parts = [];
    
    // Snowpipe breakdown
    if (isBCVPS && inp.snowpipeUncompressedGBPerDay > 0) {
      const snowpipeConfig = defaultPricing.serverless?.snowpipe?.businessCriticalVPS || {};
      const ratePerGB = snowpipeConfig.rateCreditsPerGB || 0.0037;
      step6Parts.push(`Snowpipe (BC/VPS): ${inp.snowpipeUncompressedGBPerDay.toFixed(1)} GB × ${ratePerGB} = <strong>${snowpipeCreditsDay.toFixed(2)}</strong>`);
    } else if (!isBCVPS && (inp.snowpipeFilesPerDay > 0 || inp.snowpipeComputeHoursPerDay > 0)) {
      const snowpipeConfig = defaultPricing.serverless?.snowpipe?.standardEnterprise || {};
      const ratePer1000 = snowpipeConfig.rateCreditsPer1000Files || 0.06;
      const computeMult = snowpipeConfig.multiplierCompute || 1.25;
      let snowpipeParts = [];
      if (inp.snowpipeFilesPerDay > 0) {
        snowpipeParts.push(`(${inp.snowpipeFilesPerDay.toLocaleString()} files ÷ 1000) × ${ratePer1000} = ${((inp.snowpipeFilesPerDay / 1000) * ratePer1000).toFixed(2)}`);
      }
      if (inp.snowpipeComputeHoursPerDay > 0) {
        snowpipeParts.push(`${inp.snowpipeComputeHoursPerDay.toFixed(1)} hours × ${computeMult} = ${(inp.snowpipeComputeHoursPerDay * computeMult).toFixed(2)}`);
      }
      step6Parts.push(`Snowpipe (Std/Ent): ${snowpipeParts.join(" + ")} = <strong>${snowpipeCreditsDay.toFixed(2)}</strong>`);
    }
    
    // Search Optimization breakdown
    if (inp.searchOptComputeHoursPerDay > 0) {
      const searchOptConfig = defaultPricing.serverless?.searchOptimization || {};
      const computeMult = searchOptConfig.multiplierCompute || 2;
      const csMult = searchOptConfig.multiplierCloudServices || 1;
      step6Parts.push(`Search Opt: ${inp.searchOptComputeHoursPerDay.toFixed(1)} hours × (${computeMult} compute + ${csMult} CS) = <strong>${searchOptCreditsDay.toFixed(2)}</strong>`);
    }
    
    // Tasks breakdown
    if (inp.tasksHoursPerDay > 0) {
      const tasksConfig = defaultPricing.serverless?.serverlessTasks || {};
      const computeMult = tasksConfig.multiplierCompute || 0.9;
      const csMult = tasksConfig.multiplierCloudServices || 1;
      step6Parts.push(`Tasks: ${inp.tasksHoursPerDay.toFixed(1)} hours × (${computeMult} compute + ${csMult} CS) = <strong>${tasksCreditsDay.toFixed(2)}</strong>`);
    }
    
    if (step6Parts.length > 0) {
      document.getElementById("logic-step6").innerHTML = 
        step6Parts.join(" + ") + ` ⟹ Total: <strong>${serverlessCreditsDay.toFixed(2)}</strong> serverless credits/day`;
    } else {
      document.getElementById("logic-step6").innerHTML = 
        `No serverless features configured = <strong>${serverlessCreditsDay.toFixed(2)}</strong> serverless credits/day`;
    }
    
    // Step 7: Scale to monthly credits based on execution frequency
    document.getElementById("logic-step7").innerHTML = 
      `(${whCreditsDay.toFixed(2)} + ${csCreditsDay.toFixed(2)} + ${serverlessCreditsDay.toFixed(2)}) × <strong>${inp.frequencyPerMonth}</strong> runs/month = <strong>${totalMonthlyCredits.toFixed(2)}</strong> total credits/month`;
    
    // Step 8: Convert credits to dollars using region/edition pricing
    document.getElementById("logic-step8").innerHTML = 
      `<strong>${totalMonthlyCredits.toFixed(2)}</strong> credits × <strong>$${pricePerCredit.toFixed(2)}</strong>/credit (${inp.region}, ${inp.edition}) = <strong>$${res.monthly.dollarsCompute.toFixed(2)}</strong>`;
    
    // Step 9: Calculate storage costs (regular + Time Travel + Fail-safe)
    const storageBreakdown = [];
    if (inp.uncompressedTBAtRest > 0) {
      storageBreakdown.push(`${inp.uncompressedTBAtRest} TB regular`);
    }
    if (inp.timeTravelTB > 0) {
      storageBreakdown.push(`${inp.timeTravelTB} TB Time Travel`);
    }
    if (inp.failsafeTB > 0) {
      storageBreakdown.push(`${inp.failsafeTB} TB Fail-safe`);
    }
    const totalStorageTB = (inp.uncompressedTBAtRest || 0) + (inp.timeTravelTB || 0) + (inp.failsafeTB || 0);
    const storageDesc = storageBreakdown.length > 0 ? ` (${storageBreakdown.join(" + ")})` : "";
    document.getElementById("logic-step9").innerHTML = 
      `<strong>${totalStorageTB.toFixed(1)}</strong> TB total storage${storageDesc} × <strong>$${storageRate.toFixed(2)}</strong>/TB/month = <strong>$${res.monthly.dollarsStorage.toFixed(2)}</strong>`;
    
    // Step 10: Calculate data transfer (egress) costs
    document.getElementById("logic-step10").innerHTML = 
      `<strong>${inp.egressTB}</strong> TB egress × <strong>$${egressRate.toFixed(2)}</strong>/TB (${inp.egressRoute}) = <strong>$${res.monthly.dollarsTransfer.toFixed(2)}</strong>`;
    
    // Step 11: Grand total (sum of all costs)
    document.getElementById("logic-step11").innerHTML = 
      `$${res.monthly.dollarsCompute.toFixed(2)} (compute) + $${res.monthly.dollarsStorage.toFixed(2)} (storage) + $${res.monthly.dollarsTransfer.toFixed(2)} (transfer) = <strong>$${res.monthly.grandTotal.toFixed(2)}</strong>`;
    
    // ============================================================================
    // STEP 6: POPULATE RESULTS DISPLAY
    // ============================================================================
    // Update the "Results" section with calculated values
    // This shows users the final cost breakdown and warehouse recommendations
    document.getElementById("result-size").textContent = res.selection.size;
    document.getElementById("result-wh-hours").textContent = res.selection.whHoursDay.toFixed(2);
    document.getElementById("result-wh-credits").textContent = res.daily.whCreditsDay.toFixed(2);
    
    // Show cluster count if multi-cluster
    const clusterCountLabel = document.getElementById("result-cluster-count-label");
    const clusterCountValue = document.getElementById("result-cluster-count");
    if (inp.warehouseType === "multi_cluster") {
      clusterCountLabel.style.display = "block";
      clusterCountValue.textContent = res.selection.clusterCount || inp.clusterCount;
    } else {
      clusterCountLabel.style.display = "none";
    }
    
    document.getElementById("result-cs-credits").textContent = res.daily.csCreditsDay.toFixed(2);
    document.getElementById("result-serverless-credits").textContent = res.daily.serverlessCreditsDay.toFixed(2);
    document.getElementById("result-monthly-credits").textContent = res.monthly.credits.toFixed(2);
    document.getElementById("result-compute").textContent = "$" + res.monthly.dollarsCompute.toFixed(2);
    document.getElementById("result-storage").textContent = "$" + res.monthly.dollarsStorage.toFixed(2);
    document.getElementById("result-transfer").textContent = "$" + res.monthly.dollarsTransfer.toFixed(2);
    document.getElementById("result-grand-total").textContent = "$" + res.monthly.grandTotal.toFixed(2);
    document.getElementById("result-grand-total-year").textContent = "$" + (res.monthly.grandTotal * 12).toFixed(2);
    
    // Store raw JSON for export functionality (JSON/CSV export buttons)
    outEl.textContent = JSON.stringify(res, null, 2);
    
    // Show the logic and results sections (they're hidden by default)
    document.getElementById("logic").style.display = "block";
    document.getElementById("results").style.display = "block";
    
    // Scroll to logic section so users can see the calculation breakdown
    document.getElementById("logic").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // ============================================================================
  // EXPORT FUNCTIONALITY
  // ============================================================================
  // Functions to export calculation results as JSON or CSV files
  
  /**
   * Downloads a file with the given name, content, and MIME type.
   * 
   * This is a utility function used by JSON and CSV export buttons.
   * It creates a temporary download link, triggers it, then cleans up.
   * 
   * @param {string} name - Filename for the download
   * @param {string} text - File content (text)
   * @param {string} mime - MIME type (e.g., "application/json", "text/csv")
   */
  function download(name, text, mime) {
    const blob = new Blob([text], {type: mime});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  }

  // JSON Export Button Handler
  // Exports the complete calculation result as a JSON file
  // Useful for saving results, sharing with team, or importing into other tools
  document.getElementById("export_json").addEventListener("click", () => {
    if (!outEl.textContent) return; // No calculation results available
    download('result.json', outEl.textContent, 'application/json');
  });

  // CSV Export Button Handler
  // Exports key calculation results as a CSV file
  // Useful for importing into Excel, Google Sheets, or other spreadsheet tools
  document.getElementById("export_csv").addEventListener("click", () => {
    if (!outEl.textContent) {
      alert("No calculation results available. Please run a calculation first.");
      return;
    }
    try {
      // Parse the JSON result object
      const obj = JSON.parse(outEl.textContent);
      
      // Create CSV rows with key calculation results
      // Format: [["column_name", value], ...]
      // This creates a simple key-value CSV that's easy to import into spreadsheets
      const rows = [
        ["size", obj.selection.size],
        ["whHoursDay", obj.selection.whHoursDay],
        ["whCreditsDay", obj.daily.whCreditsDay],
        ["csCreditsDay", obj.daily.csCreditsDay],
        ["serverlessCreditsDay", obj.daily.serverlessCreditsDay],
        ["monthlyCredits", obj.monthly.credits],
        ["dollarsCompute", obj.monthly.dollarsCompute],
        ["dollarsStorage", obj.monthly.dollarsStorage],
        ["dollarsTransfer", obj.monthly.dollarsTransfer],
        ["grandTotal", obj.monthly.grandTotal]
      ];
      
      // Convert rows to CSV format: "key,value\nkey,value\n..."
      const csv = rows.map(r=>r.join(",")).join("\n");
      download('result.csv', csv, 'text/csv');
    } catch (error) {
      // Handle errors gracefully (e.g., invalid JSON, missing data)
      alert(`Error exporting CSV: ${error.message}`);
      console.error("CSV export error:", error);
    }
  });
})();

