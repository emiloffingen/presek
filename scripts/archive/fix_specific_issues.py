#!/usr/bin/env python3
"""
Targeted Fix Script for Specific Code Quality Issues
Handles issues that ruff can't auto-fix.
"""

import re
import os
from pathlib import Path


def fix_lambda_assignments(file_path):
    """Convert lambda assignments to def functions."""
    try:
        content = Path(file_path).read_text()

        # Pattern to find lambda assignments
        pattern = r"(\w+)\s*=\s*lambda\s+([^:]+):\s*([^\n]+)"

        def replace_lambda(match):
            name = match.group(1)
            args = match.group(2).strip()
            body = match.group(3).strip()
            return f"def {name}({args}):\n    return {body}"

        new_content = re.sub(pattern, replace_lambda, content)

        if new_content != content:
            Path(file_path).write_text(new_content)
            return True
        return False
    except Exception as e:
        print(f"❌ Error fixing {file_path}: {e}")
        return False


def fix_unused_variables(file_path):
    """Remove unused variable assignments."""
    try:
        content = Path(file_path).read_text()
        lines = content.split("\n")

        # Simple pattern for unused variable assignments
        # This is a basic approach - more sophisticated analysis would be better
        pattern = r"\s*(\w+)\s*=\s*.+\n\s*(#|\s*if|\s*for|\s*while|\s*return|\s*\w+\s*=|$)"

        fixed = False
        for i, line in enumerate(lines):
            if re.match(pattern, line) and not line.strip().startswith("#"):
                # Check if variable is used in subsequent lines
                var_name = re.match(pattern, line).group(1)
                used = False
                for j in range(i + 1, min(i + 20, len(lines))):  # Check next 20 lines
                    if var_name in lines[j] and not lines[j].strip().startswith("#"):
                        used = True
                        break

                if not used:
                    print(f"  🗑️  Removing unused variable: {var_name} in {file_path}:{i + 1}")
                    lines[i] = "# " + line  # Comment out instead of delete for safety
                    fixed = True

        if fixed:
            Path(file_path).write_text("\n".join(lines))

        return fixed
    except Exception as e:
        print(f"❌ Error analyzing {file_path}: {e}")
        return False


def main():
    print("🎯 Targeted Code Quality Fixes")
    print("=" * 40)

    fixes_made = 0

    # Fix lambda assignments
    print("🔧 Converting lambda assignments to def functions...")
    python_files = list(Path(".").rglob("*.py"))
    for file_path in python_files:
        if fix_lambda_assignments(str(file_path)):
            fixes_made += 1
            print(f"  ✅ Fixed lambda in {file_path}")

    # Fix unused variables (more conservative approach)
    print("\n🔍 Analyzing unused variables...")
    specific_files = ["nlp/generation.py", "core/copy_quality.py"]

    for file_path in specific_files:
        if os.path.exists(file_path):
            if fix_unused_variables(file_path):
                fixes_made += 1

    print("\n🎉 Completed targeted fixes!")
    print(f"Total fixes applied: {fixes_made}")

    if fixes_made > 0:
        print("\n💡 Recommend running ruff again to verify fixes:")
        print("   .venv/bin/python3 -m ruff check . --statistics")
    else:
        print("\n✨ No additional fixes needed for these issue types.")


if __name__ == "__main__":
    main()
