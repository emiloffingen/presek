#!/usr/bin/env python3
"""
Automated Code Quality Fix Script for Presek
Applies ruff fixes to resolve linting issues automatically.
"""

import subprocess
import sys


def run_command(cmd, description):
    """Run a command and report results."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd="/home/emiloffingen/presek")
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
            if result.stdout:
                print(f"Output: {result.stdout[:200]}...")
            return True
        else:
            print(f"❌ {description} failed with code {result.returncode}")
            print(f"Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"💥 {description} crashed: {str(e)}")
        return False


def main():
    print("🚀 Starting Presek Code Quality Automation")
    print("=" * 50)

    # Check if ruff is available
    ruff_check = run_command(".venv/bin/python3 -m ruff --version", "Checking ruff availability")
    if not ruff_check:
        print("⚠️  Ruff not found. Installing...")
        install_ruff = run_command(".venv/bin/python3 -m pip install ruff==0.1.6", "Installing ruff")
        if not install_ruff:
            print("🔴 Cannot proceed without ruff. Exiting.")
            sys.exit(1)

    # Run ruff fixes
    print("\n🧹 Applying automated fixes...")

    fixes_applied = []

    # Fix all auto-fixable issues
    if run_command(".venv/bin/python3 -m ruff check --fix .", "Applying general fixes"):
        fixes_applied.append("general fixes")

    # Fix import sorting
    if run_command(".venv/bin/python3 -m ruff check --select I --fix .", "Fixing import sorting"):
        fixes_applied.append("import sorting")

    # Check what remains
    print("\n🔍 Checking remaining issues...")
    remaining = run_command(".venv/bin/python3 -m ruff check . --statistics", "Counting remaining issues")

    print("\n🎉 Completed code quality automation!")
    print(f"Fixes applied: {', '.join(fixes_applied) if fixes_applied else 'None'}")

    if remaining:
        print("✨ Some issues may require manual review.")
    else:
        print("🎯 All fixable issues resolved!")


if __name__ == "__main__":
    main()
