import React from 'react';

// Transliteration character mapping for Cyrillic/Latin script-agnostic matching
const SCRIPT_MAP: Record<string, string[]> = {
  'a': ['a', 'а', 'А', 'A'],
  'а': ['a', 'а', 'А', 'A'],
  'b': ['b', 'б', 'Б', 'B'],
  'б': ['b', 'б', 'Б', 'B'],
  'v': ['v', 'в', 'В', 'V'],
  'в': ['v', 'в', 'В', 'V'],
  'g': ['g', 'г', 'Г', 'G', 'ѓ', 'Ѓ'],
  'г': ['g', 'г', 'Г', 'G', 'ѓ', 'Ѓ'],
  'ѓ': ['g', 'г', 'Г', 'G', 'ѓ', 'Ѓ'],
  'd': ['d', 'д', 'Д', 'D'],
  'д': ['d', 'д', 'Д', 'D'],
  'đ': ['đ', 'ђ', 'Ђ', 'Đ'],
  'ђ': ['đ', 'ђ', 'Ђ', 'Đ'],
  'e': ['e', 'е', 'Е', 'E'],
  'е': ['e', 'е', 'Е', 'E'],
  'ž': ['ž', 'ж', 'Ж', 'Ž'],
  'ж': ['ž', 'ж', 'Ж', 'Ž'],
  'z': ['z', 'з', 'З', 'Z'],
  'з': ['z', 'з', 'З', 'Z'],
  'i': ['i', 'и', 'И', 'I'],
  'и': ['i', 'и', 'И', 'I'],
  'j': ['j', 'ј', 'Ј', 'J'],
  'ј': ['j', 'ј', 'Ј', 'J'],
  'k': ['k', 'к', 'К', 'K', 'ќ', 'Ќ'],
  'к': ['k', 'к', 'К', 'K', 'ќ', 'Ќ'],
  'ќ': ['k', 'к', 'К', 'K', 'ќ', 'Ќ'],
  'l': ['l', 'л', 'Л', 'L'],
  'л': ['l', 'л', 'Л', 'L'],
  'љ': ['љ', 'Љ'],
  'm': ['m', 'м', 'М', 'M'],
  'м': ['m', 'м', 'М', 'M'],
  'n': ['n', 'н', 'Н', 'N'],
  'н': ['n', 'н', 'Н', 'N'],
  'њ': ['њ', 'Њ'],
  'o': ['o', 'о', 'О', 'O'],
  'о': ['o', 'о', 'О', 'O'],
  'p': ['p', 'п', 'П', 'P'],
  'п': ['p', 'п', 'П', 'P'],
  'r': ['r', 'р', 'Р', 'R'],
  'р': ['r', 'р', 'Р', 'R'],
  's': ['s', 'с', 'С', 'S'],
  'с': ['s', 'с', 'С', 'S'],
  'ѕ': ['ѕ', 'Ѕ'],
  't': ['t', 'т', 'Т', 'T'],
  'т': ['t', 'т', 'Т', 'T'],
  'ć': ['ć', 'ћ', 'Ћ', 'Ć'],
  'ћ': ['ć', 'ћ', 'Ћ', 'Ć'],
  'u': ['u', 'у', 'У', 'U'],
  'у': ['u', 'у', 'У', 'U'],
  'f': ['f', 'ф', 'Ф', 'F'],
  'ф': ['f', 'ф', 'Ф', 'F'],
  'h': ['h', 'х', 'Х', 'H'],
  'х': ['h', 'х', 'Х', 'H'],
  'c': ['c', 'ц', 'Ц', 'C'],
  'ц': ['c', 'ц', 'Ц', 'C'],
  'č': ['č', 'ч', 'Ч', 'Č'],
  'ч': ['č', 'ч', 'Ч', 'Č'],
  'џ': ['џ', 'Џ'],
  'š': ['š', 'ш', 'Ш', 'Š'],
  'ш': ['š', 'ш', 'Ш', 'Š']
};

function getScriptAgnosticPattern(query: string): string {
  let escaped = query.toLowerCase().replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');

  // Replace digraphs first
  escaped = escaped.replace(/dž/g, '(џ|dž)');
  escaped = escaped.replace(/lj/g, '(љ|lj)');
  escaped = escaped.replace(/nj/g, '(њ|nj)');
  escaped = escaped.replace(/dz/g, '(ѕ|dz)');

  let result = '';
  for (let i = 0; i < escaped.length; i++) {
    const char = escaped[i];
    if (char === '(') {
      const endIdx = escaped.indexOf(')', i);
      if (endIdx !== -1) {
        result += escaped.substring(i, endIdx + 1);
        i = endIdx;
        continue;
      }
    }

    const mapping = SCRIPT_MAP[char];
    if (mapping) {
      result += `[${Array.from(new Set(mapping)).join('')}]`;
    } else {
      result += char;
    }
  }
  return result;
}

function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const pattern = getScriptAgnosticPattern(query);
  const regex = new RegExp(`(${pattern})`, 'gi');
  const testRegex = new RegExp(`^(${pattern})$`, 'i');
  const parts = text.split(regex);
  return (
    <>
      {parts.map((part, i) =>
        testRegex.test(part) ? (
          <mark
            key={i}
            className="bg-amber-500/20 text-amber-900 dark:bg-amber-500/30 dark:text-amber-300 font-bold px-0.5 rounded-none"
          >
            {part}
          </mark>
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        )
      )}
    </>
  );
}

// Memoized wrapper so highlighting is not recomputed for unchanged items/queries
export const HighlightMatch = React.memo(function HighlightMatch({
  text,
  query,
}: {
  text: string;
  query: string;
}) {
  return <>{highlightMatch(text, query)}</>;
});
