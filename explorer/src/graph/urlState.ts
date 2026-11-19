export interface UrlState {
  a: number | null;
  b: number | null;
  city: string | null;
}

function readId(value: string | null): number | null {
  if (value === null || !/^-?\d{1,15}$/.test(value)) return null;
  return Number(value);
}

export function parseHash(hash: string): UrlState {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const a = readId(params.get("a"));
  const b = a === null ? null : readId(params.get("b"));
  const city = params.get("c")?.trim() || null;
  return { a, b: b === a ? null : b, city };
}

export function formatHash(state: UrlState): string {
  const params = new URLSearchParams();
  if (state.a !== null) {
    params.set("a", String(state.a));
    if (state.b !== null && state.b !== state.a) params.set("b", String(state.b));
  }
  if (state.city !== null) params.set("c", state.city);
  const hash = params.toString();
  return hash === "" ? "" : `#${hash}`;
}

export function safeHref(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}
