/** Escape JSON for safe embedding in HTML script blocks. */
export function safeJsonForScript(value: unknown): string {
  const json = JSON.stringify(value);
  // JSON.stringify(undefined) returns undefined; emit a valid literal instead.
  return (json === undefined ? 'null' : json)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}
