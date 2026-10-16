// Dependency-free so it can be unit-tested directly with node --test.
export function parseTopicParam(raw: string | undefined) {
  const value = raw || '';
  let cleaned: string;
  try {
    cleaned = decodeURIComponent(value).replace(/\s+/g, ' ').trim();
  } catch {
    cleaned = value.replace(/\s+/g, ' ').trim();
  }
  // Topics are stored capitalised ("Politika") and matched exactly, but a hand-typed slug is
  // usually lowercase ("/tema/politika") and used to land on an empty page. Capitalise plain
  // lowercase Latin slugs; anything else (Cyrillic, already capitalised, digits) is left alone.
  return /^[a-z]+(?: [a-z]+)*$/.test(cleaned) ? cleaned.replace(/\b[a-z]/g, (c) => c.toUpperCase()) : cleaned;
}
