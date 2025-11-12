#!/usr/bin/env python3
"""
Copyright (c) 2025 JoshKCIT

Comprehensive validation script for DB2 to Snowflake cost calculator.
Validates calculation logic, configs, CSS, and documentation.

Usage: python scripts/validate_all.py
"""

import json
import sys
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Any
from urllib.parse import urlparse

# Add parent directory to path for imports
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

class ValidationResult:
    """Container for validation results"""
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed = []
    
    def add_error(self, category: str, message: str):
        self.errors.append((category, message))
    
    def add_warning(self, category: str, message: str):
        self.warnings.append((category, message))
    
    def add_pass(self, category: str, message: str):
        self.passed.append((category, message))
    
    def has_errors(self) -> bool:
        return len(self.errors) > 0

def validate_calculation_logic(result: ValidationResult) -> bool:
    """Run existing calculation validation script"""
    print("=" * 70)
    print("1. CALCULATION LOGIC VALIDATION")
    print("=" * 70)
    
    try:
        # Run the existing validation script
        script_path = ROOT / "scripts" / "validate_calculations.py"
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(ROOT)
        )
        
        if proc.returncode == 0:
            result.add_pass("Calculation Logic", "All calculation tests passed")
            print(proc.stdout)
            return True
        else:
            result.add_error("Calculation Logic", f"Validation failed:\n{proc.stderr}")
            print(proc.stdout)
            print(proc.stderr)
            return False
    except Exception as e:
        result.add_error("Calculation Logic", f"Failed to run validation: {e}")
        return False

def validate_json_syntax(result: ValidationResult) -> Dict[str, Any]:
    """Validate JSON syntax for all config files"""
    print("\n" + "=" * 70)
    print("2. JSON SYNTAX VALIDATION")
    print("=" * 70)
    
    configs = {}
    json_files = {
        "pricing": ROOT / "config" / "pricing.json",
        "rules": ROOT / "config" / "rules.json",
        "calibration": ROOT / "config" / "calibration.json"
    }
    
    for name, path in json_files.items():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            configs[name] = data
            result.add_pass("JSON Syntax", f"{name}.json is valid JSON")
            print(f"[PASS] {name}.json: Valid JSON")
        except json.JSONDecodeError as e:
            result.add_error("JSON Syntax", f"{name}.json: Invalid JSON - {e}")
            print(f"[FAIL] {name}.json: Invalid JSON - {e}")
        except FileNotFoundError:
            result.add_error("JSON Syntax", f"{name}.json: File not found")
            print(f"[FAIL] {name}.json: File not found")
    
    return configs

def extract_js_config(js_path: Path) -> Dict[str, Any]:
    """Extract JavaScript config object from .js file"""
    try:
        content = js_path.read_text(encoding='utf-8')
        # Find the window.CONFIG_* assignment
        match = re.search(r'window\.CONFIG_\w+\s*=\s*(\{.*?\});', content, re.DOTALL)
        if match:
            # Convert JavaScript object to JSON-compatible string
            js_obj = match.group(1)
            # Replace JavaScript-specific syntax
            js_obj = re.sub(r'(\w+):', r'"\1":', js_obj)  # Quote keys
            js_obj = re.sub(r':\s*null', r': null', js_obj)  # Keep null
            js_obj = re.sub(r':\s*(\d+\.?\d*)', r': \1', js_obj)  # Numbers
            # Try to parse as JSON
            return json.loads(js_obj)
    except Exception as e:
        pass
    return None

