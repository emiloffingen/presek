/** Presek editorial placeholder tints — aligned with presek-identity.css */

export const PRESEK_MARK = '#c45c26';

const LEGACY_COLD_TINTS = new Set([
  '#1e40af',
  '#132a4f',
  '#070c16',
  '#27272a',
  '#1e3a8a',
  '#0b2545',
  '#020b18',
  '#8b5cf6',
  '#6d28d9',
  '#581c87',
  '#3b82f6',
  '#1d4ed8',
]);

/** Resolve card/hero placeholder tint from cluster dominant_color. */
export function resolvePlaceholderTint(dominantColor?: string | null): string {
  const normalized = String(dominantColor || '').trim().toLowerCase();
  if (!normalized || LEGACY_COLD_TINTS.has(normalized)) {
    return PRESEK_MARK;
  }
  return dominantColor!.trim();
}
