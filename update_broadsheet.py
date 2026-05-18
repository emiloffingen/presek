import os
import glob
import re

files = glob.glob('web/src/**/*.astro', recursive=True) + glob.glob('web/src/**/*.tsx', recursive=True)

for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'broadsheet-grid' not in content:
        continue

    original_content = content

    # Change grid-template-columns in .broadsheet-grid
    content = re.sub(r'grid-template-columns:\s*minmax\([^)]+\)\s*[^;\}]+([;\}])', r'grid-template-columns: 1fr\1', content)

    # Update .broadsheet-main
    content = re.sub(r'(\.broadsheet-main\s*\{[^\}]*)border-right:\s*[^;\}]+[;]?', r'\1border-right: none;', content)
    content = re.sub(r'(\.broadsheet-main\s*\{[^\}]*)padding-right:\s*[^;\}]+[;]?', r'\1padding-right: 0;', content)

    # Update .broadsheet-rail
    content = re.sub(r'(\.broadsheet-rail\s*\{[^\}]*)position:\s*sticky[;]?', r'\1', content)
    content = re.sub(r'(\.broadsheet-rail\s*\{[^\}]*)top:\s*[^;\}]+[;]?', r'\1', content)

    if content != original_content:
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated: {file}")

