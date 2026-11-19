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
  cities: string[];
}

export function prepare(map: MapFile): Explorer {
  const graph = buildGraph(map.artists, map.related);
  const sceneOf = map.artists.map((artist) => artist.scene);
  let maxNights = 0;
  for (const artist of map.artists) maxNights = Math.max(maxNights, artist.nights);
  const homes = new Map<string, number>();
  for (const artist of map.artists) {
    const home = artist.cities[0];
    if (home !== undefined) homes.set(home, (homes.get(home) ?? 0) + 1);
  }
  const cities = [...homes].sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0])).map(([city]) => city);
  return {
    map,
    graph,
    related: relatedBySource(graph, map.related),
    search: buildSearchIndex(map.artists),
    sceneOf,
    sceneById: new Map(map.scenes.map((scene) => [scene.id, scene])),
    maxNights,
    withoutScene: sceneOf.filter((scene) => scene === null).length,
    cities,
  };
}

export function inCity(map: MapFile, city: string): Uint8Array {
  return Uint8Array.from(map.artists, (artist) => (artist.cities.includes(city) ? 1 : 0));
}

export function basedIn(map: MapFile, city: string): number[] {
  const indices: number[] = [];
  map.artists.forEach((artist, i) => {
    if (artist.cities[0] === city) indices.push(i);
  });
  return indices;
}