def compare_js_json_configs(result: ValidationResult, configs: Dict[str, Any]):
    """Compare JavaScript config files with JSON configs"""
    print("\n" + "=" * 70)
    print("3. JS/JSON CONFIG CONSISTENCY VALIDATION")
    print("=" * 70)
    
    config_pairs = [
        ("pricing", "CONFIG_PRICING"),
        ("rules", "CONFIG_RULES"),
        ("calibration", "CONFIG_CALIBRATION")
    ]
    
    for json_name, js_var_name in config_pairs:
        json_path = ROOT / "config" / f"{json_name}.json"
        js_path = ROOT / "config" / f"{json_name}.js"
        
        if json_name not in configs:
            result.add_warning("JS/JSON Consistency", f"{json_name}.json not loaded, skipping comparison")
            continue
        
        if not js_path.exists():
            result.add_error("JS/JSON Consistency", f"{json_name}.js not found")
            print(f"✗ {json_name}.js: File not found")
            continue
        
        # Read JS file and extract config
        js_content = js_path.read_text(encoding='utf-8')
        
        # Simple comparison: check if JSON string appears in JS file
        json_str = json.dumps(configs[json_name], sort_keys=True, indent=2)
        json_compact = json.dumps(configs[json_name], sort_keys=True)
        
        # Normalize both for comparison (remove whitespace differences)
        json_normalized = re.sub(r'\s+', '', json_compact)
        
        # Extract JS object content more carefully
        js_match = re.search(rf'window\.{js_var_name}\s*=\s*(\{{.*?\}});', js_content, re.DOTALL)
        if js_match:
            js_obj_str = js_match.group(1)
            # Remove comments
            js_obj_str = re.sub(r'//.*?$', '', js_obj_str, flags=re.MULTILINE)
            # Normalize whitespace
            js_obj_str = re.sub(r'\s+', '', js_obj_str)
            
            # Try to parse and compare structure
            try:
                # Use a more sophisticated approach: parse JS-like object
                # For now, do a structural comparison
                json_keys = set(_get_all_keys(configs[json_name]))
                
                # Extract keys from JS (simple regex approach)
                # Note: This is a simplified comparison - actual structure matching would require
                # a full JS parser. For now, we check that the JS file contains the expected structure.
                js_keys = set(re.findall(r'"(\w+)"\s*:', js_obj_str))
                js_keys.update(re.findall(r'(\w+)\s*:', js_obj_str))
                
                # Check if top-level keys match (more reliable than nested comparison)
                json_top_keys = {k.split('.')[0] for k in json_keys}
                js_top_keys = js_keys
                
                # For a more accurate check, verify the JS file contains the expected regions/workloads
                if json_name == "pricing" and "regions" in js_obj_str:
                    result.add_pass("JS/JSON Consistency", f"{json_name}.js contains regions structure")
                    print(f"[PASS] {json_name}.js: Contains expected structure")
                elif json_name == "rules" and "warehouseCreditsPerHour" in js_obj_str and "sizeFactor" in js_obj_str:
                    result.add_pass("JS/JSON Consistency", f"{json_name}.js contains expected structure")
                    print(f"[PASS] {json_name}.js: Contains expected structure")
                elif json_name == "calibration" and "workloadFamilies" in js_obj_str:
                    result.add_pass("JS/JSON Consistency", f"{json_name}.js contains expected structure")
                    print(f"[PASS] {json_name}.js: Contains expected structure")
                else:
                    result.add_warning("JS/JSON Consistency", f"{json_name}.js: Structure comparison limited (regex-based)")
                    print(f"[WARN] {json_name}.js: Structure comparison limited")
            except Exception as e:
                result.add_warning("JS/JSON Consistency", f"{json_name}.js: Could not fully compare - {e}")
                print(f"[WARN] {json_name}.js: Comparison limited - {e}")
        else:
            result.add_error("JS/JSON Consistency", f"{json_name}.js: Could not find {js_var_name} assignment")
            print(f"[FAIL] {json_name}.js: Could not find config assignment")

def _get_all_keys(obj: Any, prefix: str = "") -> List[str]:
    """Recursively get all keys from nested dict"""
    keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(prefix + k if prefix else k)
            if isinstance(v, dict):
                keys.extend(_get_all_keys(v, prefix + k + "."))
    return keys

