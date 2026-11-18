import { openDuckDB, type DuckDBConnection } from "./cosmograph/duckdb";
import { arrowTables, uploadTables, type GraphTables } from "./cosmograph/tables";
import { MapFileError, parseMapFile, type MapFile } from "./graph/mapFile";
import { prepare, type Explorer } from "./graph/prepare";

export class LoadError extends Error {
  readonly detail: string;

  constructor(message: string, detail: string) {
    super(message);
    this.name = "LoadError";
    this.detail = detail;
  }
}

export interface Loaded {
  explorer: Explorer;
  tables: GraphTables;
  connection: DuckDBConnection;
}

async function fetchMap(): Promise<MapFile> {
  let response: Response;
  try {
    response = await fetch("./map.json", { cache: "no-cache" });
  } catch {
    throw new LoadError("The map could not be downloaded.", "Check your connection and try again.");
  }
  if (response.status === 404) {
    throw new LoadError("There is no map here yet.", "map.json was not found next to the explorer.");
  }
  if (!response.ok) {
    throw new LoadError("The map could not be downloaded.", `map.json answered with HTTP ${response.status}.`);
  }
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    throw new LoadError("The map file is broken.", "map.json is not valid JSON.");
  }
  try {
    return parseMapFile(raw);
  } catch (error) {
    if (error instanceof MapFileError) {
      throw new LoadError("The map file is not in the expected format.", `map.json: ${error.message}.`);
    }
    throw error;
  }
}

function hasWebGL(): boolean {
  const canvas = document.createElement("canvas");
  return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
}

async function openDatabase(): Promise<DuckDBConnection> {
  try {
    return await openDuckDB();
  } catch (error) {
    throw new LoadError("This browser can’t draw the map.", `The graph engine did not start: ${String(error)}`);
  }
}

export async function loadExplorer(): Promise<Loaded> {
  if (!hasWebGL()) {
    throw new LoadError("This browser can’t draw the map.", "The map needs WebGL, which is turned off or missing.");
  }
  const [map, connection] = await Promise.all([fetchMap(), openDatabase()]);
  performance.mark("explorer:map-parsed");
  const explorer = prepare(map);
  const tables = await uploadTables(connection, arrowTables(explorer));
  performance.mark("explorer:prepared");
  performance.measure("explorer:load", "explorer:start", "explorer:prepared");
  return { explorer, tables, connection };
}
