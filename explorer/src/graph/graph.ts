import type { Artist, RelatedRow } from "./mapFile";

export interface Graph {
  size: number;
  ids: Int32Array;
  indexById: Map<number, number>;
  edgeCount: number;
  edgeSource: Int32Array;
  edgeTarget: Int32Array;
  offsets: Int32Array;
  neighbours: Int32Array;
  neighbourEdges: Int32Array;
}

export interface RelatedEntry {
  index: number;
  score: number;
}

export function buildGraph(artists: readonly Artist[], related: readonly RelatedRow[]): Graph {
  const size = artists.length;
  const ids = new Int32Array(size);
  const indexById = new Map<number, number>();
  artists.forEach((artist, i) => {
    ids[i] = artist.id;
    indexById.set(artist.id, i);
  });

  const seen = new Set<number>();
  const sources: number[] = [];
  const targets: number[] = [];
  for (const [sourceId, targetId] of related) {
    const a = indexById.get(sourceId);
    const b = indexById.get(targetId);
    if (a === undefined || b === undefined || a === b) continue;
    const lo = a < b ? a : b;
    const hi = a < b ? b : a;
    const key = lo * size + hi;
    if (seen.has(key)) continue;
    seen.add(key);
    sources.push(lo);
    targets.push(hi);
  }

  const edgeCount = sources.length;
  const edgeSource = Int32Array.from(sources);
  const edgeTarget = Int32Array.from(targets);

  const degree = new Int32Array(size);
  for (let e = 0; e < edgeCount; e += 1) {
    degree[edgeSource[e]] += 1;
    degree[edgeTarget[e]] += 1;
  }
  const offsets = new Int32Array(size + 1);
  for (let i = 0; i < size; i += 1) offsets[i + 1] = offsets[i] + degree[i];
  const cursor = offsets.slice(0, size);
  const neighbours = new Int32Array(edgeCount * 2);
  const neighbourEdges = new Int32Array(edgeCount * 2);
  for (let e = 0; e < edgeCount; e += 1) {
    const a = edgeSource[e];
    const b = edgeTarget[e];
    neighbours[cursor[a]] = b;
    neighbourEdges[cursor[a]] = e;
    cursor[a] += 1;
    neighbours[cursor[b]] = a;
    neighbourEdges[cursor[b]] = e;
    cursor[b] += 1;
  }

  return { size, ids, indexById, edgeCount, edgeSource, edgeTarget, offsets, neighbours, neighbourEdges };
}

export function hopsFrom(graph: Graph, start: number, maxHops: number): Int8Array {
  const hops = new Int8Array(graph.size).fill(-1);
  if (start < 0 || start >= graph.size) return hops;
  hops[start] = 0;
  let frontier = [start];
  for (let depth = 1; depth <= maxHops && frontier.length > 0; depth += 1) {
    const next: number[] = [];
    for (const node of frontier) {
      for (let k = graph.offsets[node]; k < graph.offsets[node + 1]; k += 1) {
        const other = graph.neighbours[k];
        if (hops[other] === -1) {
          hops[other] = depth;
          next.push(other);
        }
      }
    }
    frontier = next;
  }
  return hops;
}

export function shortestPath(graph: Graph, from: number, to: number): number[] | null {
  if (from < 0 || to < 0 || from >= graph.size || to >= graph.size) return null;
  if (from === to) return [from];
  const parent = new Int32Array(graph.size).fill(-1);
  parent[from] = from;
  const queue = new Int32Array(graph.size);
  let head = 0;
  let tail = 0;
  queue[tail++] = from;
  while (head < tail) {
    const node = queue[head++];
    for (let k = graph.offsets[node]; k < graph.offsets[node + 1]; k += 1) {
      const other = graph.neighbours[k];
      if (parent[other] !== -1) continue;
      parent[other] = node;
      if (other === to) {
        const path = [to];
        let step = to;
        while (step !== from) {
          step = parent[step];
          path.push(step);
        }
        return path.reverse();
      }
      queue[tail++] = other;
    }
  }
  return null;
}

export function edgesAlong(graph: Graph, path: readonly number[]): number[] {
  const edges: number[] = [];
  for (let i = 0; i + 1 < path.length; i += 1) {
    const a = path[i];
    const b = path[i + 1];
    for (let k = graph.offsets[a]; k < graph.offsets[a + 1]; k += 1) {
      if (graph.neighbours[k] === b) {
        edges.push(graph.neighbourEdges[k]);
        break;
      }
    }
  }
  return edges;
}

export function relatedBySource(graph: Graph, related: readonly RelatedRow[]): RelatedEntry[][] {
  const lists: RelatedEntry[][] = Array.from({ length: graph.size }, () => []);
  for (const [sourceId, targetId, score] of related) {
    const a = graph.indexById.get(sourceId);
    const b = graph.indexById.get(targetId);
    if (a === undefined || b === undefined) continue;
    lists[a].push({ index: b, score });
  }
  for (const list of lists) list.sort((x, y) => y.score - x.score);
  return lists;
}

export function componentSizes(graph: Graph): { component: Int32Array; sizes: number[] } {
  const component = new Int32Array(graph.size).fill(-1);
  const sizes: number[] = [];
  const stack: number[] = [];
  for (let start = 0; start < graph.size; start += 1) {
    if (component[start] !== -1) continue;
    const id = sizes.length;
    let size = 0;
    component[start] = id;
    stack.push(start);
    while (stack.length > 0) {
      const node = stack.pop() as number;
      size += 1;
      for (let k = graph.offsets[node]; k < graph.offsets[node + 1]; k += 1) {
        const other = graph.neighbours[k];
        if (component[other] === -1) {
          component[other] = id;
          stack.push(other);
        }
      }
    }
    sizes.push(size);
  }
  return { component, sizes };
}

export function mainIndices(graph: Graph, minShare = 0.02): number[] {
  const { component, sizes } = componentSizes(graph);
  const largest = Math.max(0, ...sizes);
  const threshold = Math.min(largest, Math.max(3, Math.ceil(graph.size * minShare)));
  const indices: number[] = [];
  for (let i = 0; i < graph.size; i += 1) {
    if (sizes[component[i]] >= threshold) indices.push(i);
  }
  return indices;
}