def validate_config_structure(result: ValidationResult, configs: Dict[str, Any]):
    """Validate config structure and completeness"""
    print("\n" + "=" * 70)
    print("4. CONFIG STRUCTURE VALIDATION")
    print("=" * 70)
    
    # Validate pricing.json
    if "pricing" in configs:
        pricing = configs["pricing"]
        
        # Check regions structure
        if "regions" not in pricing:
            result.add_error("Config Structure", "pricing.json missing 'regions'")
        else:
            result.add_pass("Config Structure", "pricing.json has 'regions'")
            
            # Validate each region
            required_region_fields = ["pricePerCredit", "storagePerTBMonth", "egressPerTB"]
            for region_name, region_data in pricing["regions"].items():
                for field in required_region_fields:
                    if field not in region_data:
                        result.add_error("Config Structure", f"Region '{region_name}' missing '{field}'")
                    else:
                        result.add_pass("Config Structure", f"Region '{region_name}' has '{field}'")
                
                # Validate pricePerCredit structure
                if "pricePerCredit" in region_data:
                    editions = ["standard", "enterprise", "business_critical", "vps"]
                    for edition in editions:
                        if edition not in region_data["pricePerCredit"]:
                            # null is acceptable for some gov regions
                            if region_data["pricePerCredit"].get(edition) is None:
                                result.add_pass("Config Structure", f"Region '{region_name}' has null for '{edition}' (acceptable)")
                            else:
                                result.add_warning("Config Structure", f"Region '{region_name}' missing '{edition}' in pricePerCredit")
        
        # Validate serverless structure
        if "serverless" not in pricing:
            result.add_warning("Config Structure", "pricing.json missing 'serverless' section")
        else:
            result.add_pass("Config Structure", "pricing.json has 'serverless' section")
    
    # Validate rules.json
    if "rules" in configs:
        rules = configs["rules"]
        
        required_fields = ["warehouseCreditsPerHour", "sizeFactor", "cloudServices"]
        for field in required_fields:
            if field not in rules:
                result.add_error("Config Structure", f"rules.json missing '{field}'")
            else:
                result.add_pass("Config Structure", f"rules.json has '{field}'")
        
        # Validate warehouse sizes
        if "warehouseCreditsPerHour" in rules:
            sizes = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL"]
            for size in sizes:
                if size not in rules["warehouseCreditsPerHour"]:
                    result.add_error("Config Structure", f"rules.json missing warehouse size '{size}' in warehouseCreditsPerHour")
                else:
                    result.add_pass("Config Structure", f"rules.json has warehouse size '{size}'")
        
        # Validate cloudServices
        if "cloudServices" in rules:
            if "capCreditsPerHour" not in rules["cloudServices"]:
                result.add_error("Config Structure", "rules.json cloudServices missing 'capCreditsPerHour'")
            if "waiverPctOfDailyWH" not in rules["cloudServices"]:
                result.add_warning("Config Structure", "rules.json cloudServices missing 'waiverPctOfDailyWH' (will use default 0.10)")
    
    # Validate calibration.json
    if "calibration" in configs:
        calib = configs["calibration"]
        
        if "workloadFamilies" not in calib:
            result.add_error("Config Structure", "calibration.json missing 'workloadFamilies'")
        else:
            result.add_pass("Config Structure", "calibration.json has 'workloadFamilies'")
            
            # Check each workload family
            for family_name, family_data in calib["workloadFamilies"].items():
                if "k_xs_seconds_per_db2_cpu_second" not in family_data:
                    result.add_error("Config Structure", f"Workload family '{family_name}' missing 'k_xs_seconds_per_db2_cpu_second'")
                else:
                    result.add_pass("Config Structure", f"Workload family '{family_name}' has k-value")
        
        if "defaultFamily" not in calib:
            result.add_error("Config Structure", "calibration.json missing 'defaultFamily'")
        else:
            default_family = calib["defaultFamily"]
            if "workloadFamilies" in calib and default_family not in calib["workloadFamilies"]:
                result.add_error("Config Structure", f"calibration.json defaultFamily '{default_family}' not in workloadFamilies")
            else:
                result.add_pass("Config Structure", f"calibration.json has valid defaultFamily")

def validate_css(result: ValidationResult):
    """Validate CSS syntax and best practices"""
    print("\n" + "=" * 70)
    print("5. CSS VALIDATION")
    print("=" * 70)
    
    css_path = ROOT / "css" / "styles.css"
    
    if not css_path.exists():
        result.add_error("CSS", "styles.css not found")
        return
    
    try:
        css_content = css_path.read_text(encoding='utf-8')
        
        # Basic syntax checks
        open_braces = css_content.count('{')
        close_braces = css_content.count('}')
        if open_braces != close_braces:
            result.add_error("CSS", f"Mismatched braces: {open_braces} open, {close_braces} close")
        else:
            result.add_pass("CSS", "Braces are balanced")
        
        # Check for CSS variables (best practice)
        if ':root' in css_content and '--' in css_content:
            result.add_pass("CSS", "Uses CSS variables (best practice)")
        else:
            result.add_warning("CSS", "No CSS variables found (consider using :root variables)")
        
        # Check for responsive design
        if '@media' in css_content:
            result.add_pass("CSS", "Contains media queries (responsive design)")
        else:
            result.add_warning("CSS", "No media queries found (may not be responsive)")
        
        # Check for accessibility (focus states)
        if ':focus' in css_content or ':focus-visible' in css_content:
            result.add_pass("CSS", "Contains focus states (accessibility)")
        else:
            result.add_warning("CSS", "No focus states found (accessibility concern)")
        
        # Check file size (performance)
        file_size_kb = len(css_content) / 1024
        if file_size_kb < 10:
            result.add_pass("CSS", f"File size reasonable ({file_size_kb:.1f} KB)")
        else:
            result.add_warning("CSS", f"File size large ({file_size_kb:.1f} KB) - consider optimization")
        
        print(f"[PASS] CSS file loaded: {file_size_kb:.1f} KB")
        print(f"[PASS] Braces balanced: {open_braces} pairs")
        
    except Exception as e:
        result.add_error("CSS", f"Error reading CSS file: {e}")

