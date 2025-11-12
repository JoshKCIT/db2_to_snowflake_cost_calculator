/**
 * Copyright (c) 2025 JoshKCIT
 * 
 * Configuration editor for Snowflake Budget Calculator
 */
(function(){
  "use strict";

  // Storage keys
  const STORAGE_KEYS = {
    PRICING: 'snowflake_config_pricing',
    RULES: 'snowflake_config_rules',
    CALIBRATION: 'snowflake_config_calibration'
  };

  // Get default configs
  const getDefaultPricing = () => window.CONFIG_PRICING || {};
  const getDefaultRules = () => window.CONFIG_RULES || {};
  const getDefaultCalibration = () => window.CONFIG_CALIBRATION || {};

  // Load configs from localStorage or defaults
  function loadConfig(key, defaultConfig) {
    try {
      const stored = localStorage.getItem(key);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (e) {
      console.error(`Error loading ${key}:`, e);
    }
    return JSON.parse(JSON.stringify(defaultConfig)); // Deep clone
  }

  // Save config to localStorage
  function saveConfig(key, config) {
    try {
      localStorage.setItem(key, JSON.stringify(config));
      return true;
    } catch (e) {
      console.error(`Error saving ${key}:`, e);
      alert(`Error saving configuration: ${e.message}`);
      return false;
    }
  }

  // Current configs
  let currentPricing = loadConfig(STORAGE_KEYS.PRICING, getDefaultPricing());
  let currentRules = loadConfig(STORAGE_KEYS.RULES, getDefaultRules());
  let currentCalibration = loadConfig(STORAGE_KEYS.CALIBRATION, getDefaultCalibration());

  // Initialize configs in window immediately (before app.js runs)
  window.CONFIG_PRICING = currentPricing;
  window.CONFIG_RULES = currentRules;
  window.CONFIG_CALIBRATION = currentCalibration;

  // Render functions (defined at module level so they're accessible)
  function renderRegions() {
    const container = document.getElementById('regions-list');
    container.innerHTML = '';
    
    const regions = currentPricing.regions || {};
    Object.keys(regions).sort().forEach(regionKey => {
      const region = regions[regionKey];
      const item = document.createElement('div');
      item.className = 'config-item';
      item.innerHTML = `
        <div class="config-item-header">
          <div class="config-item-title">${region.displayName || regionKey}</div>
          <div class="config-item-actions">
            <button onclick="configEditor.removeRegion('${regionKey}')">Delete</button>
          </div>
        </div>
        <div class="config-form">
          <div class="config-form-group">
            <label>Region Key</label>
            <input type="text" value="${regionKey}" onchange="configEditor.updateRegionKey('${regionKey}', this.value)" />
          </div>
          <div class="config-form-group">
            <label>Display Name</label>
            <input type="text" value="${region.displayName || ''}" onchange="configEditor.updateRegionField('${regionKey}', 'displayName', this.value)" />
          </div>
          <div class="config-form-group">
            <label>Storage ($/TB/month)</label>
            <input type="number" step="0.01" value="${region.storagePerTBMonth || 0}" onchange="configEditor.updateRegionField('${regionKey}', 'storagePerTBMonth', parseFloat(this.value))" />
          </div>
        </div>
        <div class="config-nested">
          <h4>Price Per Credit by Edition</h4>
          <div class="config-form">
            <div class="config-form-group">
              <label>Standard</label>
              <input type="number" step="0.01" value="${region.pricePerCredit?.standard || ''}" placeholder="N/A" onchange="configEditor.updatePricePerCredit('${regionKey}', 'standard', this.value ? parseFloat(this.value) : null)" />
            </div>
            <div class="config-form-group">
              <label>Enterprise</label>
              <input type="number" step="0.01" value="${region.pricePerCredit?.enterprise || ''}" placeholder="N/A" onchange="configEditor.updatePricePerCredit('${regionKey}', 'enterprise', this.value ? parseFloat(this.value) : null)" />
            </div>
            <div class="config-form-group">
              <label>Business Critical</label>
              <input type="number" step="0.01" value="${region.pricePerCredit?.business_critical || ''}" placeholder="N/A" onchange="configEditor.updatePricePerCredit('${regionKey}', 'business_critical', this.value ? parseFloat(this.value) : null)" />
            </div>
            <div class="config-form-group">
              <label>VPS</label>
              <input type="number" step="0.01" value="${region.pricePerCredit?.vps || ''}" placeholder="N/A" onchange="configEditor.updatePricePerCredit('${regionKey}', 'vps', this.value ? parseFloat(this.value) : null)" />
            </div>
          </div>
          <h4>Egress Pricing ($/TB)</h4>
          <div class="config-form">
            <div class="config-form-group">
              <label>Intra-Region</label>
              <input type="number" step="0.01" value="${region.egressPerTB?.intraRegion || 0}" onchange="configEditor.updateEgress('${regionKey}', 'intraRegion', parseFloat(this.value))" />
            </div>
            <div class="config-form-group">
              <label>Inter-Region</label>
              <input type="number" step="0.01" value="${region.egressPerTB?.interRegion || 0}" onchange="configEditor.updateEgress('${regionKey}', 'interRegion', parseFloat(this.value))" />
            </div>
            <div class="config-form-group">
              <label>Cross-Cloud</label>
              <input type="number" step="0.01" value="${region.egressPerTB?.crossCloud || 0}" onchange="configEditor.updateEgress('${regionKey}', 'crossCloud', parseFloat(this.value))" />
            </div>
            <div class="config-form-group">
              <label>Internet</label>
              <input type="number" step="0.01" value="${region.egressPerTB?.internet || 0}" onchange="configEditor.updateEgress('${regionKey}', 'internet', parseFloat(this.value))" />
            </div>
            <div class="config-form-group">
              <label>Account Transfer</label>
              <input type="number" step="0.01" value="${region.egressPerTB?.accountTransfer || 0}" onchange="configEditor.updateEgress('${regionKey}', 'accountTransfer', parseFloat(this.value))" />
            </div>
          </div>
        </div>
      `;
      container.appendChild(item);
    });
  }

  function renderServerless() {
    const container = document.getElementById('serverless-config');
    const serverless = currentPricing.serverless || {};
    container.innerHTML = `
      <div class="config-form">
        <div class="config-form-group">
          <label>Snowpipe Credits (per 1000 files)</label>
          <input type="number" step="0.001" value="${serverless.snowpipePer1000FilesCredits || 0.05}" onchange="configEditor.updateServerless('snowpipePer1000FilesCredits', parseFloat(this.value))" />
        </div>
        <div class="config-form-group">
          <label>Search Optimization Credits (per TB/month)</label>
          <input type="number" step="0.01" value="${serverless.searchOptimizationPerTBMonthCredits || 1.0}" onchange="configEditor.updateServerless('searchOptimizationPerTBMonthCredits', parseFloat(this.value))" />
        </div>
        <div class="config-form-group">
          <label>Tasks Overhead Credits (per hour)</label>
          <input type="number" step="0.01" value="${serverless.tasksOverheadCreditsPerHour || 0.25}" onchange="configEditor.updateServerless('tasksOverheadCreditsPerHour', parseFloat(this.value))" />
        </div>
      </div>
    `;
  }

  function renderWarehouseCredits() {
    const container = document.getElementById('warehouse-credits-config');
    const credits = currentRules.warehouseCreditsPerHour || {};
    const sizes = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL'];
    container.innerHTML = `
      <div class="config-form">
        ${sizes.map(size => `
          <div class="config-form-group">
            <label>${size}</label>
            <input type="number" step="0.01" value="${credits[size] || 0}" onchange="configEditor.updateWarehouseCredits('${size}', parseFloat(this.value))" />
          </div>
        `).join('')}
      </div>
    `;
  }

  function renderSizeFactors() {
    const container = document.getElementById('size-factors-config');
    const factors = currentRules.sizeFactor || {};
    const sizes = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL'];
    container.innerHTML = `
      <div class="config-form">
        ${sizes.map(size => `
          <div class="config-form-group">
            <label>${size}</label>
            <input type="number" step="1" value="${factors[size] || 0}" onchange="configEditor.updateSizeFactor('${size}', parseInt(this.value))" />
          </div>
        `).join('')}
      </div>
    `;
  }

  function renderCloudServices() {
    const container = document.getElementById('cloud-services-config');
    const cs = currentRules.cloudServices || {};
    container.innerHTML = `
      <div class="config-form">
        <div class="config-form-group">
          <label>Cap Credits Per Hour</label>
          <input type="number" step="0.1" value="${cs.capCreditsPerHour || 4.4}" onchange="configEditor.updateCloudServices('capCreditsPerHour', parseFloat(this.value))" />
        </div>
      </div>
    `;
  }

  function renderWorkloadFamilies() {
    const container = document.getElementById('workload-families-list');
    container.innerHTML = '';
    
    const families = currentCalibration.workloadFamilies || {};
    Object.keys(families).sort().forEach(familyKey => {
      const family = families[familyKey];
      const item = document.createElement('div');
      item.className = 'config-item';
      item.innerHTML = `
        <div class="config-item-header">
          <div class="config-item-title">${familyKey}</div>
          <div class="config-item-actions">
            <button onclick="configEditor.removeWorkloadFamily('${familyKey}')">Delete</button>
          </div>
        </div>
        <div class="config-form">
          <div class="config-form-group">
            <label>Family Key</label>
            <input type="text" value="${familyKey}" onchange="configEditor.updateWorkloadFamilyKey('${familyKey}', this.value)" />
          </div>
          <div class="config-form-group">
            <label>K (XS seconds per Db2 for z/OS CPU second)</label>
            <input type="number" step="0.1" value="${family.k_xs_seconds_per_db2_cpu_second || 0}" onchange="configEditor.updateWorkloadFamilyField('${familyKey}', 'k_xs_seconds_per_db2_cpu_second', parseFloat(this.value))" />
          </div>
          <div class="config-form-group">
            <label>Notes</label>
            <input type="text" value="${family.notes || ''}" onchange="configEditor.updateWorkloadFamilyField('${familyKey}', 'notes', this.value)" />
          </div>
        </div>
      `;
      container.appendChild(item);
    });
  }

  function renderDefaultFamily() {
    const container = document.getElementById('default-family-config');
    const families = Object.keys(currentCalibration.workloadFamilies || {});
    container.innerHTML = `
      <div class="config-form">
        <div class="config-form-group">
          <label>Default Workload Family</label>
          <select onchange="configEditor.updateDefaultFamily(this.value)">
            ${families.map(f => `<option value="${f}" ${f === currentCalibration.defaultFamily ? 'selected' : ''}>${f}</option>`).join('')}
          </select>
        </div>
      </div>
    `;
  }

  function renderAll() {
    renderRegions();
    renderServerless();
    renderWarehouseCredits();
    renderSizeFactors();
    renderCloudServices();
    renderWorkloadFamilies();
    renderDefaultFamily();
  }

  // Update functions
  const configEditor = {
    // Pricing updates
    updateRegionKey(oldKey, newKey) {
      if (oldKey === newKey) return;
      if (!newKey || newKey.trim() === '') {
        alert('Region key cannot be empty');
        return;
      }
      if (currentPricing.regions[newKey]) {
        alert('Region key already exists');
        return;
      }
      currentPricing.regions[newKey] = currentPricing.regions[oldKey];
      delete currentPricing.regions[oldKey];
      saveConfig(STORAGE_KEYS.PRICING, currentPricing);
      renderRegions();
      // Update window config for calculator
      window.CONFIG_PRICING = currentPricing;
    },
    updateRegionField(regionKey, field, value) {
      if (!currentPricing.regions[regionKey]) return;
      currentPricing.regions[regionKey][field] = value;
      saveConfig(STORAGE_KEYS.PRICING, currentPricing);
      window.CONFIG_PRICING = currentPricing;
    },
    updatePricePerCredit(regionKey, edition, value) {
      if (!currentPricing.regions[regionKey]) return;
      if (!currentPricing.regions[regionKey].pricePerCredit) {
        currentPricing.regions[regionKey].pricePerCredit = {};
      }
      if (value === null || value === '') {
        delete currentPricing.regions[regionKey].pricePerCredit[edition];
      } else {
        currentPricing.regions[regionKey].pricePerCredit[edition] = value;
      }
      saveConfig(STORAGE_KEYS.PRICING, currentPricing);
      window.CONFIG_PRICING = currentPricing;
    },
    updateEgress(regionKey, route, value) {
      if (!currentPricing.regions[regionKey]) return;
      if (!currentPricing.regions[regionKey].egressPerTB) {
        currentPricing.regions[regionKey].egressPerTB = {};
      }
      currentPricing.regions[regionKey].egressPerTB[route] = value;
      saveConfig(STORAGE_KEYS.PRICING, currentPricing);
      window.CONFIG_PRICING = currentPricing;
    },
    updateServerless(field, value) {
      if (!currentPricing.serverless) {
        currentPricing.serverless = {};
      }
      currentPricing.serverless[field] = value;
      saveConfig(STORAGE_KEYS.PRICING, currentPricing);
      window.CONFIG_PRICING = currentPricing;
    },
    addRegion() {
      const cloudProvider = prompt('Enter cloud provider (aws, azure, gcp):', 'aws');
      if (!cloudProvider) return;
      const regionName = prompt('Enter region name (e.g., us-east-1):', '');
      if (!regionName) return;
      const displayName = prompt('Enter display name:', '');
      const regionKey = `${cloudProvider}-${regionName}`;
      if (currentPricing.regions[regionKey]) {
        alert('Region already exists');
        return;
      }
      if (!currentPricing.regions) {
        currentPricing.regions = {};
      }
      currentPricing.regions[regionKey] = {
        pricePerCredit: { standard: null, enterprise: null, business_critical: null, vps: null },
        storagePerTBMonth: 23.0,
        egressPerTB: { intraRegion: 0, interRegion: 0, crossCloud: 0, internet: 0, accountTransfer: 0 },
        displayName: displayName || regionKey
      };
      saveConfig(STORAGE_KEYS.PRICING, currentPricing);
      window.CONFIG_PRICING = currentPricing;
      renderRegions();
    },
    removeRegion(regionKey) {
      if (!confirm(`Delete region "${currentPricing.regions[regionKey]?.displayName || regionKey}"?`)) return;
      delete currentPricing.regions[regionKey];
      saveConfig(STORAGE_KEYS.PRICING, currentPricing);
      window.CONFIG_PRICING = currentPricing;
      renderRegions();
    },
    // Rules updates
    updateWarehouseCredits(size, value) {
      if (!currentRules.warehouseCreditsPerHour) {
        currentRules.warehouseCreditsPerHour = {};
      }
      currentRules.warehouseCreditsPerHour[size] = value;
      saveConfig(STORAGE_KEYS.RULES, currentRules);
      window.CONFIG_RULES = currentRules;
    },
    updateSizeFactor(size, value) {
      if (!currentRules.sizeFactor) {
        currentRules.sizeFactor = {};
      }
      currentRules.sizeFactor[size] = value;
      saveConfig(STORAGE_KEYS.RULES, currentRules);
      window.CONFIG_RULES = currentRules;
    },
    updateCloudServices(field, value) {
      if (!currentRules.cloudServices) {
        currentRules.cloudServices = {};
      }
      currentRules.cloudServices[field] = value;
      saveConfig(STORAGE_KEYS.RULES, currentRules);
      window.CONFIG_RULES = currentRules;
    },
    // Calibration updates
    updateWorkloadFamilyKey(oldKey, newKey) {
      if (oldKey === newKey) return;
      if (!newKey || newKey.trim() === '') {
        alert('Workload family key cannot be empty');
        return;
      }
      if (currentCalibration.workloadFamilies[newKey]) {
        alert('Workload family key already exists');
        return;
      }
      currentCalibration.workloadFamilies[newKey] = currentCalibration.workloadFamilies[oldKey];
      delete currentCalibration.workloadFamilies[oldKey];
      if (currentCalibration.defaultFamily === oldKey) {
        currentCalibration.defaultFamily = newKey;
      }
      saveConfig(STORAGE_KEYS.CALIBRATION, currentCalibration);
      window.CONFIG_CALIBRATION = currentCalibration;
      renderWorkloadFamilies();
      renderDefaultFamily();
    },
    updateWorkloadFamilyField(familyKey, field, value) {
      if (!currentCalibration.workloadFamilies[familyKey]) return;
      currentCalibration.workloadFamilies[familyKey][field] = value;
      saveConfig(STORAGE_KEYS.CALIBRATION, currentCalibration);
      window.CONFIG_CALIBRATION = currentCalibration;
    },
    addWorkloadFamily() {
      const familyKey = prompt('Enter workload family key:', '');
      if (!familyKey || familyKey.trim() === '') return;
      if (currentCalibration.workloadFamilies[familyKey]) {
        alert('Workload family already exists');
        return;
      }
      if (!currentCalibration.workloadFamilies) {
        currentCalibration.workloadFamilies = {};
      }
      currentCalibration.workloadFamilies[familyKey] = {
        k_xs_seconds_per_db2_cpu_second: 1.8,
        notes: ''
      };
      saveConfig(STORAGE_KEYS.CALIBRATION, currentCalibration);
      window.CONFIG_CALIBRATION = currentCalibration;
      renderWorkloadFamilies();
      renderDefaultFamily();
    },
    removeWorkloadFamily(familyKey) {
      if (!confirm(`Delete workload family "${familyKey}"?`)) return;
      delete currentCalibration.workloadFamilies[familyKey];
      if (currentCalibration.defaultFamily === familyKey) {
        const remaining = Object.keys(currentCalibration.workloadFamilies);
        currentCalibration.defaultFamily = remaining.length > 0 ? remaining[0] : '';
      }
      saveConfig(STORAGE_KEYS.CALIBRATION, currentCalibration);
      window.CONFIG_CALIBRATION = currentCalibration;
      renderWorkloadFamilies();
      renderDefaultFamily();
    },
    updateDefaultFamily(familyKey) {
      currentCalibration.defaultFamily = familyKey;
      saveConfig(STORAGE_KEYS.CALIBRATION, currentCalibration);
      window.CONFIG_CALIBRATION = currentCalibration;
    },
    // Reset to defaults
    resetConfig() {
      if (!confirm('Reset all configurations to defaults? This cannot be undone.')) return;
      localStorage.removeItem(STORAGE_KEYS.PRICING);
      localStorage.removeItem(STORAGE_KEYS.RULES);
      localStorage.removeItem(STORAGE_KEYS.CALIBRATION);
      currentPricing = JSON.parse(JSON.stringify(getDefaultPricing()));
      currentRules = JSON.parse(JSON.stringify(getDefaultRules()));
      currentCalibration = JSON.parse(JSON.stringify(getDefaultCalibration()));
      window.CONFIG_PRICING = currentPricing;
      window.CONFIG_RULES = currentRules;
      window.CONFIG_CALIBRATION = currentCalibration;
      renderAll();
      alert('Configuration reset to defaults');
    },
    // Export config
    exportConfig() {
      const config = {
        pricing: currentPricing,
        rules: currentRules,
        calibration: currentCalibration
      };
      const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'snowflake-config.json';
      a.click();
      URL.revokeObjectURL(url);
    },
    // Import config
    importConfig(file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const config = JSON.parse(e.target.result);
          if (config.pricing) {
            currentPricing = config.pricing;
            saveConfig(STORAGE_KEYS.PRICING, currentPricing);
            window.CONFIG_PRICING = currentPricing;
          }
          if (config.rules) {
            currentRules = config.rules;
            saveConfig(STORAGE_KEYS.RULES, currentRules);
            window.CONFIG_RULES = currentRules;
          }
          if (config.calibration) {
            currentCalibration = config.calibration;
            saveConfig(STORAGE_KEYS.CALIBRATION, currentCalibration);
            window.CONFIG_CALIBRATION = currentCalibration;
          }
          renderAll();
          alert('Configuration imported successfully');
        } catch (err) {
          alert(`Error importing configuration: ${err.message}`);
        }
      };
      reader.readAsText(file);
    }
  };

  // Expose to window immediately (before DOM ready)
  window.configEditor = configEditor;

  // Wait for DOM to be ready
  function initConfigEditor() {
    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tabName = btn.dataset.tab;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`${tabName}-tab`).classList.add('active');
      });
    });

    // Event listeners
    const resetBtn = document.getElementById('reset-config');
    const exportBtn = document.getElementById('export-config');
    const importBtn = document.getElementById('import-config');
    const importFile = document.getElementById('import-file');
    
    if (resetBtn) resetBtn.addEventListener('click', () => configEditor.resetConfig());
    if (exportBtn) exportBtn.addEventListener('click', () => configEditor.exportConfig());
    if (importBtn) {
      importBtn.addEventListener('click', () => {
        if (importFile) importFile.click();
      });
    }
    if (importFile) {
      importFile.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
          configEditor.importConfig(e.target.files[0]);
          e.target.value = ''; // Reset file input
        }
      });
    }
    document.querySelectorAll('.add-item-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const type = btn.dataset.type;
        if (type === 'region') {
          configEditor.addRegion();
        } else if (type === 'workload') {
          configEditor.addWorkloadFamily();
        }
      });
    });

    // Render on load
    renderAll();
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initConfigEditor);
  } else {
    initConfigEditor();
  }
})();

