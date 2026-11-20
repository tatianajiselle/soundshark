import { mainIndices, type Graph, type RelatedEntry } from "./graph";
import type { Rgba, Styling } from "./styling";

export function edgeBetween(graph: Graph, a: number, b: number): number {
  for (let k = graph.offsets[a]; k < graph.offsets[a + 1]; k += 1) {
    if (graph.neighbours[k] === b) return graph.neighbourEdges[k];
  }
  return -1;
}

export function mainMask(graph: Graph): Uint8Array {
  const mask = new Uint8Array(graph.size);
  for (const index of mainIndices(graph)) mask[index] = 1;
  return mask;
}

export function layoutEdges(
  graph: Graph,
  related: readonly (readonly RelatedEntry[])[],
  shown: Uint8Array,
  perArtist: number,
): number[] {
  const picked = new Uint8Array(graph.edgeCount);
  const edges: number[] = [];
  for (let a = 0; a < graph.size; a += 1) {
    if (shown[a] !== 1) continue;
    let taken = 0;
    for (const { index: b } of related[a]) {
      if (taken >= perArtist) break;
      if (shown[b] !== 1) continue;
      const e = edgeBetween(graph, a, b);
      if (e < 0) continue;
      taken += 1;
      if (picked[e] === 0) {
        picked[e] = 1;
        edges.push(e);
      }
    }
  }
  return edges;
}

export function emphasisedEdges(
  graph: Graph,
  styling: Styling,
  shown: Uint8Array,
  skip: ReadonlySet<number>,
): number[] {
  const edges: number[] = [];
  for (let e = 0; e < graph.edgeCount; e += 1) {
    if (styling.linkWidths[e] <= 1 || skip.has(e)) continue;
    if (shown[graph.edgeSource[e]] === 1 && shown[graph.edgeTarget[e]] === 1) edges.push(e);
  }
  return edges;
}

export function rgbaCss([r, g, b, a]: Rgba): string {
  return `rgba(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)},${a})`;
}