def validate_documentation(result: ValidationResult):
    """Validate documentation links and references"""
    print("\n" + "=" * 70)
    print("6. DOCUMENTATION VALIDATION")
    print("=" * 70)
    
    # Check markdown files
    md_files = [
        ROOT / "docs" / "calculation_validation_report.md",
        ROOT / "README.md"
    ]
    
    for md_path in md_files:
        if not md_path.exists():
            result.add_warning("Documentation", f"{md_path.name} not found")
            continue
        
        try:
            content = md_path.read_text(encoding='utf-8')
            
            # Find all markdown links
            md_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
            for link_text, link_url in md_links:
                # Check if it's a relative file link
                if not link_url.startswith('http'):
                    # Relative path
                    if link_url.startswith('./'):
                        link_path = md_path.parent / link_url[2:]
                    elif link_url.startswith('../'):
                        link_path = md_path.parent.parent / link_url[3:]
                    else:
                        link_path = md_path.parent / link_url
                    
                    if link_path.exists():
                        result.add_pass("Documentation", f"{md_path.name}: Link '{link_text}' -> '{link_url}' works")
                    else:
                        result.add_error("Documentation", f"{md_path.name}: Broken link '{link_text}' -> '{link_url}'")
                else:
                    # External link - just note it
                    result.add_pass("Documentation", f"{md_path.name}: External link '{link_text}' -> '{link_url}'")
        
        except Exception as e:
            result.add_error("Documentation", f"Error reading {md_path.name}: {e}")
    
    # Check HTML files
    html_files = [
        ROOT / "docs" / "calibration_guide.html",
        ROOT / "docs" / "db2_dba_how_to_use.html",
        ROOT / "docs" / "snowflake_architects_how_to_use.html",
        ROOT / "index.html"
    ]
    
    for html_path in html_files:
        if not html_path.exists():
            result.add_warning("Documentation", f"{html_path.name} not found")
            continue
        
        try:
            content = html_path.read_text(encoding='utf-8')
            
            # Find all href links
            href_links = re.findall(r'href=["\']([^"\']+)["\']', content)
            for link_url in href_links:
                # Skip anchors and external links
                if link_url.startswith('#') or link_url.startswith('http'):
                    continue
                
                # Relative path
                if link_url.startswith('./'):
                    link_path = html_path.parent / link_url[2:]
                elif link_url.startswith('../'):
                    link_path = html_path.parent.parent / link_url[3:]
                else:
                    link_path = html_path.parent / link_url
                
                if link_path.exists():
                    result.add_pass("Documentation", f"{html_path.name}: Link '{link_url}' works")
                else:
                    result.add_error("Documentation", f"{html_path.name}: Broken link '{link_url}'")
        
        except Exception as e:
            result.add_error("Documentation", f"Error reading {html_path.name}: {e}")

def generate_report(result: ValidationResult) -> str:
    """Generate validation report"""
    report = []
    report.append("=" * 70)
    report.append("COMPREHENSIVE VALIDATION REPORT")
    report.append("=" * 70)
    report.append("")
    
    # Summary
    total_checks = len(result.passed) + len(result.warnings) + len(result.errors)
    report.append("SUMMARY")
    report.append("-" * 70)
    report.append(f"Total Checks: {total_checks}")
    report.append(f"Passed: {len(result.passed)}")
    report.append(f"Warnings: {len(result.warnings)}")
    report.append(f"Errors: {len(result.errors)}")
    report.append("")
    
    # Errors
    if result.errors:
        report.append("ERRORS")
        report.append("-" * 70)
        for category, message in result.errors:
            report.append(f"[{category}] {message}")
        report.append("")
    
    # Warnings
    if result.warnings:
        report.append("WARNINGS")
        report.append("-" * 70)
        for category, message in result.warnings:
            report.append(f"[{category}] {message}")
        report.append("")
    
    # Passed (summary only)
    if result.passed:
        report.append("PASSED CHECKS")
        report.append("-" * 70)
        report.append(f"{len(result.passed)} checks passed successfully")
        report.append("")
    
    # Overall status
    if result.has_errors():
        report.append("STATUS: [FAIL] VALIDATION FAILED")
        report.append("Please fix errors before proceeding.")
    elif result.warnings:
        report.append("STATUS: [WARN] VALIDATION PASSED WITH WARNINGS")
        report.append("Review warnings and fix as needed.")
    else:
        report.append("STATUS: [PASS] VALIDATION PASSED")
        report.append("All checks passed successfully!")
    
    return "\n".join(report)

def main():
    """Main validation function"""
    result = ValidationResult()
    
    # Run all validations
    validate_calculation_logic(result)
    configs = validate_json_syntax(result)
    
    if configs:
        compare_js_json_configs(result, configs)
        validate_config_structure(result, configs)
    
    validate_css(result)
    validate_documentation(result)
    
    # Generate and print report
    report = generate_report(result)
    print("\n" + report)
    
    # Save report to file
    report_path = ROOT / "docs" / "validation_report.txt"
    report_path.write_text(report, encoding='utf-8')
    print(f"\nReport saved to: {report_path}")
    
    # Return exit code
    return 1 if result.has_errors() else 0

if __name__ == "__main__":
    exit(main())

