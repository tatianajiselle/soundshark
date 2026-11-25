import type { RelatedEntry } from "./graph";

export interface DegreeEntry {
  index: number;
  score: number;
  via: number | null;
}

export interface DegreeList {
  entries: DegreeEntry[];
  total: number;
}

export function relatedAtDegree(
  related: readonly (readonly RelatedEntry[])[],
  focus: number,
  degree: number,
  limit: number,
): DegreeList {
  const seen = new Set<number>([focus]);
  let layer = new Map<number, DegreeEntry>([[focus, { index: focus, score: 1, via: null }]]);
  for (let step = 1; step <= degree; step += 1) {
    const next = new Map<number, DegreeEntry & { best: number }>();
    for (const parent of layer.values()) {
      const list = related[parent.index] ?? [];
      const top = list[0]?.score ?? 0;
      if (top <= 0) continue;
      for (const entry of list) {
        if (seen.has(entry.index)) continue;
        const share = parent.score * (entry.score / top);
        const current = next.get(entry.index);
        if (current === undefined) {
          next.set(entry.index, {
            index: entry.index,
            score: share,
            via: step === 1 ? null : parent.index,
            best: share,
          });
        } else {
          current.score += share;
          if (share > current.best) {
            current.best = share;
            current.via = parent.index;
          }
        }
      }
    }
    for (const index of next.keys()) seen.add(index);
    layer = new Map([...next].map(([index, { score, via }]) => [index, { index, score, via }]));
  }
  const entries = [...layer.values()].sort((a, b) => b.score - a.score || a.index - b.index);
  return { entries: entries.slice(0, limit), total: entries.length };
}
