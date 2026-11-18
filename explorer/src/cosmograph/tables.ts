import { Table, Utf8, makeBuilder, makeVector, type Vector } from "apache-arrow";
import type { Explorer } from "../graph/prepare";
import type { DuckDBConnection } from "./duckdb";
import { escapeHtml } from "../graph/text";

export interface GraphTables {
  points: string;
  links: string;
}

export interface ArrowTables {
  points: Table;
  links: Table;
}

function utf8(values: readonly string[]): Vector<Utf8> {
  const builder = makeBuilder({ type: new Utf8(), nullValues: [] });
  for (const value of values) builder.append(value);
  return builder.finish().toVector();
}

function sequence(length: number): Int32Array {
  return Int32Array.from({ length }, (_, i) => i);
}

export function arrowTables({ map, graph }: Explorer): ArrowTables {
  const ids = Array.from(graph.ids, (id) => String(id));
  const points = new Table({
    idx: makeVector(sequence(graph.size)),
    id: utf8(ids),
    label: utf8(map.artists.map((artist) => escapeHtml(artist.name))),
    nights: makeVector(Int32Array.from(map.artists, (artist) => artist.nights)),
  });
  const links = new Table({
    edge: makeVector(sequence(graph.edgeCount)),
    source: utf8(Array.from(graph.edgeSource, (i) => ids[i])),
    target: utf8(Array.from(graph.edgeTarget, (i) => ids[i])),
    sourceidx: makeVector(graph.edgeSource),
    targetidx: makeVector(graph.edgeTarget),
  });
  return { points, links };
}

export async function uploadTables(connection: DuckDBConnection, tables: ArrowTables): Promise<GraphTables> {
  const db = connection.connection ?? (await connection.duckdb.connect());
  await db.insertArrowTable(tables.points, { name: "explorer_points" });
  await db.insertArrowTable(tables.links, { name: "explorer_links" });
  return { points: "explorer_points", links: "explorer_links" };
}
