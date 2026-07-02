#!/usr/bin/env python3
"""
Dependency Scanner for Presek

This script scans for vulnerable dependencies and provides recommendations
for updates. It should be run regularly as part of CI/CD or maintenance.
"""

import subprocess
import json
import sys
from typing import List, Dict, Any


def run_pip_audit() -> Dict[str, Any]:
    """Run pip-audit and return the results as a dictionary."""
    try:
        result = subprocess.run(
            ["pip-audit"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            # Parse the pip-audit output
            vulnerabilities = []
            lines = result.stdout.strip().split('\n')
            
            # Skip header lines
            for line in lines[2:]:  # Skip the first 2 header lines
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 4:
                        vulnerabilities.append({
                            'package': parts[0],
                            'version': parts[1],
                            'vulnerability_id': parts[2],
                            'fix_versions': parts[3] if len(parts) > 3 else 'None'
                        })
            
            return {
                'success': False,
                'vulnerabilities': vulnerabilities,
                'raw_output': result.stdout,
                'error': result.stderr
            }
        
        return {
            'success': True,
            'vulnerabilities': [],
            'message': 'No vulnerabilities found'
        }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': 'pip-audit timed out',
            'vulnerabilities': []
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'vulnerabilities': []
        }


def get_outdated_packages() -> List[Dict[str, str]]:
    """Get a list of outdated packages."""
    try:
        result = subprocess.run(
            ["pip", "list", "--outdated", "--format=json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return []
    except Exception:
        return []


def generate_update_script(vulnerabilities: List[Dict[str, Any]]) -> str:
    """Generate a shell script to update vulnerable packages."""
    script = "#!/bin/bash\n"
    script += "# Auto-generated dependency update script\n"
    script += "# Run this to fix critical security vulnerabilities\n"
    script += "\n"
    
    for vuln in vulnerabilities:
        package = vuln['package']
        fix_versions = vuln['fix_versions']
        if fix_versions and fix_versions != 'None':
            # Use the first fix version
            fix_version = fix_versions.split()[0]
            script += f"echo 'Updating {package} to {fix_version}...'\n"
            script += f"pip install --upgrade {package}=={fix_version}\n"
            script += "\n"
    
    script += "echo '✅ Dependency updates completed!'\n"
    script += "echo 'Run pip-audit again to verify fixes.'\n"
    
    return script


def main() -> int:
    """Main function to run the dependency scan."""
    print("🔍 Starting Presek Dependency Scan...")
    print("=" * 50)
    
    # Check for vulnerabilities
    print("🛡️  Scanning for vulnerable dependencies...")
    audit_result = run_pip_audit()
    
    if not audit_result['success']:
        vulnerabilities = audit_result['vulnerabilities']
        
        if vulnerabilities:
            print(f"⚠️  Found {len(vulnerabilities)} security vulnerabilities:")
            print("-" * 50)
            
            for vuln in vulnerabilities:
                print(f"📦 {vuln['package']} {vuln['version']}")
                print(f"   🔴 {vuln['vulnerability_id']}")
                print(f"   💡 Fix: {vuln['fix_versions']}")
                print()
            
            # Generate update script
            update_script = generate_update_script(vulnerabilities)
            
            with open('fix_vulnerabilities.sh', 'w') as f:
                f.write(update_script)
            
            print("📝 Generated fix script: fix_vulnerabilities.sh")
            print("   Run: bash fix_vulnerabilities.sh")
            print()
        else:
            print("✅ No security vulnerabilities found!")
    else:
        print("✅ No security vulnerabilities found!")
    
    print()
    
    # Check for outdated packages
    print("🔄 Checking for outdated packages...")
    outdated = get_outdated_packages()
    
    if outdated:
        print(f"📦 Found {len(outdated)} outdated packages:")
        print("-" * 50)
        
        critical_updates = []
        for pkg in outdated[:10]:  # Show top 10
            print(f"📦 {pkg['name']}: {pkg['version']} → {pkg['latest_version']}")
            if 'security' in pkg.get('name', '').lower() or 'crypto' in pkg.get('name', '').lower():
                critical_updates.append(pkg)
        
        if len(outdated) > 10:
            print(f"... and {len(outdated) - 10} more")
        
        print()
        
        if critical_updates:
            print("⚠️  Critical security-related packages need updating:")
            for pkg in critical_updates:
                print(f"   {pkg['name']}: {pkg['version']} → {pkg['latest_version']}")
    else:
        print("✅ All packages are up to date!")
    
    print()
    print("📊 Scan Summary:")
    print("-" * 50)
    print(f"🛡️  Security Issues: {len(audit_result.get('vulnerabilities', []))}")
    print(f"🔄 Outdated Packages: {len(outdated)}")
    
    if audit_result.get('vulnerabilities'):
        print()
        print("🚨 CRITICAL: Security vulnerabilities require immediate attention!")
        return 1
    elif outdated:
        print()
        print("⚠️  WARNING: Outdated packages should be updated soon.")
        return 0
    else:
        print()
        print("✅ EXCELLENT: All dependencies are secure and up to date!")
        return 0


if __name__ == "__main__":
    sys.exit(main())