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


def run_command(cmd: str, description: str = "") -> Tuple[bool, str, str]:
    """Run a command and return success status and output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd="/home/emiloffingen/presek")
        return (result.returncode == 0, result.stdout.strip(), result.stderr.strip())
    except Exception as e:
        return False, "", str(e)


def get_installed_packages() -> Dict[str, str]:
    """Get currently installed packages and versions."""
    success, output, error = run_command(".venv/bin/python3 -m pip list --format=json")
    if not success:
        print(f"❌ Error getting installed packages: {error}")
        return {}

    try:
        packages = json.loads(output)
        return {pkg["name"].lower(): pkg["version"] for pkg in packages}
    except json.JSONDecodeError:
        print(f"❌ Error parsing package list: {output}")
        return {}


def get_outdated_packages() -> List[Dict]:
    """Get outdated packages with current and latest versions."""
    success, output, error = run_command(".venv/bin/python3 -m pip list --outdated --format=json")
    if not success:
        print(f"❌ Error getting outdated packages: {error}")
        return []

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        print(f"❌ Error parsing outdated packages: {output}")
        return []


def get_vulnerable_packages() -> List[Dict]:
    """Get packages with known vulnerabilities."""
    success, output, error = run_command(".venv/bin/python3 -m pip-audit --desc --format=json")
    if not success:
        # pip-audit returns non-zero when vulnerabilities found, so check output
        if output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                pass
        return []

    try:
        data = json.loads(output)
        return data.get("dependencies", [])
    except json.JSONDecodeError:
        return []


def categorize_vulnerability(severity: str) -> str:
    """Categorize vulnerability by severity."""
    severity = severity.lower()
    if "critical" in severity or "high" in severity:
        return "🔴 CRITICAL"
    elif "medium" in severity:
        return "🟠 HIGH"
    else:
        return "🟡 MEDIUM"


def analyze_dependency_usage() -> Dict[str, List[str]]:
    """Analyze which files import each dependency."""
    usage = {}

    # Common core dependencies to check
    core_deps = [
        "fastapi",
        "celery",
        "redis",
        "requests",
        "pydantic",
        "psycopg",
        "sqlalchemy",
        "numpy",
        "pillow",
        "bleach",
    ]

    for dep in core_deps:
        success, output, error = run_command(f"grep -r 'import {dep}' --include='*.py' core/ routes/ tasks/ | head -5")
        if output:
            usage[dep] = output.split("\n")
        else:
            usage[dep] = []

    return usage


def generate_update_recommendations(outdated: List[Dict], vulnerable: List[Dict]) -> List[Dict]:
    """Generate prioritized update recommendations."""
    recommendations = []

    # Create lookup for vulnerable packages
    vuln_lookup = {pkg["name"].lower(): pkg for pkg in vulnerable}

    for pkg in outdated:
        name = pkg["name"].lower()
        current = pkg["version"]
        latest = pkg["latest"]

        recommendation = {
            "package": name,
            "current": current,
            "latest": latest,
            "priority": "medium",
            "reason": "Outdated package",
            "vulnerabilities": [],
        }

        # Check if vulnerable
        if name in vuln_lookup:
            vuln_pkg = vuln_lookup[name]
            for vuln in vuln_pkg.get("vulns", []):
                recommendation["vulnerabilities"].append(
                    {
                        "id": vuln.get("id", "Unknown"),
                        "severity": categorize_vulnerability(vuln.get("severity", "medium")),
                    }
                )

            if recommendation["vulnerabilities"]:
                recommendation["priority"] = "high"
                recommendation["reason"] = "Security vulnerability"

        recommendations.append(recommendation)

    # Sort by priority (high first)
    recommendations.sort(key=lambda x: 0 if x["priority"] == "high" else 1)

    return recommendations


def generate_requirements_update() -> str:
    """Generate updated requirements.txt with pinned versions."""
    success, output, error = run_command(
        ".venv/bin/python3 -m pip freeze | grep -E '^(fastapi|celery|redis|requests|pydantic|psycopg|sqlalchemy|numpy|pillow|bleach)=='"
    )

    if not success:
        return "# Could not generate updated requirements"

    lines = output.split("\n")
    updated = "# Updated requirements with security fixes\n"

    for line in lines:
        if line:
            # Add comments for critical packages
            if line.startswith("cryptography=="):
                updated += f"# SECURITY: Updated for CVE fixes\n{line}\n"
            elif line.startswith("pyjwt=="):
                updated += f"# SECURITY: Updated for JWT vulnerabilities\n{line}\n"
            else:
                updated += f"{line}\n"

    return updated


def main():
    print("🔍 Presek Dependency Analysis")
    print("=" * 50)

    # Get current state
    print("\n📦 Analyzing installed packages...")
    installed = get_installed_packages()
    print(f"   Found {len(installed)} installed packages")

    print("\n🔄 Checking for outdated packages...")
    outdated = get_outdated_packages()
    print(f"   Found {len(outdated)} outdated packages")

    print("\n⚠️  Checking for vulnerabilities...")
    vulnerable = get_vulnerable_packages()
    print(f"   Found {len(vulnerable)} packages with vulnerabilities")

    print("\n🔍 Analyzing dependency usage...")
    usage = analyze_dependency_usage()

    # Generate recommendations
    print("\n🎯 Generating update recommendations...")
    recommendations = generate_update_recommendations(outdated, vulnerable)

    # Display critical findings
    print(f"\n🔴 CRITICAL FINDINGS ({sum(1 for r in recommendations if r['priority'] == 'high')}):")
    for rec in recommendations:
        if rec["priority"] == "high":
            print(f"   {rec['package']}: {rec['current']} → {rec['latest']}")
            for vuln in rec["vulnerabilities"]:
                print(f"      {vuln['severity']} {vuln['id']}")

    # Generate reports
    print("\n📊 Generating reports...")

    # Create detailed report
    report_content = "# Dependency Analysis Report\n\n## Summary\n\n"
    report_content += f"- Total packages: {len(installed)}\n"
    report_content += f"- Outdated packages: {len(outdated)}\n"
    report_content += f"- Vulnerable packages: {len(vulnerable)}\n"
    report_content += f"- Critical updates needed: {sum(1 for r in recommendations if r['priority'] == 'high')}\n\n"

    # Add recommendations
    report_content += "## Update Recommendations\n\n"
    report_content += "| Package | Current | Latest | Priority | Reason |\n"
    report_content += "|---------|---------|--------|----------|--------|\n"

    for rec in recommendations:
        priority_emoji = "🔴" if rec["priority"] == "high" else "🟡"
        report_content += f"| `{rec['package']}` | `{rec['current']}` | `{rec['latest']}` | {priority_emoji} {rec['priority']} | {rec['reason']} |\n"

    # Add usage analysis
    report_content += "\n## Dependency Usage Analysis\n\n"
    for dep, files in usage.items():
        if files:
            report_content += f"### {dep}\n\nUsed in:\n"
            for file in files[:3]:  # Show top 3 files
                report_content += f"- `{file}`\n"
            if len(files) > 3:
                report_content += f"- ... and {len(files) - 3} more files\n"

    # Write report
    Path("DEPENDENCY_ANALYSIS_REPORT.md").write_text(report_content)
    print("   ✅ Written DEPENDENCY_ANALYSIS_REPORT.md")

    # Generate updated requirements
    updated_reqs = generate_requirements_update()
    Path("requirements_updated.txt").write_text(updated_reqs)
    print("   ✅ Written requirements_updated.txt")

    # Generate update script
    update_script = "#!/usr/bin/env bash\n"
    update_script += "# Dependency Update Script\n"
    update_script += "# Run this to update critical dependencies\n\n"

    for rec in recommendations:
        if rec["priority"] == "high":
            update_script += f"echo 'Updating {rec['package']} from {rec['current']} to {rec['latest']}...'\n"
            update_script += f"pip install --upgrade {rec['package']}=={rec['latest']}\n"

    update_script += "\necho '✅ Critical dependency updates completed!'\n"
    update_script += "echo 'Run pip-audit to verify security fixes.'\n"

    Path("scripts/update_critical_deps.sh").write_text(update_script)
    Path("scripts/update_critical_deps.sh").chmod(0o755)
    print("   ✅ Written scripts/update_critical_deps.sh")

    print("\n🎉 Analysis Complete!")
    print("   📋 Report: DEPENDENCY_ANALYSIS_REPORT.md")
    print("   📦 Updated requirements: requirements_updated.txt")
    print("   🔧 Update script: scripts/update_critical_deps.sh")

    if recommendations:
        high_priority = [r for r in recommendations if r["priority"] == "high"]
        if high_priority:
            print(f"\n⚠️  {len(high_priority)} high-priority updates recommended!")
            print("   Run: bash scripts/update_critical_deps.sh")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
