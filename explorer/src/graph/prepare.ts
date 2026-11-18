import { buildGraph, relatedBySource, type Graph, type RelatedEntry } from "./graph";
import type { MapFile, Scene } from "./mapFile";
import { buildSearchIndex, type SearchIndex } from "./search";

export interface Explorer {
  map: MapFile;
  graph: Graph;
  related: RelatedEntry[][];
  search: SearchIndex;
  sceneOf: (number | null)[];
  sceneById: Map<number, Scene>;
  maxNights: number;
  withoutScene: number;
}

export function prepare(map: MapFile): Explorer {
  const graph = buildGraph(map.artists, map.related);
  const sceneOf = map.artists.map((artist) => artist.scene);
  let maxNights = 0;
  for (const artist of map.artists) maxNights = Math.max(maxNights, artist.nights);
  return {
    map,
    graph,
    related: relatedBySource(graph, map.related),
    search: buildSearchIndex(map.artists),
    sceneOf,
    sceneById: new Map(map.scenes.map((scene) => [scene.id, scene])),
    maxNights,
    withoutScene: sceneOf.filter((scene) => scene === null).length,
  };
}
