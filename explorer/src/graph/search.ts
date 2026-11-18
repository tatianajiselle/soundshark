import type { Artist } from "./mapFile";

const FOLDS: Record<string, string> = {
  ß: "ss",
  æ: "ae",
  œ: "oe",
  ø: "o",
  đ: "d",
  ð: "d",
  ł: "l",
  þ: "th",
  ı: "i",
};

const FOLD_PATTERN = new RegExp(`[${Object.keys(FOLDS).join("")}]`, "g");

export function normalize(text: string): string {
  return text
    .normalize("NFKD")
    .toLowerCase()
    .replace(/\p{M}+/gu, "")
    .replace(FOLD_PATTERN, (ch) => FOLDS[ch] ?? ch)
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

export const MatchTier = {
  Exact: 0,
  Prefix: 1,
  WordPrefix: 2,
  Substring: 3,
} as const;

export type MatchTier = (typeof MatchTier)[keyof typeof MatchTier];

export interface SearchHit {
  index: number;
  tier: MatchTier;
  alias: string | null;
}

interface Entry {
  index: number;
  text: string;
  alias: string | null;
}

export interface SearchIndex {
  entries: Entry[];
  nights: Int32Array;
  names: string[];
}

export function buildSearchIndex(artists: readonly Artist[]): SearchIndex {
  const entries: Entry[] = [];
  const nights = new Int32Array(artists.length);
  const names: string[] = [];
  artists.forEach((artist, index) => {
    nights[index] = artist.nights;
    names.push(artist.name);
    const name = normalize(artist.name);
    if (name !== "") entries.push({ index, text: name, alias: null });
    const seen = new Set([name]);
    for (const alias of artist.aliases) {
      const text = normalize(alias);
      if (text === "" || seen.has(text)) continue;
      seen.add(text);
      entries.push({ index, text, alias });
    }
  });
  return { entries, nights, names };
}

function tierOf(text: string, query: string): MatchTier | null {
  if (text === query) return MatchTier.Exact;
  if (text.startsWith(query)) return MatchTier.Prefix;
  if (!text.includes(query)) return null;
  if (text.includes(` ${query}`)) return MatchTier.WordPrefix;
  return MatchTier.Substring;
}

export function search(index: SearchIndex, rawQuery: string, limit = 8): SearchHit[] {
  const query = normalize(rawQuery);
  if (query === "") return [];
  const best = new Map<number, SearchHit>();
  for (const entry of index.entries) {
    const tier = tierOf(entry.text, query);
    if (tier === null) continue;
    const current = best.get(entry.index);
    if (
      current === undefined ||
      tier < current.tier ||
      (tier === current.tier && current.alias !== null && entry.alias === null)
    ) {
      best.set(entry.index, { index: entry.index, tier, alias: entry.alias });
    }
  }
  return [...best.values()]
    .sort(
      (a, b) =>
        a.tier - b.tier ||
        index.nights[b.index] - index.nights[a.index] ||
        index.names[a.index].localeCompare(index.names[b.index]) ||
        a.index - b.index,
    )
    .slice(0, limit);
}
