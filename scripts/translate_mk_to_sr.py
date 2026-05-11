#!/usr/bin/env python3
"""
Translation script: Macedonian Cyrillic → Serbian Latin

This script automates the transition from Macedonian to Serbian.

Usage:
    # Scan for files with Cyrillic/RS references
    python3 scripts/translate_mk_to_sr.py --stats
    
    # Preview changes for specific files
    python3 scripts/translate_mk_to_sr.py --files local_analyst.py tasks/delivery.py
    
    # Apply changes to specific files
    python3 scripts/translate_mk_to_sr.py --files local_analyst.py --apply
    
    # Process all files
    python3 scripts/translate_mk_to_sr.py --all --apply
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

# Root directory of the project
ROOT = Path(__file__).parent.parent

# ============================================================================
# TRANSLATION MAPPINGS
# ============================================================================

# Macedonian to Serbian Latin word/phrase mappings
MK_TO_SR: Dict[str, str] = {
    # News terms
    "vest": "vest", "vesti": "vesti", "vest": "vest",
    "izvor": "izvor", "izvori": "izvori", "izvor": "izvor",
    "klaster": "klaster", "klasteri": "klasteri",
    "clanak": "clanak", "clanci": "clanci", "clanci": "clanci",
    "prica": "prica", "price": "price",
    
    # Analysis terms
    "perspektiva": "perspektiva",
    "ugao": "ugao", "ugao": "ugao",
    "tacka": "tacka",
    "stav": "stav", "stavovi": "stavovi",
    "glediste": "glediste",
    "rezime": "rezime",
    "sublimat": "sublimat",
    "razliciti": "razliciti", "razlicito": "razlicito",
    "akcenti": "akcenti", "akcenat": "akcenat",
    "zajednicka": "zajednicka", "zajednicki": "zajednicki",
    "linija": "linija",
    "otvoreno": "otvoreno",
    "nejasno": "nejasno", "nejasnost": "nejasnost",
    "nepotvrdeno": "nepotvrdeno", "nepotvrdeni": "nepotvrdeni",
    "potvrdeno": "potvrdeno", "potvrdeni": "potvrdeni",
    "ostaje": "ostaje", "ostaju": "ostaju",
    "reakcije": "reakcije", "reakcija": "reakcija",
    "odgovori": "odgovori", "odgovor": "odgovor",
    "komentar": "komentar", "komentari": "komentari",
    "osuda": "osuda", "osuda": "osuda",
    "kontekst": "kontekst",
    "pozadina": "pozadina", "pozadina": "pozadina",
    "siri": "siri", "sirok": "sirok",
    "glavni": "glavni", "glavni": "glavni", "glavna": "glavna", "glavno": "glavno",
    "razvoj": "razvoj",
    "ova": "ova", "ova": "ova",
    "izvestaj": "izvestaj",
    "jos": "jos", "jos": "jos", "jos uvek": "jos uvek",
    "sledece": "sledece", "dalje": "dalje",
    "posledice": "posledice", "posledica": "posledica", "posledice": "posledice",
    "najvazniji": "najvazniji", "najvazniji": "najvazniji", "najvaznije": "najvaznije", "najvaznija": "najvaznija",
    "nove": "nove", "novi": "novi", "nova": "nova",
    
    # Perspective labels
    "Kljucan ugao": "Kljucan ugao",
    "Razliciti akcenti": "Razliciti akcenti",
    "Zajednicka linija": "Zajednicka linija",
    "Sta ostaje otvoreno": "Sta ostaje otvoreno",
    "Sta ostaje otvoreno": "Sta ostaje otvoreno",
    "Reakcije i odgovori": "Reakcije i odgovori",
    "Siri kontekst": "Siri kontekst",
    "Visoko poverenje": "Visoko poverenje",
    "Nisko poverenje": "Nisko poverenje",
    "Srednje poverenje": "Srednje poverenje",
    
    # Questions
    "Sto e glavni razvoj vo ova prica?": "Sta je glavni razvoj u ovoj prici?",
    "Kako se razlikuvaat izvorite vo izvestaj?": "Kako se razlikuju izvori u izvestaju?",
    "Sto jos uvek ne e potvrdeno?": "Sta jos uvek nije potvrdeno?",
    "Koji je najvazniji razvoj u temi": "Koji je najvazniji razvoj u temi",
    "Sto ostaje nejasno ili nepotvrdeno?": "Sta ostaje nejasno ili nepotvrdeno?",
    "Sto sleduva dalje vo ova prica?": "Sta sledi dalje u ovoj prici?",
    "Sto e najvaznoto novo vo ova vest?": "Sta je najvaznija vest u ovoj vesti?",
    "Koi detali jos uvek zavisat od sledni potvdi?": "Koji detalji jos uvek zavise od sledecih potvrda?",
    "Koi detali jos uvek zavisat od sledni potvrdi?": "Koji detalji jos uvek zavise od sledecih potvrda?",
    
    # Categories
    "Politika": "Politika", "Sport": "Sport", "Hronika": "Hronika",
    "Ekonomija": "Ekonomija", "Balkan": "Balkan", "Svet": "Svet",
    "Dijaspora": "Dijaspora", "Kultura": "Kultura",
    "Tehnologija": "Tehnologija", "Zdravstvo": "Zdravstvo",
    "Obrazovanje": "Obrazovanje",
    "Srbija": "Srbija", "Beograd": "Beograd",
    
    # Time terms
    "danas": "danas", "danas": "danas",
    "juce": "juce", "sutra": "sutra",
    
    # Month names
    "januar": "januar", "februar": "februar", "mart": "mart",
    "april": "april", "maj": "maj", "jun": "jun",
    "jul": "jul", "avgust": "avgust",
    "septembar": "septembar", "oktobar": "oktobar",
    "novembar": "novembar", "decembar": "decembar",
    
    # Day names
    "Ponedeljak": "Ponedeljak", "Utorak": "Utorak", "Sreda": "Sreda",
    "Cetvrtak": "Cetvrtak", "Petak": "Petak", "Subota": "Subota", "Nedelja": "Nedelja",
    
    # Delivery/push notification terms
    "Vodeci izvor": "Vodeci izvor",
    "Broj izvora": "Broj izvora",
    "sledeci izvor": "sledeci izvor",
    "Praceni izvori": "Praceni izvori",
    "Fokus izvori": "Fokus izvori",
    "Kljucna prica": "Kljucna prica",
    "Kljucna prica nedeljna": "Kljucna prica nedeljna",
    "Vazna prica": "Vazna prica",
    "nedeljni kontekst": "nedeljni kontekst",
    
    # Various other terms found in code
    " sve": " sva",
    " gi": " im",
    " go": " ga",
    " im": " im",
    " mu": " mu",
    " ja": " me",
    " mi": " mi",
    " me": " me",
    " te": " te",
    " ve": " vi",
    " ni": " nas",
    " si": " si",
    "ce": "ce",
    "a": "a", "b": "b", "v": "v", "g": "g", "d": "d",
    "dj": "dj", "e": "e", "z": "z", "z": "z",
    "i": "i", "j": "j", "k": "k", "l": "l",
    "lj": "lj", "m": "m", "n": "n", "nj": "nj",
    "o": "o", "p": "p", "r": "r", "s": "s",
    "t": "t", "c": "c", "u": "u", "f": "f",
    "h": "h", "c": "c", "c": "c", "dz": "dz",
    "s": "s",
    "A": "A", "B": "B", "V": "V", "G": "G", "D": "D",
    "Dj": "Dj", "E": "E", "Z": "Z", "Z": "Z",
    "I": "I", "J": "J", "K": "K", "L": "L",
    "Lj": "Lj", "M": "M", "N": "N", "Nj": "Nj",
    "O": "O", "P": "P", "R": "R", "S": "S",
    "T": "T", "C": "C", "U": "U", "F": "F",
    "H": "H", "C": "C", "C": "C", "Dz": "Dz",
    "S": "S",
}

# RS country code to RS
MK_CODE_TO_RS: Dict[str, str] = {
    "RS": "RS", "rs": "rs",
    "Srbija": "Srbija", "srbija": "srbija",
}

# Cyrillic regex patterns
CYRILLIC_PATTERNS: List[Tuple[str, str]] = [
    (r"\[A-Za-z\w\]", r"[A-Za-z\w]"),
    (r"\[A-Za-z\w\]\+", r"[A-Za-z\w]+"),
    (r"\[A-Za-z\w\]\{3,\}", r"[A-Za-z\w]{3,}"),
    (r"A-Za-z", "A-Za-z"),
]

# Skip patterns
SKIP_FILES: set = {".venv", "node_modules", "__pycache__", ".pyc", "uv.lock", "requirements.txt", "package-lock.json"}
PROCESS_EXTENSIONS: set = {".py", ".js", ".ts", ".tsx", ".astro", ".json", ".md", ".txt"}


# ============================================================================
# FUNCTIONS
# ============================================================================

def find_files(root: Path, extensions: set, skip_dirs: set) -> List[Path]:
    """Find all files with given extensions, skipping specified directories."""
    files = []
    for path in root.rglob("*"):
        if path.is_file():
            if path.suffix in extensions:
                if not any(skip in path.parts for skip in skip_dirs):
                    files.append(path)
    return files


def contains_cyrillic(text: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", text))


def contains_mk_code(text: str) -> bool:
    return bool(re.search(r"\bMK\b|\bmk\b|MK|rs", text))


def translate_text(text: str, dry_run: bool = True) -> Tuple[str, List[str]]:
    changes = []
    translated = text
    
    # Word/phrase replacements (longest first)
    sorted_mappings = sorted(MK_TO_SR.items(), key=lambda x: len(x[0]), reverse=True)
    
    for mk, sr in sorted_mappings:
        if len(mk) < 2:
            continue
        # Word boundary matching, case-insensitive
        pattern = r"\b" + re.escape(mk) + r"\b"
        matches = re.findall(pattern, translated, flags=re.IGNORECASE)
        if matches:
            count = len(matches)
            if not dry_run:
                translated = re.sub(pattern, sr, translated, flags=re.IGNORECASE)
            changes.append(f"  '{mk}' → '{sr}' ({count})")
    
    # Country code RS -> RS
    for mk, rs in MK_CODE_TO_RS.items():
        pattern = r"\b" + re.escape(mk) + r"\b"
        matches = re.findall(pattern, translated)
        if matches:
            count = len(matches)
            if not dry_run:
                translated = re.sub(pattern, rs, translated)
            changes.append(f"  country '{mk}' → '{rs}' ({count})")
    
    # Cyrillic regex patterns
    for pattern, replacement in CYRILLIC_PATTERNS:
        if re.search(pattern, translated):
            count = len(re.findall(pattern, translated))
            if not dry_run:
                translated = re.sub(pattern, replacement, translated)
            changes.append(f"  pattern '{pattern}' → '{replacement}' ({count})")
    
    # Individual Cyrillic chars (fallback)
    cyrillic_pattern = r"[\u0400-\u04FF]"
    if re.search(cyrillic_pattern, translated):
        cyrillic_count = len(re.findall(cyrillic_pattern, translated))
        if not dry_run:
            for char, latin in MK_TO_SR.items():
                if len(char) == 1:
                    translated = translated.replace(char, latin)
        changes.append(f"  Cyrillic chars → Latin ({cyrillic_count})")
    
    return translated, changes


def translate_file(filepath: Path, dry_run: bool = True) -> Tuple[bool, List[str]]:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        has_cyrillic = contains_cyrillic(content)
        has_mk = contains_mk_code(content)
        
        if not has_cyrillic and not has_mk:
            return False, []
        
        translated, changes = translate_text(content, dry_run)
        
        if changes and not dry_run:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(translated)
            return True, changes
        
        return bool(changes), changes
        
    except Exception as e:
        return False, [f"  ERROR: {e}"]


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Translate Macedonian Cyrillic to Serbian Latin"
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Preview changes (default)")
    parser.add_argument("--apply", action="store_true", default=False,
                        help="Apply changes to files")
    parser.add_argument("--files", nargs="+", default=None,
                        help="Specific files to process")
    parser.add_argument("--all", action="store_true", default=False,
                        help="Process all files")
    parser.add_argument("--stats", action="store_true", default=False,
                        help="Show statistics only")
    
    args = parser.parse_args()
    
    dry_run = not args.apply
    if args.stats:
        dry_run = True
    
    # Collect files
    if args.files:
        files_to_process = [ROOT / f for f in args.files]
    elif args.all:
        files_to_process = find_files(ROOT, PROCESS_EXTENSIONS, SKIP_FILES)
    else:
        files_to_process = find_files(ROOT, PROCESS_EXTENSIONS, SKIP_FILES)
    
    # Find files with issues
    print(f"Scanning {len(files_to_process)} files...")
    files_with_issues = []
    
    for filepath in files_to_process:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if contains_cyrillic(content) or contains_mk_code(content):
                files_with_issues.append(filepath)
        except Exception:
            pass
    
    if args.stats:
        print(f"\n{'='*70}")
        print(f"Files with Macedonian Cyrillic/RS references: {len(files_with_issues)}")
        print(f"{'='*70}")
        for fp in sorted(files_with_issues):
            print(f"  {fp.relative_to(ROOT)}")
        return
    
    # Process files
    print(f"\n{'='*70}")
    print(f"TRANSLATION: Macedonian → Serbian Latin")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY CHANGES'}")
    print(f"{'='*70}\n")
    
    for filepath in sorted(files_with_issues):
        was_modified, changes = translate_file(filepath, dry_run)
        if changes:
            rel_path = filepath.relative_to(ROOT)
            print(f"\n{rel_path}:")
            for change in changes:
                print(change)
    
    print(f"\n{'='*70}")
    if dry_run:
        print(f"DRY RUN: Would modify {len(files_with_issues)} files")
    else:
        print(f"Done!")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
