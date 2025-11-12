/**
 * Copyright (c) 2025 JoshKCIT
 * 
 * Main application logic for Snowflake Budget Calculator
 */
(function(){
  "use strict";

  // Use configs from window (loaded by config-editor.js from localStorage or defaults)
  // These are initialized by config-editor.js before this script runs
  const regionSel = document.getElementById("region");
  const familySel = document.getElementById("family");
  const cloudProviderSel = document.getElementById("cloud_provider");
  const outEl = document.getElementById("out");

  // Make defaultPricing, defaultRules, defaultCalib accessible for updates
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

  // Function to refresh configs from window (called when configs are updated)
  function refreshConfigs() {
    if (window.CONFIG_PRICING) {
      defaultPricing = window.CONFIG_PRICING;
    }
    if (window.CONFIG_RULES) {
      defaultRules = window.CONFIG_RULES;
    }
    if (window.CONFIG_CALIBRATION) {
      defaultCalib = window.CONFIG_CALIBRATION;
    }
    // Refresh dropdowns
    populateRegions(cloudProviderSel.value);
    familySel.innerHTML = '';
    for (const f of Object.keys(defaultCalib.workloadFamilies)) {
      const opt = document.createElement("option");
      opt.value = f; opt.textContent = f;
      familySel.appendChild(opt);
    }
  }

  // Listen for config updates - check periodically and on focus
  setInterval(() => {
    if (window.CONFIG_PRICING && window.CONFIG_PRICING !== defaultPricing) {
      refreshConfigs();
    }
  }, 500);
  window.addEventListener('focus', refreshConfigs);

  // Function to populate regions based on cloud provider
  function populateRegions(cloudProvider) {
    regionSel.innerHTML = ""; // Clear existing options
    const regions = Object.keys(defaultPricing.regions);
    const filteredRegions = regions.filter(r => r.startsWith(cloudProvider + "-"));
    
    if (filteredRegions.length === 0) {
      // Fallback: show all regions if none match
      filteredRegions.push(...regions);
    }
    
    // Sort regions by display name for better UX
    filteredRegions.sort((a, b) => {
      const nameA = defaultPricing.regions[a]?.displayName || a;
      const nameB = defaultPricing.regions[b]?.displayName || b;
      return nameA.localeCompare(nameB);
    });
    
    for (const r of filteredRegions) {
      const opt = document.createElement("option");
      opt.value = r;
      // Use displayName if available, otherwise use the key
      opt.textContent = defaultPricing.regions[r]?.displayName || r;
      regionSel.appendChild(opt);
    }
  }

  // Initial population
  populateRegions(cloudProviderSel.value);
  
  // Update regions when cloud provider changes
  cloudProviderSel.addEventListener("change", () => {
    populateRegions(cloudProviderSel.value);
  });

  // Show/hide cluster count field based on warehouse type
  const warehouseTypeSel = document.getElementById("warehouse_type");
  const clusterCountLabel = document.getElementById("cluster_count_label");
  const clusterCountInput = document.getElementById("cluster_count");
  
  function updateClusterCountVisibility() {
    if (warehouseTypeSel.value === "multi_cluster") {
      clusterCountLabel.style.display = "block";
    } else {
      clusterCountLabel.style.display = "none";
      clusterCountInput.value = 1; // Reset to default when hidden
    }
  }
  
  warehouseTypeSel.addEventListener("change", updateClusterCountVisibility);
  updateClusterCountVisibility(); // Initial call

  for (const f of Object.keys(defaultCalib.workloadFamilies)) {
    const opt = document.createElement("option");
    opt.value = f; opt.textContent = f;
    familySel.appendChild(opt);
  }

  document.getElementById("calc_btn").addEventListener("click", () => {
    // Validate region exists before calculation
    const region = document.getElementById("region").value;
    if (!defaultPricing.regions[region]) {
      alert(`Error: Region '${region}' not found in pricing config. Please select a valid region.`);
      return;
    }

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

    let res;
    try {
      res = window.Calc.compute(inp, defaultPricing, defaultRules, defaultCalib);
    } catch (error) {
      alert(`Calculation Error: ${error.message}`);
      console.error("Calculation error:", error);
      return;
    }
    
    // Get intermediate calculation values for logic section
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
    
    // Populate logic steps
    document.getElementById("logic-step1").innerHTML = 
      `<strong>${inp.db2CpuSecondsPerDay.toLocaleString()}</strong> Db2 for z/OS CPU seconds/day × <strong>${k}</strong> (${inp.family} factor) ÷ 3600 = <strong>${xsHours.toFixed(2)}</strong> XS hours`;
    
    document.getElementById("logic-step2").innerHTML = 
      `<strong>${xsHours.toFixed(2)}</strong> XS hours × max(1, <strong>${inp.concurrency}</strong> concurrent jobs) = <strong>${need.toFixed(2)}</strong> XS-equivalent hours needed`;
    
    // Step 3: Warehouse size selection (with multi-cluster info)
    let step3Text = `Size <strong>${res.selection.size}</strong> selected (${sizeFactor}× faster than XS) ⟹ <strong>${need.toFixed(2)}</strong> ÷ ${sizeFactor} = <strong>${(need / sizeFactor).toFixed(2)}</strong> hours`;
    if (inp.warehouseType === "multi_cluster") {
      step3Text += ` × <strong>${inp.clusterCount}</strong> clusters = <strong>${whHoursDay.toFixed(2)}</strong> total warehouse hours`;
    } else {
      step3Text += ` = <strong>${whHoursDay.toFixed(2)}</strong> hours`;
    }
    step3Text += ` (fits in ${inp.batchWindowHours}h window)`;
    document.getElementById("logic-step3").innerHTML = step3Text;
    
    document.getElementById("logic-step4").innerHTML = 
      `<strong>${whHoursDay.toFixed(2)}</strong> warehouse hours × <strong>${creditsPerHour}</strong> credits/hour (${res.selection.size}) = <strong>${whCreditsDay.toFixed(2)}</strong> warehouse credits/day`;
    
    document.getElementById("logic-step5").innerHTML = 
      `min(${(waiverPct * 100).toFixed(0)}% of ${whCreditsDay.toFixed(2)} = <strong>${csTenPct.toFixed(2)}</strong>, cap of ${csCap.toFixed(2)}) = <strong>${csCreditsDay.toFixed(2)}</strong> cloud services credits/day`;
    
    // Step 6: Serverless breakdown
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
    
    document.getElementById("logic-step7").innerHTML = 
      `(${whCreditsDay.toFixed(2)} + ${csCreditsDay.toFixed(2)} + ${serverlessCreditsDay.toFixed(2)}) × <strong>${inp.frequencyPerMonth}</strong> runs/month = <strong>${totalMonthlyCredits.toFixed(2)}</strong> total credits/month`;
    
    document.getElementById("logic-step8").innerHTML = 
      `<strong>${totalMonthlyCredits.toFixed(2)}</strong> credits × <strong>$${pricePerCredit.toFixed(2)}</strong>/credit (${inp.region}, ${inp.edition}) = <strong>$${res.monthly.dollarsCompute.toFixed(2)}</strong>`;
    
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
    
    document.getElementById("logic-step10").innerHTML = 
      `<strong>${inp.egressTB}</strong> TB egress × <strong>$${egressRate.toFixed(2)}</strong>/TB (${inp.egressRoute}) = <strong>$${res.monthly.dollarsTransfer.toFixed(2)}</strong>`;
    
    document.getElementById("logic-step11").innerHTML = 
      `$${res.monthly.dollarsCompute.toFixed(2)} (compute) + $${res.monthly.dollarsStorage.toFixed(2)} (storage) + $${res.monthly.dollarsTransfer.toFixed(2)} (transfer) = <strong>$${res.monthly.grandTotal.toFixed(2)}</strong>`;
    
    // Populate the structured results
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
    
    // Still keep the raw JSON for export functionality
    outEl.textContent = JSON.stringify(res, null, 2);
    
    // Show the logic and results sections
    document.getElementById("logic").style.display = "block";
    document.getElementById("results").style.display = "block";
    
    // Scroll to logic section
    document.getElementById("logic").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  function download(name, text, mime) {
    const blob = new Blob([text], {type: mime});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  }

  document.getElementById("export_json").addEventListener("click", () => {
    if (!outEl.textContent) return;
    download('result.json', outEl.textContent, 'application/json');
  });

  document.getElementById("export_csv").addEventListener("click", () => {
    if (!outEl.textContent) {
      alert("No calculation results available. Please run a calculation first.");
      return;
    }
    try {
      const obj = JSON.parse(outEl.textContent);
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
      const csv = rows.map(r=>r.join(",")).join("\n");
      download('result.csv', csv, 'text/csv');
    } catch (error) {
      alert(`Error exporting CSV: ${error.message}`);
      console.error("CSV export error:", error);
    }
  });
})();

