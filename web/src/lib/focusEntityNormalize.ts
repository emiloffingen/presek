/** Mirrors nlp/keywords.FOCUS_ENTITY_SURFACE_NORMALIZATIONS for client-side display dedup. */
const SURFACE_NORMALIZATIONS: Record<string, string> = {
  srbije: 'Srbija',
  srbiji: 'Srbija',
  srbijom: 'Srbija',
  srbiju: 'Srbija',
  beogradu: 'Beograd',
  beograda: 'Beograd',
  evrope: 'Evropa',
  evropi: 'Evropa',
  evropu: 'Evropa',
  kosova: 'Kosovo',
  kosovu: 'Kosovo',
  kosovom: 'Kosovo',
  kine: 'Kina',
  kini: 'Kina',
  kinom: 'Kina',
  rusije: 'Rusija',
  rusiji: 'Rusija',
  rusijom: 'Rusija',
  ukrajine: 'Ukrajina',
  ukrajini: 'Ukrajina',
  ukrajinom: 'Ukrajina',
  ukrajinu: 'Ukrajina',
  partizana: 'Partizan',
  partizanu: 'Partizan',
  zvezde: 'Crvena zvezda',
  zvezdi: 'Crvena zvezda',
  zvezda: 'Crvena zvezda',
  evrovizije: 'Evrovizija',
  evroviziji: 'Evrovizija',
  policije: 'Policija',
  policiji: 'Policija',
};

function capitalizeLeadingWord(value: string): string {
  const first = value.charAt(0);
  if (!first || first === first.toUpperCase()) return value;
  return `${first.toUpperCase()}${value.slice(1)}`;
}

export function normalizeFocusEntitySurface(name: string): string {
  const clean = String(name || '').trim().replace(/\s+/g, ' ');
  if (!clean) return '';
  const normalized = SURFACE_NORMALIZATIONS[clean.toLowerCase()] ?? clean;
  return capitalizeLeadingWord(normalized);
}
