export interface UrlState {
  a: number | null;
  b: number | null;
}

function readId(value: string | null): number | null {
  if (value === null || !/^-?\d{1,15}$/.test(value)) return null;
  return Number(value);
}

export function parseHash(hash: string): UrlState {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const a = readId(params.get("a"));
  const b = a === null ? null : readId(params.get("b"));
  return { a, b: b === a ? null : b };
}

export function formatHash(state: UrlState): string {
  if (state.a === null) return "";
  const parts = [`a=${state.a}`];
  if (state.b !== null && state.b !== state.a) parts.push(`b=${state.b}`);
  return `#${parts.join("&")}`;
}

export function safeHref(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}
