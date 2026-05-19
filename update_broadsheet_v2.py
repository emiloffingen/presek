import glob
import re

files = glob.glob('web/src/**/*.astro', recursive=True) + glob.glob('web/src/**/*.tsx', recursive=True)

for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # 1. Update grid-template-columns in .broadsheet-grid (including :global)
    content = re.sub(r'grid-template-columns:\s*minmax\([^)]+\)\s*[^;\}]+([;\}])', r'grid-template-columns: 1fr\1', content)

    # 2. Update .broadsheet-main (including :global)
    content = re.sub(r'((?:\.broadsheet-main|:global\(\.broadsheet-main\))\s*\{[^\}]*)border-right:\s*[^;\}]+[;]?', r'\1border-right: none;', content)
    content = re.sub(r'((?:\.broadsheet-main|:global\(\.broadsheet-main\))\s*\{[^\}]*)padding-right:\s*[^;\}]+[;]?', r'\1padding-right: 0;', content)

    # 3. Update .broadsheet-rail (including :global)
    content = re.sub(r'((?:\.broadsheet-rail|:global\(\.broadsheet-rail\))\s*\{[^\}]*)position:\s*sticky[;]?', r'\1', content)
    content = re.sub(r'((?:\.broadsheet-rail|:global\(\.broadsheet-rail\))\s*\{[^\}]*)top:\s*[^;\}]+[;]?', r'\1', content)

    # 4. Remove Tailwind classes from HTML/JSX
    # Look for broadsheet-main followed by pr- and border-r
    content = re.sub(r'(class(?:Name)?="[^"]*broadsheet-main)\s+pr-\d+\s+border-r\s+border-border/40([^"]*")', r'\1\2', content)
    # Generic cleanup of pr- and border-r near broadsheet-main if needed
    content = re.sub(r'(class(?:Name)?="[^"]*broadsheet-main)\s+pr-12\s+border-r([^"]*")', r'\1\2', content)

    if content != original_content:
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated: {file}")

