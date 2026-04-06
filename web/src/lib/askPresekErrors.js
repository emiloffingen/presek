export const genericAskError =
  'Во моментов не можам сигурно да одговорам на ова прашање. Обидете се повторно за кратко.';

export function normalizeAskErrorMessage(message, status) {
  const clean = String(message || '').trim();
  if (!clean) return genericAskError;

  const lowered = clean.toLowerCase();
  if (
    lowered === 'internal server error' ||
    lowered.includes('<html') ||
    lowered.includes('<!doctype') ||
    lowered.includes('failed to process query') ||
    lowered.includes('failed to fetch')
  ) {
    return genericAskError;
  }

  if (status && status >= 500) {
    return genericAskError;
  }

  return clean;
}
