#!/usr/bin/env python3
"""
Comprehensive Dependency Analysis for Presek
Analyzes current dependencies, identifies vulnerabilities, and suggests updates.
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple
from pathlib import Path

def run_command(cmd: str) -> Tuple[bool, str, str]:
    """Run a command and return success status and output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd="/home/emiloffingen/presek")
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def main():
    print("🔍 Presek Dependency Analysis")
    print("=" * 50)
    
    # Simple dependency check using pip-audit
    print("\n⚠️  Checking for vulnerable dependencies...")
    success, output, error = run_command(".venv/bin/python3 -m pip-audit --desc --format=json 2>/dev/null || true")
    
    if output:
        try:
            data = json.loads(output)
            vulnerabilities = data.get("dependencies", [])
            print(f"   Found {len(vulnerabilities)} packages with vulnerabilities")
            
            # Show critical ones
            critical = []
            for pkg in vulnerabilities:
                for vuln in pkg.get("vulns", []):
                    if "critical" in vuln.get("severity", "").lower() or "high" in vuln.get("severity", "").lower():
                        critical.append((pkg["name"], vuln["id"]))
                        break
            
            if critical:
                print("\n🔴 CRITICAL VULNERABILITIES:")
                for name, vid in critical[:5]:  # Show top 5
                    print(f"   {name}: {vid}")
            
            # Generate simple report
            report = "# Critical Dependency Updates Needed\n\n"
            report += f"Total vulnerable packages: {len(vulnerabilities)}\n"
            report += f"Critical/high severity: {len(critical)}\n\n"
            
            if critical:
                report += "## Immediate Action Required\n\n"
                for name, vid in critical:
                    report += f"- `{name}`: {vid}\n"
            
            Path("CRITICAL_DEPENDENCIES.md").write_text(report)
            print("\n   ✅ Written CRITICAL_DEPENDENCIES.md")
            
        except json.JSONDecodeError:
            print("   ❌ Could not parse vulnerability data")
    else:
        print("   ❌ No vulnerability data available")
    
    # Check outdated packages
    print("\n🔄 Checking for outdated packages...")
    success, output, error = run_command(".venv/bin/python3 -m pip list --outdated --format=json")
    
    if success and output:
        try:
            outdated = json.loads(output)
            print(f"   Found {len(outdated)} outdated packages")
            
            # Show top 5 outdated
            if outdated:
                print("\n📦 Top outdated packages:")
                for pkg in outdated[:5]:
                    print(f"   {pkg['name']}: {pkg['version']} → {pkg['latest']}")
            
        except json.JSONDecodeError:
            print("   ❌ Could not parse outdated packages data")
    else:
        print("   ❌ Could not get outdated packages")
    
    print(f"\n🎉 Basic analysis complete!")
    print("   📋 Report: CRITICAL_DEPENDENCIES.md")
    print("\n💡 For full analysis, run:")
    print("   .venv/bin/python3 -m pip-audit --desc")
    print("   .venv/bin/python3 -m pip list --outdated")

if __name__ == "__main__":
    main()